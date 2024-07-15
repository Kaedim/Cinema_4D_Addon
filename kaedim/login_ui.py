import c4d
import os
import sys
from c4d import gui, bitmaps
import urllib.request
import tempfile
from kaedim.api import refresh_jwt, fetch_assets, load_preferences


PLUGIN_ID = 1300021  # Use a unique ID for your plugin. Obtain one from Maxon to avoid conflicts.


# Path to the directory where the plugin is located
plugin_dir = os.path.dirname(__file__)
libs_path = os.path.join(plugin_dir, 'libs')
sys.path.append(libs_path)

# Now import requests
import requests

# Configuration Constants
API_DOMAIN = "https://api.kaedim3d.com/"


# State Variables
jwt_token = None
assets_list = []
state = "logged_out"


def save_preferences(dev_id, api_key, refresh_token):
    prefs = c4d.plugins.GetWorldPluginData(c4d.PLUGINTYPE_PREFS)
    if not prefs:
        prefs = c4d.BaseContainer()
    prefs.SetString(101, dev_id)
    prefs.SetString(102, api_key)
    prefs.SetString(103, refresh_token)
    c4d.plugins.SetWorldPluginData(c4d.PLUGINTYPE_PREFS, prefs)
    
def import_file(filepath):
    # Get the current active document
    doc = c4d.documents.GetActiveDocument()
    print(filepath)
    # Check file extension and call the appropriate loader
    if filepath.endswith('.obj'):
        # Import OBJ file
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import OBJ file.")
    elif filepath.endswith('.c4d'):
        # Import Cinema 4D file
        result = c4d.documents.LoadFile(filepath)
        if not result:
            c4d.gui.MessageDialog("Failed to import C4D file.")
    elif filepath.endswith('.fbx'):
        # Import FBX file
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import FBX file.")
    elif filepath.endswith('.glb') or filepath.endswith('.gltf'):
        # Import GLB/GLTF file
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import GLB/GLTF file.")
    else:
        c4d.gui.MessageDialog("Unsupported file format.")
        return
    
    # Get the imported objects
    obj = doc.GetFirstObject()
    if not obj:
        c4d.gui.MessageDialog("No object imported.")
        return
    
    # Calculate the scale factor
    bbox = obj.GetRad() * 2  # Bounding box dimensions
    max_dimension = max(bbox.x, bbox.y, bbox.z)
    scale_factor = 1000.0 / max_dimension  # Scale to 1 meter (1000 mm)

    # Apply the scale
    scale_vector = c4d.Vector(scale_factor, scale_factor, scale_factor)
    obj.SetAbsScale(scale_vector)
    
    # Update the document
    c4d.EventAdd()

def download_file(url, dest_folder, name):
    local_filename = os.path.join(dest_folder, f'{name}.obj')
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename

class FloatingPanel(c4d.gui.GeDialog):
    """Custom dialog to display assets."""
                
    page = 0
    
    def CreateLayout(self):
        global assets_list
        self.SetTitle("Kaedim Asset List")
        # Begin a scrollable group with a specified size limit and padding
        if self.ScrollGroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, scrollflags=c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_HORIZ, initw=400, inith=300):
            # Add padding around the scroll group content
            self.GroupBorderSpace(10, 10, 10, 10)  # Add padding around the entire list
            
            if self.GroupBegin(1, c4d.BFH_SCALEFIT, cols=1, rows=len(assets_list)):
                # Add padding inside the group that holds all assets
                self.GroupBorderSpace(5, 5, 5, 5)  # Padding inside the group
                print('assets', len(assets_list))
                for i in range(self.page,  len(assets_list)):
                    asset = assets_list[i]
                    asset_tags = asset['image_tags']
                    print(asset_tags[0])
                    asset_image = asset['image'][0]
                    status = asset['iterations'][0]['status']
                    if asset_tags:
                        # Begin a group for each asset (row) with two columns: one for the label, one for the button
                        if self.GroupBegin(10000 + i, c4d.BFH_CENTER, cols=2, rows=1):
                            # Adding space around each row
                            self.GroupBorderSpace(10, 5, 10, 5)  # Padding around each asset row
                            
                            # Custom area for image
                            # self.AddUserArea(7000 + i, c4d.BFH_CENTER, initw=50, inith=50)
                            # self.image_area = ImageArea(asset_image, f'asset_{i}.png')
                            # self.AttachUserArea(self.image_area, 3000 + i)

                            # Static text for asset name
                            self.AddStaticText(1000 + i, c4d.BFH_CENTER, name=asset_tags[0])
                            # Button to import the asset
                            self.AddButton(2000 + i, c4d.BFH_CENTER, initw=100, name="Import Asset")
                            self.GroupEnd()  # End the row group
                self.GroupEnd()  # End the inner group
            self.GroupEnd()  # End the scroll group
    
        # Button to close the dialog with some space around
        self.GroupBorderSpace(0, 10, 0, 10)  # Space before the close button
        
        # if self.GroupBegin(1, c4d.BFH_CENTER, cols=3, rows=len(assets_list)):
        #     # Add padding inside the group that holds all assets
        #     self.GroupBorderSpace(5, 5, 5, 5)  # Padding inside the group
        #     self.AddButton(300001, c4d.BFH_CENTER, name="Previous page")
        #     self.AddStaticText(1000 + i, c4d.BFH_CENTER, name=f"Curent page: {self.page + 1}")
        #     self.AddButton(300002, c4d.BFH_CENTER, name="Next page")
            
        #     self.GroupEnd()  # End the inner group
        self.AddButton(3000, c4d.BFH_CENTER, name="Close")
        self.AddMeter(100001, c4d.BFH_SCALEFIT)
        return True
    

    def ClearLayout(self):
        """Clear the current layout."""
        while self.GetLayoutElementCount() > 0:
            self.RemoveElement(0)

    def Command(self, id, msg):
        global jwt_token, state, assets_list
        if id == 3000:
            self.Close()
        if id == 300001:
            print("Previous page", max(0, self.page - 1), self.page)
            self.page = max(0, self.page - 1)
            print("Previous page", max(0, self.page - 1), self.page)
            # self.ClearLayout()
            self.CreateLayout()
            self.LayoutChanged(0)  # Rerender the layout
        if id == 300002:
            print("Next page", len(assets_list) // 12, self.page)
            self.page = min(len(assets_list) // 12, self.page + 1)    
            print("Next page", len(assets_list) // 12, self.page)
            # self.ClearLayout()
            self.CreateLayout()
            self.LayoutChanged(0)  # Rerender the layout
        elif 2000 <= id < 3000:
            index = id - 2000
            print("Import asset:", assets_list[index]['iterations'][0]['results']['obj'])
            asset_name = assets_list[index]['image_tags'][0]
            fbx_url = assets_list[index]['iterations'][0]['results']['obj']
            temp_dir = c4d.storage.GeGetStartupWritePath()  # Default write directory in C4D
            local_path = download_file(fbx_url, temp_dir, asset_name)
            import_file(local_path)
        return True

class ImageArea(gui.GeUserArea):
    def __init__(self, image_url, image_name):
        super().__init__()
        self.image_url = image_url
        self.image = bitmaps.BaseBitmap()
        self.image_path = self.download_image(self.image_url, image_name)
        self.setImage(self.image_path)

    def download_image(self, url, image_name):
        try:
            tmp_file = os.path.join(tempfile.gettempdir(), os.path.basename(image_name))
            urllib.request.urlretrieve(url, tmp_file)
            print(tmp_file)
            return tmp_file
        except Exception as e:
            print(f"Failed to download image: {e}")
            return None
        
    def setImage(self, path):
        if os.path.exists(path):
            result = self.image.InitWith(path)
            if result[0] != c4d.IMAGERESULT_OK:
                print(f"Image initialization failed with error code: {result}")
                self.image = None
            else:
                print(f"Image initialized successfully from {path}")
                self.LayoutChanged()
        else:
            print(f"Image file does not exist at: {path}")
            self.image = None

    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.DrawSetPen(c4d.COLOR_BG)
        self.DrawRectangle(x1, y1, x2, y2)
        if self.image:
            width, height = self.image.GetSize()
            if width > 0 and height > 0:
                self.DrawBitmap(self.image, x1, y1, x2 - x1, y2 - y1, 0, 0, width, height, c4d.BMP_NORMAL)
            else:
                print("Image dimensions are zero.")
        else:
            print("No image to draw.")

    def GetMinSize(self):
        if self.image:
            width, height = self.image.GetSize()
            return min(width, 50), min(height, 50)
        return 50, 50

class LoginDialog(c4d.gui.GeDialog):
    ID_DEV_ID = 1001
    ID_API_KEY = 1002
    ID_REFRESH_TOKEN = 1004
    ID_LOGIN_BUTTON = 1003
    
    
    def CreateLayout(self):
        default_dev_id, default_api_key, default_refresh_token = load_preferences()
        print( default_dev_id, default_api_key )
        self.SetTitle("Kaedim login")
        # Begin a vertical group for better structure
        self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, 2, 0, "Main Group", 0)
        self.GroupBorderSpace(10, 10, 10, 10)  # Padding around the main group content

        # Developer ID Field
        self.AddStaticText(1005, c4d.BFH_LEFT, name="Developer ID:", initw=0, inith=10)
        self.AddEditText(self.ID_DEV_ID, c4d.BFH_SCALEFIT, initw=300, inith=10)
        self.SetString(self.ID_DEV_ID, default_dev_id)
        

        # API Key Field
        self.AddStaticText(1006, c4d.BFH_LEFT, name="API Key:", initw=0, inith=10)
        self.AddEditText(self.ID_API_KEY, c4d.BFH_SCALEFIT, initw=300, inith=10)
        self.SetString(self.ID_API_KEY, default_api_key)
        
        
        # API Key Field
        self.AddStaticText(1007, c4d.BFH_LEFT, name="Refresh Token:", initw=0, inith=10)
        self.AddEditText(self.ID_REFRESH_TOKEN, c4d.BFH_SCALEFIT, initw=300, inith=10)
        self.SetString(self.ID_REFRESH_TOKEN, default_refresh_token)
        
        
        self.GroupEnd()  # End the vertical group

        # Button to login with some space around it
        self.GroupBorderSpace(10, 20, 10, 10)  # Space around the login button
        self.AddButton(self.ID_LOGIN_BUTTON, c4d.BFH_CENTER, initw=100, name="Login")
        self.AddMeter(100002, c4d.BFH_SCALEFIT)
        
        return True
   
    def Command(self, id, msg):
        if id == self.ID_LOGIN_BUTTON:
            dev_id = self.GetString(self.ID_DEV_ID)
            api_key = self.GetString(self.ID_API_KEY)
            refresh_token = self.GetString(self.ID_REFRESH_TOKEN)
            self.login(dev_id, api_key, refresh_token)
        return True
    
    def login(self, dev_id, api_key, refresh_token):
        global jwt_token, state
        # Mockup for the login function, replace with actual API login code
        if dev_id and api_key and refresh_token:
            print(f"Logging in with Developer ID: {dev_id} and API Key: {api_key}")
        else:
            print("Developer ID, API Key and Refresh Token cannot be empty.")
        
        url = f"{API_DOMAIN}api/v1/registerHook"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        body = {
            'devID': dev_id,
            'destination': 'test'
        }
        try:
            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()
            jwt_token = response.json()['jwt']
            state = 'logged_in'
            print('Login successful, JWT retrieved.')
            save_preferences(dev_id, api_key, refresh_token)
            self.load_assets()
        except requests.RequestException as e:
            c4d.gui.MessageDialog("Failed to login: Invalid credentials")

        return True

    def load_assets(self):
        global jwt_token, assets_list
        assets_fetched = False
        if jwt_token:
           assets_fetched, assets_list = fetch_assets()
           if not assets_fetched:
               refresh_jwt()
               assets_fetched, assets_list = fetch_assets()
        
        if assets_fetched:
            
            self.Close()
            dlg = FloatingPanel()
            dlg.Open(dlgtype=c4d.DLG_TYPE_ASYNC, defaultw=400, defaulth=300)
        else:
            c4d.gui.MessageDialog("Failed to login: Invalid credentials")
            