"""
Request context class
"""

class BaseRequestContext:
    """
    Context established by Dispatcher and passed into message handlers
    """

    @property
    def default_endpoint(self) -> str:
        """
        Accessor for the default agent endpoint (from agent config)
        """

    @property
    def default_label(self) -> str:
        """
        Accessor for the default agent label (from agent config)
        """

    @property
    def recipient_verkey(self) -> str:
        """
        Accessor for the recipient public key used to pack the incoming request
        """

    @property
    def sender_verkey(self) -> str:
        """
        Accessor for the sender public key used to pack the incoming request
        """

    @property
    def transport_type(self) -> str:
        """
        Accessor for the transport type used to receive the message
        """

    @property
    def storage(self) -> BaseStorage:
        """
        Accessor for the BaseStorage implementation
        """

    @property
    def wallet(self) -> BaseWallet:
        """
        Accessor for the BaseWallet implementation
        """

    # Connection info / state
    # Thread info / state
    # Extra transport info? (received at endpoint?)
