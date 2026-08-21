"""Authentication exceptions."""


class AuthenticationError(Exception):
    """Base authentication error."""

    pass


class TokenExpiredError(AuthenticationError):
    """Token has expired."""

    pass


class InvalidTokenError(AuthenticationError):
    """Token is invalid or malformed."""

    pass
