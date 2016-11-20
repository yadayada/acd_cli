"""Node metadata operations"""

import json
import logging
import http.client
import tempfile
from collections import namedtuple

from .common import *

logger = logging.getLogger(__name__)

ChangeSet = namedtuple('Changes', ['nodes', 'purged_nodes', 'checkpoint', 'reset'])


class MetadataMixin(object):
    def get_node_list(self, **params) -> list:
        """:param params: may include tempLink='True'"""
        return self.BOReq.paginated_get(self.metadata_url + 'nodes', params)

    def get_file_list(self) -> list:
        return self.get_node_list(filters='kind:FILE')

    def get_folder_list(self) -> list:
        return self.get_node_list(filters='kind:FOLDER')

    def get_asset_list(self) -> list:
        return self.get_node_list(filters='kind:ASSET')

    def get_trashed_folders(self) -> list:
        return self.get_node_list(filters='status:TRASH AND kind:FOLDER')

    def get_trashed_files(self) -> list:
        return self.get_node_list(filters='status:TRASH AND kind:FILE')

    def get_changes(self, checkpoint='', include_purged=False, silent=True, file=None):
        """Writes changes into a (temporary) file. See
        `<https://developer.amazon.com/public/apis/experience/cloud-drive/content/changes>`_.
        """

        logger.info('Getting changes with checkpoint "%s".' % checkpoint)

        body = {}
        if checkpoint:
            body['checkpoint'] = checkpoint
        if include_purged:
            body['includePurged'] = 'true'
        r = self.BOReq.post(self.metadata_url + 'changes', data=json.dumps(body), stream=True)
        if r.status_code not in OK_CODES:
            r.close()
            raise RequestError(r.status_code, r.text)

        if file:
            tmp = open(file, 'w+b')
        else:
            tmp = tempfile.TemporaryFile('w+b')
        try:
            for line in r.iter_lines(chunk_size=10 * 1024 ** 2, decode_unicode=False):
                if line:
                    tmp.write(line + b'\n')
                    if not silent:
                        print('.', end='', flush=True)
            if not silent:
                print()
        except (http.client.IncompleteRead, requests.exceptions.ChunkedEncodingError) as e:
            logger.info(str(e))
            raise RequestError(RequestError.CODE.INCOMPLETE_RESULT,
                               '[acd_api] reading changes terminated prematurely.')
        except:
            raise
        finally:
            r.close()
            tmp.seek(0)
            return tmp

    @staticmethod
    def _iter_changes_lines(f) -> 'Generator[ChangeSet]':
        """Generates a ChangeSet per line in passed file

        the expected return format should be:
        {"checkpoint": str, "reset": bool, "nodes": []}
        {"checkpoint": str, "reset": false, "nodes": []}
        {"end": true}

        :arg f: opened file with current position at the beginning of a changeset
        :throws: RequestError
        """

        end = False
        pages = -1

        while True:
            line = f.readline()
            if not line:
                break

            reset = False
            pages += 1

            nodes = []
            purged_nodes = []

            try:
                o = json.loads(line.decode('utf-8'))
            except ValueError:
                raise RequestError(RequestError.CODE.INCOMPLETE_RESULT,
                                   '[acd_api] Invalid JSON in change set, page %i.' % pages)

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
                                   '[acd_api] Partial failure in change request.')

            for node in o['nodes']:
                if node['status'] == 'PURGED':
                    purged_nodes.append(node['id'])
                else:
                    nodes.append(node)

            checkpoint = o['checkpoint']
            logger.debug('Checkpoint: %s' % checkpoint)

            yield ChangeSet(nodes, purged_nodes, checkpoint, reset)

        logger.info('%i page(s) in changes.' % pages)
        if not end:
            logger.warning('End of change request not reached.')

    def get_metadata(self, node_id: str, assets=False, temp_link=True) -> dict:
        """Gets a node's metadata.

        :arg assets: also include asset info (e.g. thumbnails) if the node is a file
        :arg temp_link: include a temporary download link if the node is a file
        """
        params = {'tempLink': 'true' if temp_link else 'false',
                  'asset': 'ALL' if assets else 'NONE'}
        r = self.BOReq.get(self.metadata_url + 'nodes/' + node_id, params=params)
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    # this will increment the node's version attribute
    def update_metadata(self, node_id: str, properties: dict) -> dict:
        """Update a node's properties like name, description, status, parents, ..."""
        body = json.dumps(properties)
        r = self.BOReq.patch(self.metadata_url + 'nodes/' + node_id, data=body)
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    def get_root_node(self) -> dict:
        """Gets the root node metadata"""

        params = {'filters': 'isRoot:true'}
        r = self.BOReq.get(self.metadata_url + 'nodes', params=params)

        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)

        data = r.json()

        return data['data'][0]

    def get_root_id(self) -> str:
        """Gets the ID of the root node

        :returns: the topmost folder id"""

        r = self.get_root_node()
        if 'id' in r['data'][0]:
            return r['data'][0]['id']

    def list_children(self, node_id: str) -> list:
        l = self.BOReq.paginated_get(self.metadata_url + 'nodes/' + node_id + '/children')
        return l

    def list_child_folders(self, node_id: str) -> list:
        l = self.BOReq.paginated_get(self.metadata_url + 'nodes/' + node_id + '/children',
                                     params={'filters': 'kind:FOLDER'})
        return l

    def add_child(self, parent_id: str, child_id: str) -> dict:
        """Adds node with ID *child_id* to folder with ID *parent_id*.

        :returns: updated child node dict"""

        r = self.BOReq.put(self.metadata_url + 'nodes/' + parent_id + '/children/' + child_id)
        if r.status_code not in OK_CODES:
            logger.error('Adding child failed.')
            raise RequestError(r.status_code, r.text)
        return r.json()

    def remove_child(self, parent_id: str, child_id: str) -> dict:
        """:returns: updated child node dict"""
        r = self.BOReq.delete(
            self.metadata_url + 'nodes/' + parent_id + "/children/" + child_id)
        # contrary to response code stated in API doc (202 ACCEPTED)
        if r.status_code not in OK_CODES:
            logger.error('Removing child failed.')
            raise RequestError(r.status_code, r.text)
        return r.json()

    def move_node_from(self, node_id: str, old_parent_id: str, new_parent_id: str) -> dict:
        """Moves node with given ID from old parent to new parent.
        Not tested with multi-parent nodes.

        :returns: changed node dict"""

        data = {'fromParent': old_parent_id, 'childId': node_id}
        r = self.BOReq.post(self.metadata_url + 'nodes/' + new_parent_id + '/children',
                            data=json.dumps(data))
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    def move_node(self, node_id: str, parent_id: str) -> dict:
        return self.update_metadata(node_id, {'parents': [parent_id]})

    def rename_node(self, node_id: str, new_name: str) -> dict:
        properties = {'name': new_name}
        return self.update_metadata(node_id, properties)

    def set_available(self, node_id: str) -> dict:
        """Sets node status from 'PENDING' to 'AVAILABLE'."""
        properties = {'status': 'AVAILABLE'}
        return self.update_metadata(node_id, properties)

    def get_owner_id(self):
        """Provisional function for retrieving the security profile's name, a.k.a. owner id."""
        node = self.create_file('acd_cli_get_owner_id')
        self.move_to_trash(node['id'])
        return node['createdBy']

    def list_properties(self, node_id: str, owner_id: str) -> dict:
        """This will always return an empty dict if the accessor is not the owner.
        :param owner_id: owner ID (return status 404 if empty)"""

        r = self.BOReq.get(self.metadata_url + 'nodes/' + node_id + '/properties/' + owner_id)
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()['data']

    def add_property(self, node_id: str, owner_id: str, key: str, value: str) -> dict:
        """Adds or overwrites *key* property with *content*. Maximum number of keys per owner is 10.

        :param value: string of length <= 500
        :raises: RequestError: 404, <UnknownOperationException/> if owner is empty
                 RequestError: 400, {...} if maximum of allowed properties is reached
        :returns dict: {'key': '<KEY>', 'location': '<NODE_ADDRESS>/properties/<OWNER_ID/<KEY>',
        'value': '<VALUE>'}"""

        ok_codes = [requests.codes.CREATED]
        r = self.BOReq.put(self.metadata_url + 'nodes/' + node_id +
                           '/properties/' + owner_id + '/' + key,
                           data=json.dumps({'value': value}), acc_codes=ok_codes)
        if r.status_code not in ok_codes:
            raise RequestError(r.status_code, r.text)
        return r.json()

    def delete_property(self, node_id: str, owner_id: str, key: str):
        """Deletes *key* property from node with ID *node_id*."""
        ok_codes = [requests.codes.NO_CONTENT]
        r = self.BOReq.delete(self.metadata_url + 'nodes/' + node_id +
                              '/properties/' + owner_id + '/' + key, acc_codes=ok_codes)
        if r.status_code not in ok_codes:
            raise RequestError(r.status_code, r.text)

    def delete_properties(self, node_id: str, owner_id: str):
        """Deletes all of the owner's properties. Uses multiple requests."""
        ok_codes = [requests.codes.NO_CONTENT]
        prop_dict = self.list_properties(node_id, owner_id)
        for key in prop_dict:
            r = self.BOReq.delete('%s/nodes/%s/properties/%s/%s'
                                  % (self.metadata_url, node_id, owner_id, key), acc_codes=ok_codes)
            if r.status_code not in ok_codes:
                raise RequestError(r.status_code, r.text)

    def resolve_folder_path(self, path: str) -> 'List[dict]':
        """Resolves a non-trash folder path to a list of folder entries."""
        segments = list(filter(bool, path.split('/')))
        folder_chain = []

        root = self.get_root_node()
        folder_chain.append(root)

        if not segments:
            return folder_chain

        for i, segment in enumerate(segments):
            dir_entries = self.list_child_folders(folder_chain[-1]['id'])

            for ent in dir_entries:
                if ent['status'] == 'AVAILABLE' and ent['name'] == segment:
                    folder_chain.append(ent)
                    break
            if len(folder_chain) != i + 2:
                return []

        return folder_chain
