#!/bin/bash
# Installs/updates Claude Code, applies /config, starts the GhidraMCP headless
# server (if installed), waits for a Claude login, then runs remote control.
set -uo pipefail

log() { echo "[claude-rc] $*"; }

# Claude Code lives in the persistent home volume so its auto-updates stick.
if [ ! -x "$HOME/.local/bin/claude" ]; then
  log "installing Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash
fi

python3 /opt/claude-rc/merge-config.py

# Skills shipped in /config/skills are copied into ~/.claude/skills
if [ -d /config/skills ]; then
  mkdir -p "$HOME/.claude/skills"
  cp -a /config/skills/. "$HOME/.claude/skills/"
fi

# GhidraMCP headless server on localhost only (used by the ghidra MCP bridge)
if [ -f /opt/ghidramcp/GhidraMCP.jar ] && [ "${GHIDRA_MCP_ENABLED:-true}" = "true" ]; then
  mkdir -p "$HOME/.cache/ghidra-mcp" "$HOME/ghidra-projects"
  CP=/opt/ghidramcp/GhidraMCP.jar
  for jar in "$GHIDRA_HOME"/Ghidra/{Framework,Features,Processors}/*/lib/*.jar; do CP="$CP:$jar"; done
  (
    cd "$HOME/ghidra-projects"
    while true; do
      java ${GHIDRA_JAVA_OPTS:--Xmx4g -XX:+UseG1GC} -Dghidra.home="$GHIDRA_HOME" \
        -Dapplication.name=GhidraMCP -classpath "$CP" \
        com.xebyte.headless.GhidraMCPHeadlessServer --bind 127.0.0.1 --port 8089 \
        >>"$HOME/.cache/ghidra-mcp/server.log" 2>&1
      echo "ghidra-mcp exited ($?), restarting in 30s" >>"$HOME/.cache/ghidra-mcp/server.log"
      sleep 30
    done
  ) &
fi

cd /workspace

logged_in() { claude auth status --json 2>/dev/null | jq -e '.loggedIn == true' >/dev/null; }
until logged_in; do
  log "not logged in. Run: docker exec -it ${CONTAINER_NAME:-claude-rc} claude auth login"
  sleep 30
done

log "starting remote control"
exec claude remote-control \
  --name "${RC_NAME:-claude-rc}" \
  --remote-control-session-name-prefix "${RC_NAME:-claude-rc}" \
  --permission-mode "${RC_PERMISSION_MODE:-default}" \
  --spawn "${RC_SPAWN:-same-dir}" \
  ${RC_EXTRA_ARGS:-}
