"""Domain errors raised by services; api/ maps them to HTTP in one place (CLAUDE.md)."""


class CaseNotFound(LookupError):
    pass


class RunInProgress(RuntimeError):
    """A run is already preparing this case (409)."""


class CaseAlreadyDecided(RuntimeError):
    """The case is resolved; it can't be run or decided again (409)."""


class FeeAlreadyRefunded(RuntimeError):
    """BR-05: a fee can never be refunded twice, by anyone."""


class ApprovalNotAllowed(PermissionError):
    """BR-09: the actor lacks the authority for this refund. `message` is shown to Luis."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoFeeIdentified(ValueError):
    """BR-09 "Manual cases": a refund needs an identified fee (422)."""


class InvalidDecision(ValueError):
    """A decision that doesn't fit the case (design §4.3). `message` is shown to Luis (422)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RunLimitReached(RuntimeError):
    """LLM10: the case was prepared too many times in the last hour (429)."""


class WrongCredentials(PermissionError):
    """Wrong username or password; never says which (OWASP A07)."""


class TooManyAttempts(PermissionError):
    """Too many failed sign-ins for this username (design §4.0)."""
