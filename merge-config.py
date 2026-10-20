"""Merge /config/mcp-servers.json into ~/.claude.json and pre-trust /workspace.

/config/mcp-servers.local.json (git-ignored) is used instead when it exists.
Servers listed there overwrite same-named entries in
~/.claude.json; servers added by hand with `claude mcp add` are left alone.

${VAR} placeholders are filled from the container environment. A server that
references a variable which is unset or empty is skipped (and removed if it was
added earlier), so the example file works with only some services configured.
"""
import json
import os
import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\$\{(\w+)\}")

home = Path.home()
cfg_path = home / ".claude.json"
local_path = Path("/config/mcp-servers.local.json")
servers_path = Path(os.environ.get("MCP_SERVERS_FILE")
                    or (local_path if local_path.exists() else "/config/mcp-servers.json"))


def placeholders(value):
    if isinstance(value, str):
        return set(PLACEHOLDER.findall(value))
    if isinstance(value, list):
        return set().union(*map(placeholders, value)) if value else set()
    if isinstance(value, dict):
        return placeholders(list(value.values()))
    return set()


def expand(value):
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: os.environ[m.group(1)], value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
servers = cfg.setdefault("mcpServers", {})

if servers_path.exists():
    for name, server in json.loads(servers_path.read_text()).items():
        if name.startswith("_"):
            continue  # comment keys
        missing = sorted(v for v in placeholders(server) if not os.environ.get(v))
        if missing:
            print(f"[claude-rc] skipping MCP server {name}: unset {', '.join(missing)}")
            servers.pop(name, None)
            continue
        servers[name] = expand(server)
    print(f"[claude-rc] MCP servers: {', '.join(sorted(servers)) or 'none'}")
else:
    print(f"[claude-rc] {servers_path} not found; leaving MCP servers unchanged")

cfg["hasCompletedOnboarding"] = True
# Pre-answer "Enable Remote Control? (y/n)", which otherwise blocks on the unseen TTY
cfg["remoteDialogSeen"] = True
cfg.setdefault("projects", {}).setdefault("/workspace", {})["hasTrustDialogAccepted"] = True

tmp = cfg_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cfg, indent=2))
os.chmod(tmp, 0o600)
tmp.replace(cfg_path)
