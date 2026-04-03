class ImgForgeError(Exception):
    """Base class for all imgforge errors."""

class UserError(ImgForgeError):
    """Misconfiguration or missing setup on the user's side."""
