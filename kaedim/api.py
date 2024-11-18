import c4d
import os
import sys

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

def load_preferences():
    prefs = c4d.plugins.GetWorldPluginData(c4d.PLUGINTYPE_PREFS)
    if prefs:
        dev_id = prefs.GetString(101, "")
        api_key = prefs.GetString(102, "")
        refresh_token = prefs.GetString(103, "")
        return dev_id, api_key, refresh_token
    return "", "", ""


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
    dev_id, api_key, _ = load_preferences()
    if state != 'logged_in':
        print("Not logged in. Cannot fetch assets.")
        return False, []

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
        assets_list_with_iterations = [asset for asset in all_assets if asset['iterations'] is not None and len(asset['iterations']) > 0 ]
        # c4d.gui.MessageDialog(assets_list_with_iterations[0]['iterations'][0]['status'])
        #why just the first iteration? Shouldn't it be the most recent one?
        assets_list = [asset for asset in assets_list_with_iterations if asset['iterations'][-1]['status'] in ('completed', 'approved')]
        return True, assets_list
        
    except requests.RequestException as e:
        print("Error fetching assets:", e)
        return False, []
