import json
import logging

from acd.common import *

logger = logging.getLogger(__name__)


# additional parameters are: tempLink='true'
def get_node_list(**params):
    q_params = {}
    for param in params.keys():
        q_params[param] = params[param]

    return paginated_get_request(get_metadata_url() + 'nodes', q_params)


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


def get_changes(checkpoint='', include_purged=False) -> (list, str, bool):
    """ https://developer.amazon.com/public/apis/experience/cloud-drive/content/changes
    :returns (list, purged, str, bool) list of nodes, list of purged nodes, last checkpoint, reset flag
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

        o = json.loads(line.decode('utf-8'))
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
            raise RequestError(RequestError.CODE.FAILED_SUBREQUEST, '[acd_cli] Partial failure in change request.')

        for node in o['nodes']:
            if node['status'] == 'PURGED':
                purged_nodes.append(node['id'])
            else:
                nodes.append(node)
        checkpoint = o['checkpoint']

    r.close()

    logger.info('%i pages, %i nodes, %i purged nodes in changes.' % (pages, len(nodes), len(purged_nodes)))
    if not end:
        logger.warning('End of change request not reached.')

    return nodes, purged_nodes, checkpoint, reset


def get_metadata(node_id):
    params = {'tempLink': 'true'}
    r = BackOffRequest.get(get_metadata_url() + 'nodes/' + node_id, params=params)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


# this will increment the node's version attribute
def update_metadata(node_id, properties):
    body = json.dumps(properties)
    r = BackOffRequest.patch(get_metadata_url() + 'nodes/' + node_id, data=body)
    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)
    return r.json()


# necessary?
def get_root_id():
    params = {'filters': 'isRoot:true'}
    r = BackOffRequest.get(get_metadata_url() + 'nodes', params=params)

    if r.status_code not in OK_CODES:
        raise RequestError(r.status_code, r.text)

    data = r.json()

    if 'id' in data['data'][0]:
        return data['data'][0]['id']


# unused
def list_children(node_id):
    r = BackOffRequest.get(get_metadata_url() + 'nodes/' + node_id + '/children')
    return r.json


def add_child(parent, child):
    r = BackOffRequest.put(get_metadata_url() + 'nodes/' + parent + '/children/' + child)
    if r.status_code not in OK_CODES:
        logger.error('Adding child failed.')
        raise RequestError(r.status_code, r.text)
    return r.json()


def remove_child(parent, child):
    r = BackOffRequest.delete(get_metadata_url() + 'nodes/' + parent + "/children/" + child)
    if r.status_code not in OK_CODES:
        logger.error('Removing child failed.')
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


# TODO
def list_properties(node_id):
    owner_id = ''
    r = BackOffRequest.get(get_metadata_url() + "/nodes/" + node_id + "/properties/" + owner_id)
    return r.text