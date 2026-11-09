class InvalidDateRange(Exception):
    pass


class GameNotFound(Exception):
    pass


class InsufficientFunds(Exception):
    pass


class UpstreamError(Exception):
    """Another service failed or returned an unexpected response."""
