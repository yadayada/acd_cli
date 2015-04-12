import http.client as http
import requests

from acd import oauth


class RequestError(Exception):
    def __init__(self, status_code, msg):
        self.status_code = status_code
        if msg:
            self.msg = msg
        else:
            self.msg = '{"message": "[acd_cli] no body received."}'

    def __str__(self):
        return 'RequestError: ' + str(self.status_code) + ', ' + self.msg


def paginated_get_request(url, params=None, headers=None):
    if params is None:
        params = {}
    if headers is None:
        headers = {}
    node_list = []

    while True:
        r = requests.get(url, params=params,
                         headers=dict(headers, **oauth.get_auth_header()))
        if r.status_code != http.OK:
            print("Error getting node list.")
            raise RequestError(r.status_code, r.text)
        ret = r.json()
        node_list.extend(ret['data'])
        if 'nextToken' in ret.keys():
            params['startToken'] = ret['nextToken']
        else:
            if ret['count'] != len(node_list):
                print('Expected {} items, received {}.'.format(ret['count'], len(node_list)))
            break

    return node_list