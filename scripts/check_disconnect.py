"""Run on the laptop: abruptly close our SSH attachment and verify remote PIDs."""

import os
import pty
import subprocess
import time


def remote(command):
    return subprocess.check_output(
        ["ssh", "-o", "ControlMaster=no", "-o", "ControlPath=none", "macmini", command],
        text=True,
    ).strip()


panes = '/opt/homebrew/bin/tmux -L magerbot list-panes -a -F "#{window_name}:#{pane_pid}:#{pane_dead}"'
before = remote(panes)
master, slave = pty.openpty()
proc = subprocess.Popen(
    [
        "ssh",
        "-tt",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "macmini",
        "/opt/homebrew/bin/tmux -L magerbot attach -t magerbot",
    ],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    env={**os.environ, "TERM": "xterm-256color"},
)
os.close(slave)
try:
    time.sleep(2)
    assert proc.poll() is None, "SSH attachment exited prematurely"
    clients = remote(
        '/opt/homebrew/bin/tmux -L magerbot list-clients -F "#{client_pid}"'
    )
    assert clients, "No attached tmux client"
finally:
    proc.kill()  # abrupt transport loss, no graceful tmux detach
    proc.wait(timeout=10)
    os.close(master)
after = remote(panes)  # genuinely new SSH connection
assert before == after, (before, after)
print(
    "PASS: attached over SSH, killed that SSH connection, reconnected; all remote pane PIDs unchanged"
)
print(after)
