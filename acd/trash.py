import requests
import http.client as http

from acd import oauth
from acd.common import *


# retrieves top-level trash list
def list_trash():
    return paginated_get_request(oauth.get_metadata_url() + 'trash')


def move_to_trash(node):
    r = requests.put(oauth.get_metadata_url() + 'trash/' + node, headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()


# TODO: handle 409
def restore(node):
    r = requests.post(oauth.get_metadata_url() + 'trash/' + node + '/restore', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()


# {"message":"Insufficient permissions granted for operation: purgeNode"}
def purge(node):
    r = requests.delete(oauth.get_metadata_url() + 'nodes/' + node, headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()