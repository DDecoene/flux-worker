class FluxError(Exception):
    """Base class for all flux-worker errors."""

class UserError(FluxError):
    """Misconfiguration or missing setup on the user's side.
    No bug report. Just show the message and exit."""
