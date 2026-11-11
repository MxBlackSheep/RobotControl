"""The two wordings of a failed stored-field check: the route's 400 text and the review reason."""


class CheckError(ValueError):
    """str() stays the route's 400 text; review_reason is the plain sentence a stored record shows."""

    def __init__(self, message, review_reason=None):
        super().__init__(message)
        self.review_reason = review_reason or message


def review_reason(exc, fallback):
    """The plain reason for a stored record; anything a check did not word itself reads as `fallback`."""
    return exc.review_reason if isinstance(exc, CheckError) else fallback
