"""
Represents an invitation message for establishing connection.
"""

from marshmallow import (
    Schema, ValidationError, fields, post_dump, post_load, validates_schema,
)

from ...agent_message import AgentMessage
from ...message_types import MessageTypes
from ...validators import must_not_be_none

from ..handlers.connection_invitation_handler import ConnectionInvitationHandler

class ConnectionInvitation(AgentMessage):
    def __init__(
            self,
            label: str,
            *,
            did: str = None,
            key: str = None,
            endpoint: str = None,
            image_url: str = None,
        ):
        self.handler = ConnectionInvitationHandler(self)
        self.did = did
        self.key = key
        self.endpoint = endpoint
        self.image_url = image_url
        self.label = label

    @property
    # Avoid clobbering builtin property
    def _type(self) -> str:
        return MessageTypes.CONNECTION_INVITATION.value

    @classmethod
    def deserialize(cls, obj):
        return ConnectionInvitationSchema().load(obj)

    def serialize(self):
        return ConnectionInvitationSchema().dump(self)


class ConnectionInvitationSchema(Schema):
    # Avoid clobbering builtin property
    _type = fields.Str(data_key="@type")
    label = fields.Str()
    did = fields.Str(required=False)
    key = fields.Str(required=False)
    endpoint = fields.Str(required=False)
    image_url = fields.Str(required=False)

    @post_load
    def make_model(self, data: dict) -> ConnectionInvitation:
        del data["_type"]
        return ConnectionInvitation(**data)

    @post_dump
    def remove_empty_values(self, data):
        return {
            key: value for key, value in data.items()
            if value is not None
        }

    @validates_schema
    def validate_fields(self, data):
        fields = ()
        if "did" in data:
            if "key" in data:
                raise ValidationError("Fields are incompatible", ("did", "key"))
            if "endpoint" in data:
                raise ValidationError("Fields are incompatible", ("did", "endpoint"))
        elif "key" not in data:
            raise ValidationError("One or the other is required", ("did", "key"))
        elif "endpoint" not in data:
            raise ValidationError("Both fields are required", ("key", "endpoint"))
