"""Merge /config/mcp-servers.json into ~/.claude.json and pre-trust $RC_DIR.

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
rc_dir = os.environ.get("RC_DIR") or "/workspace"
cfg.setdefault("projects", {}).setdefault(rc_dir, {})["hasTrustDialogAccepted"] = True

tmp = cfg_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cfg, indent=2))
os.chmod(tmp, 0o600)
tmp.replace(cfg_path)

# Approval rules (see README): "ask" rules and the guard.py hook from
# /config/permission-rules.json (or .local.json) go into ~/.claude/settings.json
# for the MCP servers configured above. The previous managed copies are replaced;
# rules and hooks added by hand are kept. Without a rules file they are removed.
rules_local = Path("/config/permission-rules.local.json")
rules_path = Path(os.environ.get("PERMISSION_RULES_FILE")
                  or (rules_local if rules_local.exists() else "/config/permission-rules.json"))
rules = json.loads(rules_path.read_text()) if rules_path.exists() else {}


def rx(name):  # escape for the hook matcher (a JS regex, so leave "-" alone)
    return re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", name)


ask, guarded = [], []
for name, group in rules.get("servers", {}).items():
    if name in servers:
        ask += [f"mcp__{name}__{t}" for t in rules.get("ask", {}).get(group, [])]
        guarded += [f"mcp__{rx(name)}__{'.*' if t == '*' else rx(t)}"
                    for t in rules.get("guard", {}).get(group, [])]

settings_path = home / ".claude" / "settings.json"
state_path = home / ".claude-rc" / "managed-permissions.json"
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
state = json.loads(state_path.read_text()) if state_path.exists() else {}
perms = settings.setdefault("permissions", {})
perms["ask"] = [r for r in perms.get("ask", []) if r not in set(state.get("ask", []))] + ask
if not perms["ask"]:
    del perms["ask"]
if rules.get("disableBypassPermissionsMode"):
    perms["disableBypassPermissionsMode"] = "disable"
elif state.get("disableBypassPermissionsMode"):
    perms.pop("disableBypassPermissionsMode", None)
guard = "python3 /opt/claude-rc/guard.py"
pre = [h for h in settings.get("hooks", {}).get("PreToolUse", [])
       if not any(x.get("command") == guard for x in h.get("hooks", []))]
if guarded:
    pre.append({"matcher": "|".join(guarded), "hooks": [{"type": "command", "command": guard}]})
if pre:
    settings.setdefault("hooks", {})["PreToolUse"] = pre
else:
    settings.get("hooks", {}).pop("PreToolUse", None)
if not settings.get("hooks", True):
    del settings["hooks"]
if not perms:
    del settings["permissions"]

settings_path.parent.mkdir(parents=True, exist_ok=True)
tmp = settings_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(settings, indent=2))
tmp.replace(settings_path)
state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps({"ask": ask, "disableBypassPermissionsMode": bool(rules.get("disableBypassPermissionsMode"))}))
print(f"[claude-rc] approval rules: {len(ask)} ask rules, guard hook on {len(guarded)} tool patterns")
