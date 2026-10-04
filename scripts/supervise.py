#!/usr/bin/env python3
"""Launchd supervises this process; it restores dead tmux panes, never tasks."""

import fcntl
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".local/state/magerbot"
TMUX = ["/opt/homebrew/bin/tmux", "-L", "magerbot"]
os.umask(0o077)
os.environ["PATH"] = (
    f"/opt/homebrew/bin:{Path.home() / '.local/bin'}:/usr/bin:/bin:/usr/sbin:/sbin"
)
for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
    os.environ.pop(key, None)
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
lock = (STATE / "supervisor.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def tmux(*args, check=True):
    return subprocess.run([*TMUX, *args], text=True, capture_output=True, check=check)


server = [
    "/opt/homebrew/bin/codex",
    "app-server",
    "--listen",
    f"unix://{STATE / 'codex.sock'}",
    "-c",
    'approval_policy="never"',
    "-c",
    'sandbox_mode="danger-full-access"',
    "-c",
    'forced_login_method="chatgpt"',
]
worker = [str(ROOT / ".venv/bin/homeport"), "worker"]
web = [str(ROOT / ".venv/bin/homeport"), "web"]

while True:
    try:
        if tmux("has-session", "-t", "magerbot", check=False).returncode:
            tmux(
                "new-session",
                "-d",
                "-s",
                "magerbot",
                "-n",
                "server",
                "-c",
                str(ROOT),
                *server,
            )
            tmux("set-option", "-g", "remain-on-exit", "on")
            tmux("set-option", "-t", "magerbot", "history-limit", "20000")
        windows = tmux(
            "list-windows",
            "-t",
            "magerbot",
            "-F",
            "#{window_name}|#{pane_dead}|#{pane_id}",
        ).stdout
        for name, command in [("server", server), ("worker", worker), ("web", web)]:
            found = next(
                (
                    line.split("|")
                    for line in windows.splitlines()
                    if line.split("|")[0] == name
                ),
                None,
            )
            if not found:
                tmux(
                    "new-window",
                    "-d",
                    "-t",
                    "magerbot",
                    "-n",
                    name,
                    "-c",
                    str(ROOT),
                    *command,
                )
            elif found[1] == "1":
                tmux("respawn-pane", "-t", found[2], "-c", str(ROOT), *command)
    except Exception as exc:
        print(f"supervisor: {exc}", flush=True)
    time.sleep(5)
