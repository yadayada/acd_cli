import http.client as http
import requests

from acd import oauth


class RequestError(Exception):
    def __init__(self, status_code, msg):
        self.status_code = status_code
        self.msg = msg

    def __str__(self):
        return str(self.status_code) + '\n' + self.msg


def paginated_get_request(url, params={}, headers={}):
    node_list = []

    while True:
        r = requests.get(url, params=params,
                         headers=dict(headers, **oauth.get_auth_header()))
        if r.status_code != http.OK:
            print("Error getting node list.")
            raise RequestError(r.text)
        ret = r.json()
        node_list.extend(ret['data'])
        if 'nextToken' in ret.keys():
            params['startToken'] = ret['nextToken']
        else:
            if ret['count'] != node_list.__len__():
                print('Expected %i items, got %i.' % ret['count'], node_list.__len__())
            break

    return node_list