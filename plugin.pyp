import c4d
import os
import sys
import json
from c4d import plugins

PLUGIN_ID = 1300021  # Use a unique ID for your plugin. Obtain one from Maxon to avoid conflicts.


# Path to the directory where the plugin is located
plugin_dir = os.path.dirname(__file__)
libs_path = os.path.join(plugin_dir, 'libs')
sys.path.append(libs_path)

# Now import requests
import requests

# Configuration Constants
API_DOMAIN = "https://api.kaedim3d.com/"
DEV_ID = "cd8d8f0d-6240-4c42-84c5-01d90220d111"
API_KEY = "009e8cec650d002aebf0fd389665b9fa989e9564"

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

def load_preferences():
    prefs = c4d.plugins.GetWorldPluginData(c4d.PLUGINTYPE_PREFS)
    if prefs:
        dev_id = prefs.GetString(101, "")
        api_key = prefs.GetString(102, "")
        refresh_token = prefs.GetString(103, "")
        return dev_id, api_key, refresh_token
    return "", "", ""



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

    # Refresh Cinema 4D to update the scene
    c4d.EventAdd()

def download_file(url, dest_folder, name):
    local_filename = os.path.join(dest_folder, f'{name}.obj')
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename


def refresh_jwt():
    global jwt_token, state
    dev_id, api_key, refresh_token = load_preferences()
    # Mockup for the login function, replace with actual API login code
    if dev_id and api_key:
        print(f"Logging in with Developer ID: {dev_id} and API Key: {api_key}")
    else:
        print("Developer ID and API Key cannot be empty.")
    
    url = f"{API_DOMAIN}api/v1/refreshJWT"
    headers = {
        "Content-Type": "application/json",
        "refresh-token": refresh_token,
        "X-API-Key": api_key
    }
    body = {
        'devID': dev_id,
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        jwt_token = response.json()['jwt']
        state = 'logged_in'
        print('Login successful, JWT retrieved.')
    except requests.RequestException as e:
        print('Failed to login')

    return True

def fetch_assets():
    """Fetches asset metadata from the API and filters based on specific criteria."""
    global jwt_token, state, assets_list
    dev_id, api_key, refresh_token = load_preferences()
    if state != 'logged_in':
        print("Not logged in. Cannot fetch assets.")
        return

    url = f"{API_DOMAIN}api/v1/fetchAll"
    headers = {
        "X-API-Key": api_key,
        "Authorization": f"Bearer {jwt_token}"
    }
    body = {
        'devID': dev_id,
    }

    try:
        response = requests.get(url, headers=headers, json=body)
        response.raise_for_status()
        all_assets = response.json()['assets']
        print(all_assets) # For some reasong if this gets removes the assets are not saved
        # Filter assets where the first iteration's status is not dismissed or cancelled
        assets_list_with_iterations = [asset for asset in all_assets if asset['iterations'] is not None and len(asset['iterations']) > 0 ]
        assets_list = [asset for asset in assets_list_with_iterations if asset['iterations'][0]['status'] not in ('dismissed', 'cancelled')]
        return True
        
    except requests.RequestException as e:
        print("Error fetching assets:", e)
        return False


class FloatingPanel(c4d.gui.GeDialog):
    """Custom dialog to display assets."""
                
    def CreateLayout(self):
        self.SetTitle("Kaedim Asset List")
    
        # Begin a scrollable group with a specified size limit and padding
        if self.ScrollGroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT, scrollflags=c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_HORIZ, initw=400, inith=300):
            # Add padding around the scroll group content
            self.GroupBorderSpace(10, 10, 10, 10)  # Add padding around the entire list
            
            if self.GroupBegin(1, c4d.BFH_SCALEFIT, cols=1, rows=len(assets_list)):
                # Add padding inside the group that holds all assets
                self.GroupBorderSpace(5, 5, 5, 5)  # Padding inside the group
    
                for i, asset in enumerate(assets_list):
                    asset_tags = asset['image_tags']
                    status = asset['iterations'][0]['status']
                    if asset_tags:
                        # Begin a group for each asset (row) with two columns: one for the label, one for the button
                        if self.GroupBegin(10000 + i, c4d.BFH_SCALEFIT, cols=2, rows=1):
                            # Adding space around each row
                            self.GroupBorderSpace(10, 5, 10, 5)  # Padding around each asset row
                            
                            # Static text for asset name
                            self.AddStaticText(1000 + i, c4d.BFH_LEFT, initw=250, name=asset_tags[0])
                            # Button to import the asset
                            self.AddButton(2000 + i, c4d.BFH_RIGHT, initw=100, name="Import Asset")
                            self.GroupEnd()  # End the row group
                self.GroupEnd()  # End the inner group
            self.GroupEnd()  # End the scroll group
    
        # Button to close the dialog with some space around
        self.GroupBorderSpace(0, 10, 0, 10)  # Space before the close button
        self.AddButton(3000, c4d.BFH_CENTER, name="Close")
        return True
    

    def Command(self, id, msg):
        global jwt_token, state, DEV_ID, API_KEY, assets_list
        if id == 3000:
            self.Close()
        elif 2000 <= id < 3000:
            index = id - 2000
            print("Import asset:", assets_list[index]['iterations'][0]['results']['obj'])
            asset_name = assets_list[index]['image_tags'][0]
            fbx_url = assets_list[index]['iterations'][0]['results']['obj']
            temp_dir = c4d.storage.GeGetStartupWritePath()  # Default write directory in C4D
            local_path = download_file(fbx_url, temp_dir, asset_name)
            import_file(local_path)
        return True


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
        assets_fetched = False
        if jwt_token:
           assets_fetched = fetch_assets()
           if not assets_fetched:
               refresh_jwt()
               assets_fetched = fetch_assets()
        
        if assets_fetched:
            
            self.Close()
            dlg = FloatingPanel()
            dlg.Open(dlgtype=c4d.DLG_TYPE_ASYNC, defaultw=400, defaulth=300)
        else:
            c4d.gui.MessageDialog("Failed to login: Invalid credentials")
            

class MyPlugin(plugins.CommandData):
    def Execute(self, doc):
        dlg = LoginDialog()
        dlg.Open(c4d.DLG_TYPE_ASYNC, defaultw=300, defaulth=100)
        return True

    def RestoreLayout(self, sec_ref):
        dlg = LoginDialog()
        return dlg.Restore(PLUGIN_ID, 0, sec_ref)

if __name__ == "__main__":
    plugin = plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str="Kadim Plugin",
        info=0,
        icon=None,
        help="Kaedims import asset plugin",
        dat=MyPlugin()
    )
