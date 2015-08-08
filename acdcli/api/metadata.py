import json
import logging
import http.client as http
from collections import namedtuple

from .common import *

logger = logging.getLogger(__name__)


# additional parameters are: tempLink='true'
def get_node_list(**params) -> list:
    return BackOffRequest.paginated_get(get_metadata_url() + 'nodes', params)


def get_file_list() -> list:
    return get_node_list(filters='kind:FILE')


def get_folder_list() -> list:
    return get_node_list(filters='kind:FOLDER')


def get_asset_list() -> list:
    return get_node_list(filters='kind:ASSET')


def get_trashed_folders() -> list:
    return get_node_list(filters='status:TRASH AND kind:FOLDER')


def get_trashed_files() -> list:
    return get_node_list(filters='status:TRASH AND kind:FILE')

ChangeSet = namedtuple('Changes', ['nodes', 'purged_nodes', 'checkpoint', 'reset'])


def get_changes(checkpoint='', include_purged=False) -> ChangeSet:
    """ https://developer.amazon.com/public/apis/experience/cloud-drive/content/changes
    :returns ChangeSet: list of nodes, list of purged nodes, last checkpoint, reset flag
    """

    logger.info('Getting changes with checkpoint "%s".' % checkpoint)

    body = {}
    if checkpoint:
        body['checkpoint'] = checkpoint
    if include_purged:
        body['includePurged'] = 'true'
    r = BackOffRequest.post(get_metadata_url() + 'changes', data=json.dumps(body), stream=True)
    if r.status_code not in OK_CODES:
        r.close()
        raise RequestError(r.status_code, r.text)

    """ return format should be:
    {"checkpoint": str, "reset": bool, "nodes": []}
    {"checkpoint": str, "reset": false, "nodes": []}
    {"end": true}
    """
    reset = False
    nodes = []
    purged_nodes = []

    end = False
    pages = -1

    for line in r.iter_lines(chunk_size=10 * 1024 ** 2, decode_unicode=False):
        # filter out keep-alive new lines
        if not line:
            continue

        pages += 1

        try:
            o = json.loads(line.decode('utf-8'))
        except ValueError:
            raise RequestError(RequestError.CODE.INCOMPLETE_RESULT,
                               '[acd_cli] Invalid JSON in change set, page %i.' % pages)

        try:
            if o['end']:
                end = True
                continue
        except KeyError:
            pass

        if o['reset']:
            logger.info('Found "reset" tag in changes.')
            reset = True

        # could this actually happen?
        if o['statusCode'] not in OK_CODES:
            raise RequestError(RequestError.CODE.FAILED_SUBREQUEST,
                               '[acd_cli] Partial failure in change request.')

        for node in o['nodes']:
            if node['status'] == 'PURGED':
                purged_nodes.append(node['id'])
            else:
                nodes.append(node)
        checkpoint = o['checkpoint']

    r.close()

    logger.info('%i pages, %i nodes, %i purged nodes in changes.'
                % (pages, len(nodes), len(purged_nodes)))
    if not end:
        logger.warning('End of change request not reached.')

    return ChangeSet(nodes, purged_nodes, checkpoint, reset)


def get_metadata(node_id: str) -> dict:
    params = {'tempLink': 'true'}
    r = BackOffRequest.get(get_metadata_url() + 'nodes/' + node_id, params=params)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


# this will increment the node's version attribute
def update_metadata(node_id: str, properties: dict) -> dict:
    body = json.dumps(properties)
    r = BackOffRequest.patch(get_metadata_url() + 'nodes/' + node_id, data=body)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


def get_root_id() -> dict:
    params = {'filters': 'isRoot:true'}
    r = BackOffRequest.get(get_metadata_url() + 'nodes', params=params)

    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)

    data = r.json()

    if 'id' in data['data'][0]:
        return data['data'][0]['id']


def list_children(node_id: str) -> list:
    l = BackOffRequest.paginated_get(get_metadata_url() + 'nodes/' + node_id + '/children')
    return l


def add_child(parent_id: str, child_id: str) -> dict:
    """:returns updated child node dict"""
    r = BackOffRequest.put(get_metadata_url() + 'nodes/' + parent_id + '/children/' + child_id)
    if r.status_code not in OK_CODES:
        logger.error('Adding child failed.')
        raise RequestError(r.status_code, r.text)
    return r.json()


def remove_child(parent_id: str, child_id: str) -> dict:
    """:returns updated child node dict"""
    r = BackOffRequest.delete(get_metadata_url() + 'nodes/' + parent_id + "/children/" + child_id)
    # contrary to response code stated in API doc (202 ACCEPTED)
    if r.status_code not in OK_CODES:
        logger.error('Removing child failed.')
        raise RequestError(r.status_code, r.text)
    return r.json()


def move_node(child_id: str, old_parent_id: str, new_parent_id: str) -> dict:
    data = {'fromParent': old_parent_id, 'childId': child_id}
    r = BackOffRequest.post(get_metadata_url() + 'nodes/' + new_parent_id + '/children',
                            data=json.dumps(data))
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


def rename_node(node_id: str, new_name: str) -> dict:
    properties = {'name': new_name}
    return update_metadata(node_id, properties)


def set_available(node_id: str) -> dict:
    """Sets node status from 'PENDING' to 'AVAILABLE'."""
    properties = {'status': 'AVAILABLE'}
    return update_metadata(node_id, properties)


def list_properties(node_id: str, owner_id: str) -> dict:
    """This will always return an empty dict if the accessor is not the owner.
    :param owner_id: owner ID (return status 404 if empty)
    """
    r = BackOffRequest.get(get_metadata_url() + 'nodes/' + node_id + '/properties/' + owner_id)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()['data']


def add_property(node_id: str, owner_id: str, key: str, value: str) -> dict:
    """Adds or overwrites property. Maximum number of keys per owner is 10.
    :param value: string of length <= 500
    """
    ok_codes = [http.CREATED]
    r = BackOffRequest.put(get_metadata_url() + 'nodes/' + node_id
                           + '/properties/' + owner_id + '/' + key,
                           data=json.dumps({'value': value}), acc_codes=ok_codes)
    if r.status_code not in ok_codes:
        raise RequestError(r.status_code, r.text)
    return r.json()


def delete_property(node_id: str, owner_id: str, key: str):
    ok_codes = [http.NO_CONTENT]
    r = BackOffRequest.delete(get_metadata_url() + 'nodes/' + node_id
                              + '/properties/' + owner_id + '/' + key, acc_codes=ok_codes)
    if r.status_code not in ok_codes:
        raise RequestError(r.status_code, r.text)
