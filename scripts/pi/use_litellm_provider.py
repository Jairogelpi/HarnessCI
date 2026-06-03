"""Switch Pi defaults to the LiteLLM provider after verifying the gateway.

This script is intentionally conservative: it refuses to switch unless
http://localhost:4000/v1/models responds.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

USER_SETTINGS = Path.home() / ".pi" / "agent" / "settings.json"
PROJECT_SETTINGS = Path(".pi") / "settings.json"
MODELS_URL = "http://localhost:4000/v1/models"


def main() -> int:
    if not gateway_is_up():
        print("LiteLLM gateway is not reachable at http://localhost:4000/v1/models")
        print("Start it first: powershell -File scripts/pi/start_litellm_gateway.ps1")
        return 1

    update_settings(USER_SETTINGS)
    if PROJECT_SETTINGS.exists():
        update_settings(PROJECT_SETTINGS)

    print("Pi defaults switched to provider=litellm model=harness-frontier")
    print("Restart Pi or use /model to refresh if needed.")
    return 0


def gateway_is_up() -> bool:
    req = urllib.request.Request(MODELS_URL, headers={"User-Agent": "harnessci-pi-check"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.HTTPError, urllib.error.URLError):
        return False


def update_settings(path: Path) -> None:
    data = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data["defaultProvider"] = "litellm"
    data["defaultModel"] = "harness-frontier"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
