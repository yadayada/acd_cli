"""
Node trashing and restoration.
https://developer.amazon.com/public/apis/experience/cloud-drive/content/trash
"""

from .common import *


class TrashMixin(object):
    def list_trash(self) -> list:
        """Retrieves top-level trash list"""
        return self.BOReq.paginated_get(self.metadata_url + 'trash')

    def move_to_trash(self, node_id: str) -> dict:
        r = self.BOReq.put(self.metadata_url + 'trash/' + node_id)
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    def restore(self, node_id: str) -> dict:
        r = self.BOReq.post(self.metadata_url + 'trash/' + node_id + '/restore')
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()

    # {"message":"Insufficient permissions granted for operation: purgeNode"}
    def purge(self, node_id: str) -> dict:
        r = self.BOReq.delete(self.metadata_url + 'nodes/' + node_id)
        if r.status_code not in OK_CODES:
            raise RequestError(r.status_code, r.text)
        return r.json()
