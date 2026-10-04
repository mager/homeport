#!/usr/bin/env python3
"""Give the loopback web app a private, owner-only Tailscale Serve URL."""

import json
import shutil
import subprocess
from pathlib import Path

from magerbot.cli import get_config
from magerbot.web import WebSettings

binary = (
    shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
)


def read(*args):
    return json.loads(subprocess.check_output([binary, *args], text=True))


status = read("status", "--json")
if status.get("BackendState") != "Running":
    raise SystemExit("Sign into Tailscale on this Mac first.")
self = status["Self"]
host = self["DNSName"].rstrip(".")
user = status["User"][str(self["UserID"])]["LoginName"]
existing = read("serve", "status", "--json")
key = f"{host}:9443"
handler = existing.get("Web", {}).get(key, {}).get("Handlers", {})
if (
    "9443" in existing.get("TCP", {})
    and handler != {"/": {"Proxy": "http://127.0.0.1:8787"}}
) or existing.get("AllowFunnel", {}).get(key):
    raise SystemExit(
        "Port 9443 already has a different service or Funnel enabled. Leave it unchanged and choose a different port manually."
    )
config = get_config()
config.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
settings = config.state_dir / "web.json"
settings.write_text(
    WebSettings(origin=f"https://{host}:9443", tailscale_user=user).model_dump_json(
        indent=2
    )
)
settings.chmod(0o600)
subprocess.run(
    [binary, "serve", "--bg", "--https=9443", "http://127.0.0.1:8787"], check=True
)
print("Restart only the web pane to load access settings:")
print(
    f"{config.tmux} -L magerbot respawn-pane -k -t magerbot:web {Path(__file__).resolve().parents[1] / '.venv/bin/homeport'} web"
)
print(f"Open https://{host}:9443 on a device signed into the same Tailscale account.")
