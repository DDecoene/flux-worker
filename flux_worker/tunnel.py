import re
import subprocess
import threading
import shutil
from flux_worker.exceptions import UserError

INSTALL_MSG = (
    "cloudflared is required but not installed.\n"
    "  macOS:  brew install cloudflare/cloudflare/cloudflared\n"
    "  Linux:  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/\n"
    "  Then re-run flux-worker."
)


class Tunnel:
    def __init__(self):
        self._proc = None
        self.url = None

    def start(self, port: int) -> str:
        if not shutil.which("cloudflared"):
            raise UserError(INSTALL_MSG)

        self._proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Parse URL from output (appears within ~5s)
        url = None
        for line in self._proc.stdout:
            match = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                break

        if not url:
            self._proc.terminate()
            raise RuntimeError("cloudflared did not produce a tunnel URL")

        self.url = url
        # Drain remaining stdout in background so pipe doesn't block
        threading.Thread(target=self._proc.stdout.read, daemon=True).start()
        return url

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
