class AIShopError(Exception):
    """Stable error codes. HTTP adapters must not expose exception internals."""
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)
