import requests
import http.client as http
import json

from acd import oauth
from acd.common import RequestError


def get_changes():
    r = requests.post(oauth.get_metadata_url() + 'changes', headers=oauth.get_auth_header())
    if r.status_code != http.OK:
        raise RequestError(r.status_code, r.text)

    # return format: '{}\n{"end": true|false}'
    # TODO: check end

    ro = str.splitlines(r.text)
    return json.loads(ro[0])