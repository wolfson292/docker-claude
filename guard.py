#!/usr/bin/env python3
"""PreToolUse hook: force an approval prompt for destructive calls on multi-purpose MCP tools.

Whole tools that are always destructive get plain "ask" rules in settings.json
(written by merge-config.py from /config/permission-rules.json). This hook covers
tools that mix reads and writes, where the decision depends on the arguments
(HTTP method, action, service): settings rules can't match MCP arguments.
Prints an "ask" decision for writes; prints nothing (normal flow) for reads.
Tools are recognised by name whatever their server is called.
"""
import json
import re
import sys

READ_METHODS = {"GET", "HEAD"}
UNIFI_READ = re.compile(r"(unifi|protect)_(get|list|lookup|recent|subscribe|tool_index|batch_status|load_tools|export_clip|detection_search_labels|search_detections)")
HA_SERVICE_ASK = {
    ("homeassistant", "restart"), ("homeassistant", "stop"),
    ("recorder", "purge"), ("recorder", "purge_entities"), ("recorder", "disable"),
}
HA_DOMAIN_ASK = {"hassio", "backup", "update"}


def reason(tool, args):
    """Return why this call needs approval, or None if it can run freely."""
    t = tool.split("__")[-1]
    if t in ("docker_proxy", "kubernetes_proxy"):
        m = str(args.get("method") or "GET").upper()
        return None if m in READ_METHODS else f"{m} {args.get('path')} through Portainer"
    if t == "ha_manage_backup":
        a, s = args.get("action"), args.get("scope")
        if a == "delete" or (a == "restore" and s == "snapshot"):
            return f"HA backup {s} {a}"
        return None
    if t == "ha_manage_updates":
        return "HA update install" if args.get("action") == "install" else None
    if t == "ha_manage_hacs":
        return None if args.get("action") == "update_information" else f"HACS {args.get('action')}"
    if t == "ha_manage_app":
        a = args.get("action")
        if a in (None, "", "start", "check_updates"):
            cfg = [k for k in ("options", "boot", "auto_update", "watchdog", "network") if args.get(k) not in (None, {}, "")]
            if cfg:
                return f"HA app config change ({', '.join(cfg)})"
            if args.get("array_patch") or (args.get("path") and str(args.get("method") or "GET").upper() not in READ_METHODS):
                return f"HA app API write {args.get('method')} {args.get('path')}"
            if args.get("websocket"):
                return "HA app WebSocket command"
            return None
        return f"HA app {a} {args.get('slug') or args.get('repository') or ''}".strip()
    if t == "ha_call_service":
        if args.get("ws_command"):
            return f"raw HA WebSocket command {args.get('ws_command')}"
        d, s = args.get("domain"), args.get("service")
        if d in HA_DOMAIN_ASK or (d, s) in HA_SERVICE_ASK:
            return f"HA service {d}.{s}"
        return None
    if t in ("unifi_execute", "protect_execute"):
        inner = str(args.get("tool") or "")
        return None if UNIFI_READ.match(inner) else f"UniFi write {inner}"
    if t in ("unifi_batch", "protect_batch"):
        writes = [str(o.get("tool")) for o in args.get("operations") or [] if not UNIFI_READ.match(str(o.get("tool") or ""))]
        return f"UniFi batch writes {', '.join(writes)}" if writes else None
    if t.startswith(("unifi_", "protect_")):  # tools registered directly via *_load_tools
        return None if UNIFI_READ.match(t) else f"UniFi write {t}"
    return None


def main():
    try:
        event = json.load(sys.stdin)
        why = reason(event.get("tool_name", ""), event.get("tool_input") or {})
    except Exception as e:  # fail closed: a crash here must not let the call run unprompted
        why = f"guard.py error ({type(e).__name__}: {e})"
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Needs approval: {why}",
        }}))


if __name__ == "__main__":
    main()
