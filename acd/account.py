import http.client as http
import requests
import json

from acd import oauth
from acd.common import RequestError


def get_account_usage():
    r = requests.get(oauth.get_metadata_url() + 'account/usage', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()


def get_quota():
    r = requests.get(oauth.get_metadata_url() + 'account/quota', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)
    return r.json()
