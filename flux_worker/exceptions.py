class FluxError(Exception):
    """Base class for all flux-worker errors."""

class UserError(FluxError):
    """Misconfiguration or missing setup on the user's side.
    No bug report. Just show the message and exit."""

class VastAIError(FluxError):
    """An error returned by the Vast.ai API.
    Show their message verbatim. No bug report."""
