class PublicationError(Exception):
    def __init__(self, status: int, code: str, detail: str, errors: list | None = None):
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.errors = errors
