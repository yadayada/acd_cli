import http.client as http
import json

import requests

from acd.common import *
import acd.oauth as oauth


# additional parameters are: tempLink='true'
def get_node_list(**params):
    q_params = {}
    for param in params.keys():
        q_params[param] = params[param]

    return paginated_get_request(oauth.get_metadata_url() + 'nodes', q_params, {})


def get_file_list():
    return get_node_list(filters='kind:FILE')


def get_folder_list():
    return get_node_list(filters='kind:FOLDER')


def get_asset_list():
    return get_node_list(filters='kind:ASSET')


def get_trashed_folders():
    return get_node_list(filters='status:TRASH AND kind:FOLDER')


def get_trashed_files():
    return get_node_list(filters='status:TRASH AND kind:FILE')


def get_metadata(node_id):
    params = {'tempLink': 'true'}
    r = requests.get(oauth.get_metadata_url() + 'nodes/' + node_id, headers=oauth.get_auth_header(), params=params)
    if r.status_code != http.OK:
        return RequestError(r.status_code, r.text)
    return r.json()


# this will increment the node's version attribute
def update_metadata(node_id, properties):
    body = json.dumps(properties)
    r = requests.patch(oauth.get_metadata_url() + 'nodes/' + node_id, headers=oauth.get_auth_header(), data=body)
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()


# necessary?
def get_root_id():
    params = {'filters': 'isRoot:true'}
    r = requests.get(oauth.get_metadata_url() + 'nodes', headers=oauth.get_auth_header(), params=params)

    if r.status_code != http.OK:
        return RequestError(r.status_code, r.text)

    data = r.json()

    if 'id' in data['data'][0]:
        return data['data'][0]['id']


def add_child(parent, child):
    r = requests.put(oauth.get_metadata_url()
                     + 'nodes/' + parent + '/children/' + child, headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        print('Adding child failed.')
        raise RequestError(r.status_code, r.text)
    return r.json()


def remove_child(parent, child):
    r = requests.delete(oauth.get_metadata_url()
                        + 'nodes/' + parent + "/children/" + child, headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        print('Removing child failed.')
        raise RequestError(r.status_code, r.text)
    return r.json()


# preferable to adding child to new parent and removing child from old parent
# undocumented API feature
def move_node(child, new_parent):
    properties = {'parents': [new_parent]}
    return update_metadata(child, properties)


def rename_node(node_id, new_name):
    properties = {'name': new_name}
    return update_metadata(node_id, properties)


# sets node with 'PENDING' status to 'AVAILABLE'
def set_available(node_id):
    properties = {'status': 'AVAILABLE'}
    return update_metadata(node_id, properties)