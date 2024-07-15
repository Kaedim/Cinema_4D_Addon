import c4d
import os
import sys
from c4d import gui, bitmaps, plugins
import urllib.request
import json
import tempfile
import shutil

# Add paths for plugin
PLUGIN_DIRECTORY = os.path.dirname(__file__)
CODE_DIRECTORY = os.path.join(PLUGIN_DIRECTORY, 'kaedim')
DEPENDENCIES_PATH = os.path.join(PLUGIN_DIRECTORY, 'libs')
if not PLUGIN_DIRECTORY in sys.path:
    sys.path.insert(0, PLUGIN_DIRECTORY)

if not CODE_DIRECTORY in sys.path:
    sys.path.insert(0, CODE_DIRECTORY)

if not DEPENDENCIES_PATH in sys.path:
    sys.path.insert(0, DEPENDENCIES_PATH)


from kaedim.api import refresh_jwt, fetch_assets, load_preferences
from kaedim.login_ui import LoginDialog


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
