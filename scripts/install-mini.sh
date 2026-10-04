#!/bin/zsh
set -eu
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
cd "${0:A:h:h}"
uv sync --locked
mkdir -p "$HOME/.config/magerbot" "$HOME/.local/state/magerbot" "$HOME/Library/LaunchAgents" "$HOME/.local/bin"
chmod 700 "$HOME/.config/magerbot" "$HOME/.local/state/magerbot"
.venv/bin/python - <<'PY'
from pathlib import Path
import json, plistlib
root = Path.cwd()
home = Path.home()
config = home / '.config/magerbot/config.json'
if not config.exists():
    config.write_text(json.dumps({'cwd': str(root)}, indent=2) + '\n')
    config.chmod(0o600)
plist = {'Label': 'com.magerbot.harness', 'ProgramArguments': [str(root / '.venv/bin/python'), str(root / 'scripts/supervise.py')],
    'WorkingDirectory': str(root), 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
    'StandardOutPath': str(home / '.local/state/magerbot/supervisor.log'),
    'StandardErrorPath': str(home / '.local/state/magerbot/supervisor.error.log')}
(home / 'Library/LaunchAgents/com.magerbot.harness.plist').write_bytes(plistlib.dumps(plist))
for name in ('homeport', 'magerbot'):
    link = home / '.local/bin' / name
    if not link.exists():
        link.symlink_to(root / '.venv/bin' / name)
PY
# GUI domain is appropriate for a LaunchAgent; fall back to the current SSH user domain.
domain="gui/$(id -u)"
launchctl print "$domain" >/dev/null 2>&1 || domain="user/$(id -u)"
if ! launchctl print "$domain/com.magerbot.harness" >/dev/null 2>&1; then
  launchctl bootstrap "$domain" "$HOME/Library/LaunchAgents/com.magerbot.harness.plist"
fi
print "Installed into $domain. Attach: tmux -L magerbot attach -t magerbot"
