class InvalidDateRange(Exception):
    pass


class GameNotFound(Exception):
    pass


class InsufficientFunds(Exception):
    pass


class UpstreamError(Exception):
    """Another service failed or returned an unexpected response."""


class GameNotOpen(Exception):
    """The game is not scheduled, or it has already started."""


class InvalidNumbers(Exception):
    pass
