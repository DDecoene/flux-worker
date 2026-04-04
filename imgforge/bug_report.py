import os
import platform
import urllib.parse
from importlib.metadata import version

GITHUB_REPO = "DDecoene/imgforge"
ISSUES_URL = f"https://github.com/{GITHUB_REPO}/issues"


def _build_body(error_message: str, tb: str | None) -> str:
    try:
        pkg_version = version("imgforge")
    except Exception:
        pkg_version = "unknown"

    lines = [
        "## Bug Report",
        "",
        f"**imgforge version:** {pkg_version}",
        f"**Python:** {platform.python_version()}",
        f"**OS:** {platform.system()} {platform.release()}",
        "",
        "**Error:**",
        "```",
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


def fallback_url(error_message: str, tb: str | None) -> str:
    body = _build_body(error_message, tb)
    params = urllib.parse.urlencode({
        "title": f"Unexpected error: {error_message[:80]}",
        "body": body,
        "labels": "bug",
    })
    return f"{ISSUES_URL}/new?{params}"


def create_github_issue(error_message: str, tb: str | None) -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None

    import requests as req
    body = _build_body(error_message, tb)
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


def file_report(error_message: str, tb: str | None) -> dict:
    result = {}
    issue_url = create_github_issue(error_message, tb)
    if issue_url:
        result["issue_url"] = issue_url
    result["fallback_url"] = fallback_url(error_message, tb)
    return result
