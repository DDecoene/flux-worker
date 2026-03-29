# Error Handling & Bug Reporting Design

**Goal:** Make flux-worker grandma-proof — clear messages for every failure, structured results for programmatic callers, and automatic bug reports for anything unanticipated.

---

## Error Taxonomy

Three categories with distinct behaviours:

| Category | Examples | Python API | CLI |
|---|---|---|---|
| **User error** | Missing API key, SSH key not found | `result.error_type = "user_error"` | Clean message, exit 1, no report |
| **Vast.ai error** | Insufficient credit, no capacity, HTTP 4xx/5xx | `result.error_type = "vastai_error"` | Pass through their message verbatim + link to console.vast.ai |
| **Unexpected error** | SSH timeout, unanticipated exceptions, our bugs | `result.error_type = "unexpected"` | Clean message + automated bug report |

---

## Python API: Structured Result

`generate()` never raises. It always returns a `GenerateResult`:

```python
@dataclass
class GenerateResult:
    ok: bool
    images: list[Path]          # populated on success, empty on failure
    error_type: str | None      # "user_error" | "vastai_error" | "unexpected" | None
    error_message: str | None   # human-readable message
    traceback: str | None       # only populated on "unexpected", None otherwise
```

Callers (e.g. `social-agent`) branch on `error_type`:

```python
result = generate(prompts)
if not result.ok:
    if result.error_type == "vastai_error":
        # retry later
    elif result.error_type == "user_error":
        # surface to user
    else:
        # unexpected — log result.traceback
```

---

## CLI: Formatted Output

The CLI reads `GenerateResult` and formats accordingly.

**User error:**
```
✗ Missing VASTAI_API_KEY.
  Set it in .env or pass --vastai-key.
```

**Vast.ai error:**
```
✗ Vast.ai error: Your account balance is too low to rent this instance.
  → https://console.vast.ai
```

**Unexpected error:**
```
✗ Unexpected error: SSH not ready after 300s

  An automated bug report has been filed:
  https://github.com/ddecoene/flux-worker/issues/42

  (or visit: https://github.com/ddecoene/flux-worker/issues/new?...)
```

---

## Bug Report

Triggered only on `error_type == "unexpected"`, from the CLI only.

**Included (privacy-safe):**
- flux-worker version
- Error message + traceback
- Config: `max_gpu_price`, `min_vram_gb`, `min_cuda_version`, `disk_gb`
- Platform: OS, Python version

**Never included:**
- Prompt text
- Instance ID
- API keys or SSH key paths

**Flow:**
1. If `GITHUB_TOKEN` is set: create issue via GitHub API → print issue URL
2. Always print pre-filled `github.com/ddecoene/flux-worker/issues/new?body=...` URL as fallback

---

## New Files

- `flux_worker/exceptions.py` — `FluxError`, `UserError`, `VastAIError`
- `flux_worker/result.py` — `GenerateResult` dataclass
- `flux_worker/bug_report.py` — GitHub issue creation + fallback URL

## Modified Files

- `flux_worker/config.py` — raise `UserError` instead of `ValueError`/`FileNotFoundError`
- `flux_worker/vastai.py` — wrap HTTP errors as `VastAIError` with API message
- `flux_worker/orchestrator.py` — catch all exceptions, return `GenerateResult`
- `flux_worker/cli.py` — read result, format output, trigger bug report on unexpected
