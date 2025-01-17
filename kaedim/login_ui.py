import c4d
import os
import sys
from c4d import gui, bitmaps
import urllib.request
import tempfile
from kaedim.api import refresh_jwt, fetch_assets, load_preferences
import math
import threading
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




def save_preferences(dev_id, api_key, refresh_token, studio_id):
    prefs = c4d.plugins.GetWorldPluginData(c4d.PLUGINTYPE_PREFS)
    if not prefs:
        prefs = c4d.BaseContainer()
    prefs.SetString(101, dev_id)
    prefs.SetString(102, api_key)
    prefs.SetString(103, refresh_token)
    prefs.SetString(104, studio_id)
    c4d.plugins.SetWorldPluginData(c4d.PLUGINTYPE_PREFS, prefs)

def calculate_hierarchy_bounding_box(obj):
    """
    Recursively calculates the bounding box of an object and its children.
    """
    if obj.GetType() == c4d.Onull:
        children = obj.GetChildren()
        if not children:
            return None
        
        bbox_min = c4d.Vector(float('inf'), float('inf'), float('inf'))
        bbox_max = c4d.Vector(float('-inf'), float('-inf'), float('-inf'))
        
        for child in children:
            child_bbox = calculate_hierarchy_bounding_box(child)
            if child_bbox:
                child_min, child_max = child_bbox
                bbox_min = c4d.Vector(
                    min(bbox_min.x, child_min.x),
                    min(bbox_min.y, child_min.y),
                    min(bbox_min.z, child_min.z)
                )
                bbox_max = c4d.Vector(
                    max(bbox_max.x, child_max.x),
                    max(bbox_max.y, child_max.y),
                    max(bbox_max.z, child_max.z)
                )
        return bbox_min, bbox_max
    else:
        bbox_min = obj.GetAbsPos() - obj.GetRad()
        bbox_max = obj.GetAbsPos() + obj.GetRad()
        return bbox_min, bbox_max
    
def scale_hierarchy(obj, scale_factor=1000.0):
    """
    Scales an object and its children based on the maximum dimension of the hierarchy.
    """
    bbox = calculate_hierarchy_bounding_box(obj)
    if not bbox:
        print(f"Skipping scaling for {obj.GetName()}: No bounding box found.")
        return

    bbox_min, bbox_max = bbox
    hierarchy_size = bbox_max - bbox_min
    max_dimension = max(hierarchy_size.x, hierarchy_size.y, hierarchy_size.z)

    if max_dimension == 0:
        print(f"Skipping scaling for {obj.GetName()}: Maximum dimension is zero.")
        return

    scale_ratio = scale_factor / max_dimension
    scale_vector = c4d.Vector(scale_ratio, scale_ratio, scale_ratio)
    obj.SetAbsScale(scale_vector)
    print(f"Scaled {obj.GetName()} with scale ratio {scale_ratio:.2f}")

class TextArea(gui.GeUserArea):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def DrawMsg(self, x1, y1, x2, y2, msg):
        self.DrawSetTextCol(c4d.COLOR_TEXT)
        self.DrawSetFont(c4d.FONT_BOLD)
        self.DrawText(self.text, x1, y1)

    def GetMinSize(self):
        return 100, 15  # Adjust as needed
    


    

class CustomGroup(c4d.gui.SubDialog):
    """A SubDialog to display the passed string, its used as example for the actual content of a Tab"""
    def __init__(self,page_no, assets):
        super().__init__()
        self.page_no = page_no
        self.assets = assets
        self.image_area = []
       

    def CreateLayout(self):
        print(f"page no fromdialog class {self.page_no}")
        # global assets_list
        start_index = self.page_no * 12
        end_index = min(start_index + 12, len(self.assets))
        
        self.image_area.clear()
        
        if self.GroupBegin(8888,c4d.BFH_CENTER,cols=3,rows=1):
            self.GroupSpace(0,15)
            for i in range(start_index,end_index):
                asset = self.assets[i]
                asset_id = asset['requestID']
                asset_tags = asset['image_tags']
                asset_image = asset['image'][0]
                status = asset['iterations'][0]['status']
                if asset_tags:
                    if self.GroupBegin(10000 + i, c4d.BFH_LEFT, cols=1, rows=3):
                        self.GroupBorderSpace(10, 5, 10, 5)
                        self.GroupSpace(5,10)


                
                        
                        self.GroupBegin(20000 + i, c4d.BFH_CENTER, cols=1, rows=1)
                        self.AddUserArea(7000 + i, c4d.BFH_CENTER, initw=50, inith=50)
                        self.image_area.append(ImageArea(asset_image, f'asset_{asset_id}.png'))
                        imagearea_index = len(self.image_area) - 1
                        self.AttachUserArea(self.image_area[imagearea_index], 7000 + i)
                        self.GroupEnd()

                        
                        text_width = 100
                        if(len(asset_tags[0])<=6):
                            text_width = 50
                        elif(len(asset_tags[0])>6 and len(asset_tags[0])<10):
                            text_width =90

                        self.GroupBegin(30000 + i, c4d.BFH_CENTER, cols=1,)

                        self.AddStaticText(1000 + i, c4d.BFH_CENTER,initw=text_width, name=asset_tags[0])
                        self.GroupEnd()
                       

                        

                        # self.GroupBegin(40000 + i, c4d.BFH_RIGHT, cols=1, rows=1)
                        self.AddButton(2000 + i, c4d.BFH_CENTER, initw=100, name="Import Asset")
                        # self.GroupEnd()


                        self.GroupEnd()
            self.GroupEnd()
        return True
    

    def Command(self, id, msg):
        if 2000 <= id < 3000:
            index = id - 2000
            asset_name = self.assets[index]['image_tags'][0]
            fbx_url = self.assets[index]['iterations'][0]['results']['obj']
            temp_dir = c4d.storage.GeGetStartupWritePath()
            threading.Thread(target=self.download_and_import, args=(fbx_url, temp_dir, asset_name)).start()
        return True

    def download_and_import(self, fbx_url, temp_dir, asset_name):
        local_path = download_file(fbx_url, temp_dir, asset_name)
        import_file(local_path)
    
    
    
class FloatingPanel(c4d.gui.GeDialog):
    """Custom dialog to display assets."""
    def __init__(self):
        super().__init__()
        self.page = 0
        self.assets_per_page = 12  
        self.custom_group_list = []
        self.search_query = ""
        self.filtered_assets = assets_list
        self.cg1= CustomGroup(self.page,self.filtered_assets)
        self.custom_group_list.append(self.cg1)
        self.progress_value = 0
        threading.Thread(target=self.download_next_pages, args=(len(self.filtered_assets) // self.assets_per_page,)).start()
    
    def CreateLayout(self):

        global assets_list
        
       
        self.SetTitle("Kaedim Asset List")
        # Begin a scrollable group with a specified size limit and padding
        if self.ScrollGroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, scrollflags=c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_HORIZ, initw=400, inith=350):
            # Add padding around the scroll group content
            self.GroupBorderSpace(10, 10, 10, 10)  # Add padding around the entire list
            
            if self.GroupBegin(1, c4d.BFH_SCALEFIT, cols=1, rows=1,groupflags=c4d.BFV_CMD_EQUALCOLUMNS):

                # Add padding inside the group that holds all assets
                self.GroupBorderSpace(5, 5, 5, 5)  # Padding inside the group

                self.AddEditText(4000, c4d.BFH_SCALEFIT, initw=300, inith=10)
                self.AddButton(4001, c4d.BFH_CENTER, initw=100, name="Search")
                

   
                self.AddSubDialog(1234, c4d.BFH_SCALE | c4d.BFV_SCALEFIT, 100, 100)
                self.AttachSubDialog(self.cg1, 1234)

               
                self.GroupEnd()
            self.GroupEnd()  # End the scroll group
    
        # Button to close the dialog with some space around
        self.GroupBegin(2, c4d.BFH_CENTER, cols=4, rows=1)
        self.GroupBorderSpace(0, 10, 0, 10)  # Space before the close button
        self.GroupSpace(40,0)
        

        self.AddButton(3001, c4d.BFH_CENTER, name="Previous")

        self.AddButton(3000, c4d.BFH_CENTER, name="Close")

        self.AddButton(3002, c4d.BFH_CENTER, name="Next")

        self.GroupEnd()
 
       
        return True
    

    

    def ClearLayout(self):
        while self.GetLayoutElementCount() > 0:
            self.RemoveElement(0)

    def Command(self, id, msg):
        global jwt_token, state, assets_list
        if id == 4001:  # Search button
            self.progress_value = 0
            self.update_status_bar("Loading...")
            self.search_query = self.GetString(4000)
            self.filtered_assets = self.filter_assets(self.search_query)
            self.page = 0
            self.update_assets_display()
            self.update_status_bar("Loading complete", value=100)
            # self.hide_loading_popup()
        if id == 3000:
            self.Close()
        elif id == 3001:
            if self.page > 0:
                self.page -= 1
                self.updateSubDialog()
        elif id == 3002:
            self.progress_value = 0
            self.update_status_bar("Loading...")
            if (self.page + 1) * self.assets_per_page < len(assets_list):
                self.page += 1
                self.updateSubDialog()
            self.update_status_bar("Loading complete", value=100)
        
        return True
    
    def update_status_bar(self, message, value=None):
        """Update the status bar (meter) value and optionally print a message."""
        if value is not None:
            self.progress_value = value
        self.SetMeter(100001, self.progress_value)
        c4d.StatusSetText(message)
        c4d.EventAdd()
    
    def updateSubDialog(self):
        global assets_list

        self.custom_group_list.append(CustomGroup(self.page,assets_list))

        self.AttachSubDialog(self.custom_group_list[self.page], 1234)
        self.LayoutChanged(1234)


    def download_next_pages(self, pages = 0):
        global assets_list

        # This method will run in a separate thread to download images for a specific page
        next_pages = [self.page + i for i in range(1, pages + 1)]

        for page in next_pages:
            if page * self.assets_per_page < len(assets_list):
                self.download_images(page)
    
    def download_images(self, page):
        global assets_list

        start_index = page * self.assets_per_page
        end_index = start_index + self.assets_per_page
        for asset in assets_list[start_index:end_index]:
            asset_id = asset['requestID']
            asset_image = asset['image'][0]
            print(f"Downloading image for asset: {asset_id}")
            download_image(asset_image, f'asset_{asset_id}.png')


    def filter_assets(self, query):
        if not query:
            return assets_list
        query = query.lower()
        return [asset for asset in assets_list if query in asset['image_tags'][0].lower()]
    

    def update_assets_display(self):
        # self.RemoveSubDialog(1234)
        self.cg1 = CustomGroup(self.page, self.filtered_assets)
        self.custom_group_list.append(self.cg1)
        self.AttachSubDialog(self.cg1, 1234)
        self.LayoutChanged(1234)

        
        
def download_image(url, image_name):
    try:
        tmp_file = os.path.join(tempfile.gettempdir(), os.path.basename(image_name))
        if os.path.exists(tmp_file):
            print(f"Image already exists at: {tmp_file}")
            return tmp_file
        urllib.request.urlretrieve(url, tmp_file)
        print(f"Downloaded image to: {tmp_file}")
        return tmp_file
    except Exception as e:
        print(f"Failed to download image: {e}")
        return None    


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
            if os.path.exists(tmp_file):
                print(f"Image already exists at: {tmp_file}")
                return tmp_file
            urllib.request.urlretrieve(url, tmp_file)
            print(f"Downloaded image to: {tmp_file}")
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
                draw_width, draw_height = self.calculate_aspect_ratio(width, height, x2 - x1, y2 - y1)
                offset_x = (x2 - x1 - draw_width) // 2
                offset_y = (y2 - y1 - draw_height) // 2
                self.DrawBitmap(self.image, x1 + offset_x, y1 + offset_y, draw_width, draw_height, 0, 0, width, height, c4d.BMP_ALLOWALPHA)
            else:
                print("Image dimensions are zero.")
        else:
            print("No image to draw.")

    def calculate_aspect_ratio(self, img_width, img_height, max_width, max_height):
        aspect_ratio = img_width / img_height
        if max_width / aspect_ratio <= max_height:
            return max_width, int(max_width / aspect_ratio)
        else:
            return int(max_height * aspect_ratio), max_height

    def GetMinSize(self):
        if self.image:
            width, height = self.image.GetSize()
            return min(width, 50), min(height, 50)
        return 50, 50
    


def import_file(filepath):
    doc = c4d.documents.GetActiveDocument()
    if filepath.endswith('.obj'):
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import OBJ file.")
    elif filepath.endswith('.c4d'):
        result = c4d.documents.LoadFile(filepath)
        if not result:
            c4d.gui.MessageDialog("Failed to import C4D file.")
    elif filepath.endswith('.fbx'):
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import FBX file.")
    elif filepath.endswith('.glb') or filepath.endswith('.gltf'):
        result = c4d.documents.MergeDocument(doc, filepath, c4d.SCENEFILTER_OBJECTS)
        if not result:
            c4d.gui.MessageDialog("Failed to import GLB/GLTF file.")
    else:
        c4d.gui.MessageDialog("Unsupported file format.")
        return
    
    obj = doc.GetFirstObject()
    if not obj:
        c4d.gui.MessageDialog("No object imported.")
        return

    scale_hierarchy(obj, scale_factor=1000.0)

    c4d.EventAdd()

def download_file(url, dest_folder, name):
    local_filename = os.path.join(dest_folder, f'{name}.obj')
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename

class LoginDialog(c4d.gui.GeDialog):
    ID_DEV_ID = 1001
    ID_API_KEY = 1002
    ID_REFRESH_TOKEN = 1004
    ID_LOGIN_BUTTON = 1003
    ID_STUDIO_ID = 1008
    
    
    def CreateLayout(self):
        default_dev_id, default_api_key, default_refresh_token, default_studio_id = load_preferences()
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

        # Studio ID Field
        self.AddStaticText(1009, c4d.BFH_LEFT, name="Studio ID:", initw=0, inith=10)
        self.AddEditText(self.ID_STUDIO_ID, c4d.BFH_SCALEFIT, initw=300, inith=10)
        self.SetString(self.ID_STUDIO_ID, default_studio_id)
        
        
        self.GroupEnd()  # End the vertical group

        # Button to login with some space around it
        self.GroupBorderSpace(10, 20, 10, 10)  # Space around the login button
        self.AddButton(self.ID_LOGIN_BUTTON, c4d.BFH_CENTER, initw=100, name="Login")
        
        return True
   
    def Command(self, id, msg):
        if id == self.ID_LOGIN_BUTTON:
            dev_id = self.GetString(self.ID_DEV_ID)
            api_key = self.GetString(self.ID_API_KEY)
            refresh_token = self.GetString(self.ID_REFRESH_TOKEN)
            studio_id = self.GetString(self.ID_STUDIO_ID)
            self.login(dev_id, api_key, refresh_token, studio_id)
        return True
    
    def login(self, dev_id, api_key, refresh_token, studio_id):
        global jwt_token, state
        # Mockup for the login function, replace with actual API login code
        # Mockup for the login function, replace with actual API login code
        if dev_id and api_key and refresh_token:
            print(f"Logging in with Developer ID: {dev_id} and API Key: {api_key}")
        else:
            print("Developer ID, API Key and Refresh Token cannot be empty.")
        
        try:
            jwt_token, state = refresh_jwt()
            print('Login successful, JWT retrieved.')
            save_preferences(dev_id, api_key, refresh_token, studio_id)
            self.load_assets()
        except requests.RequestException as e:
            c4d.gui.MessageDialog("Failed to login: Invalid credentials")

        return True

    def load_assets(self):
        global jwt_token, state, assets_list, dlg
        assets_fetched = False
        if jwt_token:
           assets_fetched, assets_list = fetch_assets(jwt_token, state)
           if not assets_fetched:
               jwt_token, state = refresh_jwt()
               assets_fetched, assets_list = fetch_assets(jwt_token, state)
        
        if assets_fetched:
            
            self.Close()
            dlg = FloatingPanel()
            dlg.Open(dlgtype=c4d.DLG_TYPE_ASYNC, defaultw=400, defaulth=300)
        else:
            c4d.gui.MessageDialog("Failed to login: Invalid credentials")


if __name__ == '__main__':
    global diag

    diag = FloatingPanel()
    diag.Open(c4d.DLG_TYPE_ASYNC, defaultw=100, defaulth=100)
    c4d.EventAdd()
            
