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
