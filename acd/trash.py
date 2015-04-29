from acd.common import *


# retrieves top-level trash list
def list_trash():
    return paginated_get_request(get_metadata_url() + 'trash')


def move_to_trash(node):
    r = BackOffRequest.put(get_metadata_url() + 'trash/' + node)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


def restore(node):
    r = BackOffRequest.post(get_metadata_url() + 'trash/' + node + '/restore')
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


# {"message":"Insufficient permissions granted for operation: purgeNode"}
def purge(node):
    r = BackOffRequest.delete(get_metadata_url() + 'nodes/' + node)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()