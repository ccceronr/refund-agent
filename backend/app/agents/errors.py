"""Model failures. The flow turns them into fallbacks or manual review (R-19, R-20)."""


class ModelUnavailable(RuntimeError):
    """A model could not answer after its retries (or was switched off by FAULT_INJECTION).

    `reason` is a short code for logs and steps; it never carries response text.
    """

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} unavailable: {reason}")
        self.provider = provider
        self.reason = reason
