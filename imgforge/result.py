from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenerateResult:
    ok: bool
    images: list = field(default_factory=list)   # list[Path], populated on success
    error_type: str | None = None                 # "user_error" | "unexpected"
    error_message: str | None = None
    traceback: str | None = None                  # only on "unexpected"
