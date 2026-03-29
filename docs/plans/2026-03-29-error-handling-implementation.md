# Error Handling & Bug Reporting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make flux-worker grandma-proof — clean error messages for every failure mode, structured `GenerateResult` for Python API callers, and automated GitHub bug reports for unexpected errors.

**Architecture:** Three-tier error taxonomy (user error, Vast.ai error, unexpected). `generate()` never raises — always returns `GenerateResult`. CLI reads the result and formats output; bug reporting is CLI-only. Typed exceptions are raised internally but caught at the orchestrator boundary.

**Tech Stack:** Python 3.10+, `requests` (GitHub API), `urllib.parse` (fallback URL). No new dependencies.

---

### Task 1: Exception types

**Files:**
- Create: `flux_worker/exceptions.py`

**Step 1: Write `flux_worker/exceptions.py`**

```python
class FluxError(Exception):
    """Base class for all flux-worker errors."""

class UserError(FluxError):
    """Misconfiguration or missing setup on the user's side.
    No bug report. Just show the message and exit."""

class VastAIError(FluxError):
    """An error returned by the Vast.ai API.
    Show their message verbatim. No bug report."""
```

**Step 2: Verify imports**

```bash
uv run python -c "from flux_worker.exceptions import FluxError, UserError, VastAIError; print('ok')"
```

Expected: `ok`

**Step 3: Commit**

```bash
git add flux_worker/exceptions.py
git commit -m "feat: exception hierarchy — UserError, VastAIError, FluxError"
```

---

### Task 2: GenerateResult

**Files:**
- Create: `flux_worker/result.py`

**Step 1: Write `flux_worker/result.py`**

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenerateResult:
    ok: bool
    images: list = field(default_factory=list)   # list[Path], populated on success
    error_type: str | None = None                 # "user_error" | "vastai_error" | "unexpected"
    error_message: str | None = None
    traceback: str | None = None                  # only on "unexpected"
```

**Step 2: Verify**

```bash
uv run python -c "
from flux_worker.result import GenerateResult
r = GenerateResult(ok=True, images=[])
print(r)
r2 = GenerateResult(ok=False, error_type='user_error', error_message='test')
print(r2)
"
```

Expected: both print without error.

**Step 3: Commit**

```bash
git add flux_worker/result.py
git commit -m "feat: GenerateResult dataclass"
```

---

### Task 3: Update config to raise UserError

**Files:**
- Modify: `flux_worker/config.py`

**Step 1: Replace ValueError and FileNotFoundError with UserError**

At the top of `config.py`, add the import:
```python
from flux_worker.exceptions import UserError
```

Replace:
```python
    if not api_key:
        raise ValueError("VASTAI_API_KEY is required. Set it in .env or pass vastai_api_key=.")
```
With:
```python
    if not api_key:
        raise UserError(
            "Missing VASTAI_API_KEY.\n"
            "  Set it in .env or pass --vastai-key."
        )
```

Replace:
```python
    if not key.exists():
        raise FileNotFoundError(
            f"SSH key not found at {key}. "
            "Create one or set SSH_KEY_PATH. "
            "The key must be registered in your Vast.ai account settings."
        )
```
With:
```python
    if not key.exists():
        raise UserError(
            f"SSH key not found at {key}.\n"
            "  Create one or set SSH_KEY_PATH.\n"
            "  The key must be registered in your Vast.ai account: https://console.vast.ai/account/"
        )
```

**Step 2: Verify**

```bash
uv run python -c "
from flux_worker.config import load_config
from flux_worker.exceptions import UserError
try:
    load_config()
except UserError as e:
    print('UserError caught:', e)
"
```

Expected: `UserError caught: Missing VASTAI_API_KEY.`

**Step 3: Commit**

```bash
git add flux_worker/config.py
git commit -m "feat: config raises UserError instead of ValueError/FileNotFoundError"
```

---

### Task 4: Wrap Vast.ai HTTP errors

**Files:**
- Modify: `flux_worker/vastai.py`

The goal: any `resp.raise_for_status()` call should catch `requests.HTTPError` and re-raise as `VastAIError` with the API's error message.

**Step 1: Add import at top of `vastai.py`**

```python
from flux_worker.exceptions import VastAIError
```

**Step 2: Replace every bare `resp.raise_for_status()` with a helper call**

Add this helper function near the top of `vastai.py` (after imports):

```python
def _raise_for_status(resp) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        try:
            msg = resp.json().get("error") or resp.json().get("msg") or resp.text
        except Exception:
            msg = resp.text
        raise VastAIError(f"Vast.ai error: {msg}")
```

Then replace all 5 occurrences of `resp.raise_for_status()` in `vastai.py` with `_raise_for_status(resp)`:
- In `find_offer()`
- In `create_instance()`
- In `get_instance()`
- In `destroy_instance()`

**Step 3: Verify imports**

```bash
uv run python -c "from flux_worker.vastai import find_offer; print('ok')"
```

Expected: `ok`

**Step 4: Commit**

```bash
git add flux_worker/vastai.py
git commit -m "feat: vastai HTTP errors raised as VastAIError with API message"
```

---

### Task 5: Bug report module

**Files:**
- Create: `flux_worker/bug_report.py`

**Step 1: Write `flux_worker/bug_report.py`**

```python
import os
import platform
import urllib.parse
from importlib.metadata import version

GITHUB_REPO = "ddecoene/flux-worker"
ISSUES_URL = f"https://github.com/{GITHUB_REPO}/issues"


def _build_body(error_message: str, tb: str | None, config=None) -> str:
    try:
        pkg_version = version("flux-worker")
    except Exception:
        pkg_version = "unknown"

    lines = [
        "## Bug Report",
        "",
        f"**flux-worker version:** {pkg_version}",
        f"**Python:** {platform.python_version()}",
        f"**OS:** {platform.system()} {platform.release()}",
        "",
    ]

    if config:
        lines += [
            "**Config:**",
            f"- max_gpu_price: {config.max_gpu_price}",
            f"- min_vram_gb: {config.min_vram_gb}",
            f"- min_cuda_version: {config.min_cuda_version}",
            f"- disk_gb: {config.disk_gb}",
            "",
        ]

    lines += [
        "**Error:**",
        f"```",
        error_message,
        "```",
        "",
    ]

    if tb:
        lines += [
            "**Traceback:**",
            "```",
            tb,
            "```",
        ]

    return "\n".join(lines)


def fallback_url(error_message: str, tb: str | None, config=None) -> str:
    """Return a pre-filled GitHub new-issue URL."""
    body = _build_body(error_message, tb, config)
    params = urllib.parse.urlencode({
        "title": f"Unexpected error: {error_message[:80]}",
        "body": body,
        "labels": "bug",
    })
    return f"{ISSUES_URL}/new?{params}"


def create_github_issue(error_message: str, tb: str | None, config=None) -> str | None:
    """Create a GitHub issue via API. Returns issue URL or None on failure."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    import requests as req
    body = _build_body(error_message, tb, config)
    try:
        resp = req.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={
                "title": f"Unexpected error: {error_message[:80]}",
                "body": body,
                "labels": ["bug"],
            },
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json()["html_url"]
    except Exception:
        pass
    return None


def file_report(error_message: str, tb: str | None, config=None) -> dict:
    """File a bug report. Returns dict with 'issue_url' and/or 'fallback_url'."""
    result = {}
    issue_url = create_github_issue(error_message, tb, config)
    if issue_url:
        result["issue_url"] = issue_url
    result["fallback_url"] = fallback_url(error_message, tb, config)
    return result
```

**Step 2: Verify**

```bash
uv run python -c "
from flux_worker.bug_report import fallback_url
url = fallback_url('SSH not ready after 300s', 'Traceback...\nTimeoutError')
print(url[:80], '...')
"
```

Expected: prints a GitHub URL starting with `https://github.com/ddecoene/flux-worker/issues/new?`

**Step 3: Commit**

```bash
git add flux_worker/bug_report.py
git commit -m "feat: bug report — GitHub API issue creation with pre-filled URL fallback"
```

---

### Task 6: Orchestrator returns GenerateResult

**Files:**
- Modify: `flux_worker/orchestrator.py`

**Step 1: Update imports**

Replace the current imports at the top with:

```python
import time
import traceback
from pathlib import Path
from flux_worker.config import load_config
from flux_worker.exceptions import UserError, VastAIError
from flux_worker.result import GenerateResult
from flux_worker import vastai
```

**Step 2: Wrap the entire `generate()` body in try/except**

Replace the current `generate()` function body with:

```python
def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
) -> GenerateResult:
    if isinstance(prompts, str):
        prompts = [prompts]

    config = None
    try:
        config = load_config(
            vastai_api_key=vastai_api_key,
            ssh_key_path=ssh_key_path,
            max_gpu_price=max_gpu_price,
            min_vram_gb=min_vram_gb,
            min_cuda_version=min_cuda_version,
            disk_gb=disk_gb,
            output_dir=output_dir,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Finding GPU (max ${config.max_gpu_price}/hr, {config.min_vram_gb}GB VRAM)...")
        offer = vastai.find_offer(
            config.vastai_api_key,
            config.max_gpu_price,
            config.min_vram_gb,
            config.min_cuda_version,
        )
        print(f"Found: {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr (id={offer['id']})")

        instance_id = None
        try:
            print("Renting instance...")
            result = vastai.create_instance(
                config.vastai_api_key,
                offer["id"],
                prompts,
                config.disk_gb,
            )
            instance_id = result["new_contract"]
            print(f"Instance created. Waiting for SSH...")

            host, port = _wait_for_running(config.vastai_api_key, instance_id)
            vastai.wait_for_ssh(host, port, config.ssh_key_path)
            print("SSH ready. Generating images...")

            paths = _poll_and_download(config, host, port, prompts)
            return GenerateResult(ok=True, images=paths)

        finally:
            if instance_id:
                print("Destroying instance...")
                try:
                    vastai.destroy_instance(config.vastai_api_key, instance_id)
                    print("Instance destroyed.")
                except Exception as e:
                    print(f"Warning: failed to destroy instance: {e}")

    except UserError as e:
        return GenerateResult(
            ok=False,
            error_type="user_error",
            error_message=str(e),
        )
    except VastAIError as e:
        return GenerateResult(
            ok=False,
            error_type="vastai_error",
            error_message=str(e),
        )
    except Exception as e:
        tb = traceback.format_exc()
        return GenerateResult(
            ok=False,
            error_type="unexpected",
            error_message=str(e),
            traceback=tb,
            # store config on result so CLI can include it in bug report
        )
```

Note: we need to pass `config` into the unexpected result so the CLI can include it in the bug report. Add `config` as an attribute to `GenerateResult` for this purpose — update `result.py` to add `config: object = None` as a field.

**Step 3: Update `result.py` to carry config**

In `flux_worker/result.py`, add one field:

```python
    config: object = None  # set on unexpected errors so CLI can include config in bug report
```

And update the unexpected except block in orchestrator.py:

```python
    except Exception as e:
        tb = traceback.format_exc()
        return GenerateResult(
            ok=False,
            error_type="unexpected",
            error_message=str(e),
            traceback=tb,
            config=config,
        )
```

**Step 4: Verify**

```bash
uv run python -c "
from flux_worker.orchestrator import generate
result = generate('test prompt')
print(result.ok, result.error_type, result.error_message)
"
```

Expected (no .env set): `False user_error Missing VASTAI_API_KEY.`

**Step 5: Commit**

```bash
git add flux_worker/orchestrator.py flux_worker/result.py
git commit -m "feat: orchestrator returns GenerateResult, never raises"
```

---

### Task 7: CLI reads result and formats output

**Files:**
- Modify: `flux_worker/cli.py`

**Step 1: Rewrite `generate_cmd` to handle `GenerateResult`**

```python
import json
import click
from flux_worker.orchestrator import generate


@click.group()
def cli():
    pass


@cli.command()
@click.argument("prompts", nargs=-1)
@click.option("--prompts-file", type=click.Path(exists=True), help="JSON file with list of prompts")
@click.option("--output", default="./output", show_default=True, help="Output directory")
@click.option("--vastai-key", envvar="VASTAI_API_KEY", help="Vast.ai API key")
@click.option("--max-gpu-price", type=float, envvar="MAX_GPU_PRICE", help="Max $/hr (default: 0.50)")
@click.option("--min-vram-gb", type=int, envvar="MIN_VRAM_GB", help="Min VRAM in GB (default: 16)")
@click.option("--min-cuda-version", type=float, envvar="MIN_CUDA_VERSION", help="Min CUDA version (default: 12.0)")
@click.option("--disk-gb", type=int, envvar="DISK_GB", help="Disk GB for instance (default: 50)")
@click.option("--ssh-key-path", envvar="SSH_KEY_PATH", help="SSH private key path")
def generate_cmd(prompts, prompts_file, output, vastai_key, max_gpu_price, min_vram_gb, min_cuda_version, disk_gb, ssh_key_path):
    """Generate images from one or more prompts."""
    if prompts_file:
        with open(prompts_file) as f:
            all_prompts = json.load(f)
    else:
        all_prompts = list(prompts)

    if not all_prompts:
        raise click.UsageError("Provide at least one prompt or --prompts-file.")

    result = generate(
        prompts=all_prompts,
        output_dir=output,
        vastai_api_key=vastai_key,
        max_gpu_price=max_gpu_price,
        min_vram_gb=min_vram_gb,
        min_cuda_version=min_cuda_version,
        disk_gb=disk_gb,
        ssh_key_path=ssh_key_path,
    )

    if result.ok:
        for p in result.images:
            click.echo(str(p))
        return

    # Handle errors
    if result.error_type == "user_error":
        click.echo(f"\n✗ {result.error_message}", err=True)
        raise SystemExit(1)

    if result.error_type == "vastai_error":
        click.echo(f"\n✗ {result.error_message}", err=True)
        click.echo("  → https://console.vast.ai", err=True)
        raise SystemExit(1)

    # Unexpected error — show message and file bug report
    click.echo(f"\n✗ Unexpected error: {result.error_message}", err=True)
    click.echo("\n  Filing bug report...", err=True)

    from flux_worker.bug_report import file_report
    report = file_report(result.error_message, result.traceback, result.config)

    if "issue_url" in report:
        click.echo(f"\n  Bug report filed: {report['issue_url']}", err=True)
    click.echo(f"\n  Or report manually: {report['fallback_url']}", err=True)
    raise SystemExit(1)


cli.add_command(generate_cmd, name="generate")
```

**Step 2: Verify**

```bash
flux-worker generate "test prompt"
```

Expected (no .env): clean error message:
```
✗ Missing VASTAI_API_KEY.
  Set it in .env or pass --vastai-key.
```
No Python traceback.

**Step 3: Commit**

```bash
git add flux_worker/cli.py
git commit -m "feat: CLI formats errors by type, files bug report on unexpected errors"
```

---

### Task 8: Update public API export

**Files:**
- Modify: `flux_worker/__init__.py`

**Step 1: Export `GenerateResult` from the package**

```python
from flux_worker.orchestrator import generate
from flux_worker.result import GenerateResult
from flux_worker.exceptions import UserError, VastAIError, FluxError

__all__ = ["generate", "GenerateResult", "UserError", "VastAIError", "FluxError"]
```

**Step 2: Verify**

```bash
uv run python -c "
from flux_worker import generate, GenerateResult, UserError, VastAIError
print('all exports ok')
"
```

Expected: `all exports ok`

**Step 3: Commit**

```bash
git add flux_worker/__init__.py
git commit -m "feat: export GenerateResult and exception types from package"
```
