from collections import namedtuple
import json

from .messaging.connection.messages.connection_invite import ConnectionInvite
from .messaging.request_context import BaseRequestContext
from .storage import BaseStorage, StorageRecord
from .wallet import BaseWallet

# Temporary connection object
Connection = namedtuple("Connection", "endpoint")


class ConnectionException(Exception):
    pass



### Prototype connection handling methods below
# Not handled:
# - message transmission
# - admin messages, presumably sent by the handler calling these methods
# Not yet implemented:
# - wallet.create_key for creating invitation keys
# - AdminMessage._id (for @id, optional in input)
# - AdminMessage._thread (~thread)
# - updates to ConnectionRequest, ConnectionResponse models:
#   - new model the "connection" block in ConnectionRequest, ConnectionResponse
#   - connection block signature (not defined in spec)
#   - model for DIDDoc (version exists in von_anchor)


class ConnectionManager:
    def __init__(self, context: BaseRequestContext):
        self._context = context

    @property
    def context(self) -> BaseRequestContext:
        """
        Accessor for the current request context
        """
        return self._context

    async def create_invitation(self, label: str, endpoint: str, metadata: dict) -> ConnectionInvitation:
        """
        Generate new connection invitation.
        This interaction represents an out-of-band communication channel. In the future and in
        practice, these sort of invitations will be received over any number of channels such as
        SMS, Email, QR Code, NFC, etc.
        Structure of an invite message:
            {
                "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/connections/1.0/invitation",
                "label": "Alice",
                "did": "did:sov:QmWbsNYhMrjHiqZDTUTEJs"
            }
        Or, in the case of a peer DID:
            {
                "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/connections/1.0/invitation",
                "label": "Alice",
                "did": "did:peer:oiSqsNYhMrjHiqZDTUthsw",
                "key": "8HH5gYEeNc3z7PYXmd54d4x6qAfCNrqQqEB3nS7Zfu7K",
                "endpoint": "https://example.com/endpoint"
            }
        Currently, only peer DID is supported.
        """

        # Create and store new connection key
        connection_key = await self.context.wallet.create_key(metadata)
            # may want to store additional metadata on the key (creation date etc.)

        # Create connection invitation message
        return ConnectionInvitation(
            label,
            key=connection_key,
            endpoint=endpoint,
        )

    async def store_invitation(self, invitation: ConnectionInvitation, metadata: dict = None) -> str:
        """
        Save an invitation for acceptance/rejection and later processing
        """
        # may want to generate another unique ID, or use the message ID instead of the key
        invitation_id = invitation.key

        await self.context.storage.add_record(
            StorageRecord(
                "invitation",
                invitation_id,
                json.dumps(invitation.serialize()),
                metadata,
            )
        )
        return invitation_id

    async def find_invitation(self, invitation_id: str) -> (ConnectionInvitation, dict):
        """
        Locate a previously-received invitation
        """
        # raises exception if not found
        result = await self.context.storage.get_record(
            "invitation",
            invitation_id,
        )
        invitation = ConnectionInvitation.unserialize(result.value)
        return invitation, result.metadata

    async def remove_invitation(self, invitation_id: str):
        """
        Remove a previously-stored invitation
        """
        # raises exception if not found
        result = await self.context.storage.delete_record(
            "invitation",
            invitation_id,
        )

    async def accept_invitation(
            self,
            invitation: ConnectionInvitation,
            my_label: str = None,
            my_endpoint: str = None) -> ConnectionRequest:
        """
        Create a new connection request for a previously-received invitation
        """

        their_label = invitation.label
        their_connection_key = invitation.key
        their_endpoint = invitation.endpoint

        # Create my information for connection
        my_info = await self.context.wallet.create_local_did(
            None, None, {
                "their_label": their_label,
                "their_endpoint": their_endpoint,
            }
        )
        if not my_label:
            my_label = self.context.default_label
        if not my_endpoint:
            my_endpoint = self.context.default_endpoint

        did_doc = DIDDoc({"key": my_info.verkey, "endpoint": my_endpoint})

        # Create connection request message
        request = ConnectionRequest(
            my_label,
            ConnectionDetail(my_info.did, did_doc),
        )

        # Store message so that response can be processed
        await self.context.storage.add_record(
            StorageRecord(
                "connection_request",
                request._id,
                json.dumps(request.serialize()),
            )
        )

        # request must be sent to their_endpoint using their_connection_key, from my_info.verkey
        return request

    async def find_request(self, request_id: str) -> ConnectionRequest:
        """
        Locate a previously saved connection request
        """
        # raises exception if not found
        result = await self.context.storage.get_record(
            "connection_request",
            request_id,
        )
        request = ConnectionRequest.unserialize(result.value)
        return request

    async def accept_request(
            self,
            request: ConnectionRequest,
            my_endpoint: str = None) -> ConnectionResponse:
        """
        Create a connection response for a received connection request
        """

        connection_key = self.context.my_verkey
        if not my_endpoint:
            my_endpoint = self.context.default_endpoint

        their_label = request.label
        their_did = request.connection.did
        conn_did_doc = request.connection.did_doc
        their_verkey = conn_did_doc.key
        their_endpoint = conn_did_doc.endpoint

        # Create a new pairwise record with a newly-generated local DID
        pairwise = await self.context.wallet.create_pairwise(
            their_did,
            their_verkey,
            None,
            {
                "label": their_label,
                "endpoint": their_endpoint,
                # TODO: store established & last active dates
            }
        )

        did_doc = DIDDoc({"key": pairwise.my_verkey, "endpoint": my_endpoint})

        # request must be sent to their_endpoint, packed with their_verkey and pairwise.my_verkey
        return ConnectionResponse(
            # ~thread: {tid: request._id} must be set
            ConnectionDetail(pairwise.my_did, did_doc),
        )

    async def accept_response(self, response: ConnectionResponse):
        """
        Process a ConnectionResponse message by looking up
        the connection request and setting up the pairwise connection
        """

        request_id = response._thread.tid
        request = await self.find_request(request_id)

        my_did = request.connection.did
        their_did = response.connection.did
        conn_did_doc = request.connection.did_doc
        their_verkey = conn_did_doc.key
        their_endpoint = conn_did_doc.endpoint
            # if not set in DIDDoc, retrieve from local DID metadata below

        my_info = await self.context.wallet.get_local_did(my_did)
        their_label = my_info.metadata.get("their_label")
        # their_endpoint = my_info.metadata.get("their_endpoint")
        if not their_label:
            # local DID not associated with a connection
            raise ConnectionException()

        # update local DID metadata to mark connection as accepted, prevent multiple responses?
        # may also set a creation time on the local DID to allow request expiry

        # In the final implementation, a signature will be provided to verify changes to
        # the keys and DIDs to be used long term in the relationship.
        # Both the signature and signature check are omitted for now until specifics of the
        # signature are decided.

        # Create a new pairwise record associated with our previously-generated local DID
        pairwise = await self.context.wallet.create_pairwise(
            their_did,
            their_verkey,
            my_did,
            {
                "label": their_label,
                "endpoint": their_endpoint,
                # TODO: store established & last active dates
            }
        )

        # may wish to send a Trust Ping to verify the endpoint and confirm the connection
