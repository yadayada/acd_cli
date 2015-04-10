import time
import json
from urllib.parse import urlparse, parse_qs
import os
import requests


CONN_DATA_FILE = 'conn_data'
CLIENT_DATA_FILE = 'client_data'

conn_data = {}

get_metadata_url = lambda: conn_data['endpoints']['metadataUrl']
get_content_url = lambda: conn_data['endpoints']['contentUrl']

with open(CLIENT_DATA_FILE) as f:
    cd = json.load(f)
    CLIENT_ID = cd['CLIENT_ID']
    CLIENT_SECRET = cd['CLIENT_SECRET']

    if CLIENT_ID == '' or CLIENT_SECRET == '':
        print('Please enter the security profile\'s client data in %s.' % CLIENT_DATA_FILE)
        exit()

AMAZON_OA_LOGIN_URL = 'https://amazon.com/ap/oa'
AMAZON_OA_TOKEN_URL = 'https://api.amazon.com/auth/o2/token'
REDIRECT_URI = 'http://localhost'

OAUTH_ST1 = {'client_id': CLIENT_ID,
             'response_type': 'code',
             'scope': 'clouddrive:read clouddrive:write',
             'redirect_uri': REDIRECT_URI}

OAUTH_ST2 = {'grant_type': 'authorization_code',
             'code': None,
             'client_id': CLIENT_ID,
             'client_secret': CLIENT_SECRET,
             'redirect_uri': REDIRECT_URI}

OAUTH_REF = {'grant_type': 'refresh_token',
             'refresh_token': None,
             'client_id': CLIENT_ID,
             'client_secret': CLIENT_SECRET,
             'redirect_uri': REDIRECT_URI}

AMZ_ENDPOINT_REQ_URL = 'https://drive.amazonaws.com/drive/v1/account/endpoint'
ENDPOINT_VAL_TIME = 259200


# noinspection PyDictCreation
def get_data():
    """ Loads stored conn data from file or starts OA procedure """
    global conn_data
    changed = False

    if os.path.isfile(CONN_DATA_FILE):
        with open(CONN_DATA_FILE) as infile:
            try:
                conn_data = json.load(infile)
                get_auth_token()  # refresh, if necessary
                if time.time() > conn_data['endpoints']['expTime']:
                    conn_data['endpoints'] = get_endpoints()
                    changed = True
            except TypeError:
                print("Error loading user data.")
            except ValueError:
                print('Missing key in user data file.')

    if not conn_data:
        conn_data = {}
        conn_data['token'] = authenticate()
        conn_data['endpoints'] = get_endpoints()
        changed = True

    if changed:
        on_user_data_changed()

    return


def on_user_data_changed():
    with open(CONN_DATA_FILE, 'w') as outfile:
        json.dump(conn_data, outfile, indent=4)


def authenticate():
    response = requests.post(AMAZON_OA_LOGIN_URL, params=OAUTH_ST1, allow_redirects=True)

    print('Please visit %s' % response.url)

    ret_url = input("Please enter the url you have been redirected to: ")
    ret_q = parse_qs(urlparse(ret_url).query)

    if ret_q['scope'][0] != OAUTH_ST1['scope']:
        print('Scope mismatch.')

    OAUTH_ST2['code'] = ret_q['code'][0]

    curr_time = time.time()
    response = requests.post(AMAZON_OA_TOKEN_URL, data=OAUTH_ST2)
    try:
        r = response.json()
    except ValueError as e:
        print('Invalid JSON.')
        raise e

    treat_auth_token(r, curr_time)

    return r


def get_auth_header():
    return {'Authorization': get_auth_token()}


def get_auth_token():
    if time.time() > conn_data['token']['expTime']:
        refresh_auth_token()
        on_user_data_changed()
    return conn_data['token']['auth_token']


def get_endpoints():
    params = {"Authorization": get_auth_token()}
    r = requests.get(AMZ_ENDPOINT_REQ_URL, headers=params)

    try:
        e = r.json()
        e['expTime'] = time.time() + ENDPOINT_VAL_TIME
    except ValueError as e:
        print('Invalid JSON.')
        raise e

    return e


def treat_auth_token(token, curr_time):
    if not token:
        return
    try:
        token['expTime'] = curr_time + token['expires_in'] - 60
        token['auth_token'] = "Bearer " + token['access_token']
    except KeyError as e:
        print('Fatal error: Token key not found.')
        raise e


def refresh_auth_token():
    print('Refreshing authentication token.')

    OAUTH_REF['refresh_token'] = conn_data['token']['refresh_token']
    t = time.time()
    response = requests.post(AMAZON_OA_TOKEN_URL, data=OAUTH_REF)
    try:
        r = response.json()
    except ValueError as e:
        print('Refresh error: Invalid JSON.')
        raise e

    treat_auth_token(r, t)

    conn_data['token'] = r

    return r