from .common import *


def list_trash() -> list:
    """retrieves top-level trash list"""
    return BackOffRequest.paginated_get(get_metadata_url() + 'trash')


def move_to_trash(node_id: str) -> dict:
    r = BackOffRequest.put(get_metadata_url() + 'trash/' + node_id)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


def restore(node_id: str) -> dict:
    r = BackOffRequest.post(get_metadata_url() + 'trash/' + node_id + '/restore')
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


# {"message":"Insufficient permissions granted for operation: purgeNode"}
def purge(node_id: str) -> dict:
    r = BackOffRequest.delete(get_metadata_url() + 'nodes/' + node_id)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()