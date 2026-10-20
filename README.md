# docker-claude

An always-on Docker container running
[Claude Code Remote Control](https://code.claude.com/docs/en/remote-control),
so you can start and drive Claude Code sessions on a home server from the
Claude mobile app or [claude.ai/code](https://claude.ai/code).

It comes with a set of MCP servers that work headless in Linux, plus optional
SMB mounts (e.g. Home Assistant `/config` via the Samba share app) so
Claude can work on those files directly.

## What's inside

| Tool | Notes |
| --- | --- |
| Claude Code | Installed into the persistent home volume on first start; auto-updates. |
| Node 22, Python 3 + [uv](https://docs.astral.sh/uv/) | For `npx` / `uvx` MCP servers. |
| Chromium | Headless, for the Playwright and Chrome DevTools MCP servers. |
| tshark | For the Wireshark MCP server. |
| semgrep, serena, rea | Preinstalled CLI MCP servers. |
| Ghidra 12.1.4 + [GhidraMCP](https://github.com/bethington/ghidra-mcp) headless server | Optional (`INSTALL_GHIDRA=false` to skip). Runs on `127.0.0.1:8089` inside the container. |

MCP servers are defined in [`config/mcp-servers.json`](config/mcp-servers.json):
context7, deepwiki, playwright, chrome-devtools, semgrep, serena, wireshark,
ghidra, rea, two Home Assistant instances ([ha-mcp](https://github.com/homeassistant-ai/ha-mcp)),
Portainer, UniFi Network and UniFi Protect. Any server whose `${VARIABLES}`
aren't set in `.env` is skipped, so you only configure what you use.
MCP connectors attached to your claude.ai account appear automatically once you log in.

## Setup

```bash
git clone https://github.com/wolfson292/docker-claude.git
cd docker-claude
cp .env.example .env && chmod 600 .env
$EDITOR .env
docker compose up -d --build
```

### Log in (once)

Remote Control needs a claude.ai subscription login. API keys and
`claude setup-token` tokens aren't supported. The container waits until you log in:

```bash
docker exec -it claude-rc claude auth login
```

Open the URL it prints, approve, and paste the code back. Credentials are kept
in `data/home`, so restarts don't need a new login. Within ~30 s the container
starts `claude remote-control`. Then open the Claude app, go to **Code**, and
pick the environment named after `RC_NAME`.

Check status with `docker logs -f claude-rc`, or attach to the remote-control
UI with `docker attach claude-rc` (detach with `Ctrl-P Ctrl-Q`).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RC_NAME` | `claude-rc` | Environment name shown in the Claude app. |
| `RC_PERMISSION_MODE` | `default` | Permission mode for spawned sessions (`default`, `acceptEdits`, `auto`, `plan`, `dontAsk`, `bypassPermissions`). |
| `RC_SPAWN` | `same-dir` | `same-dir`, `worktree` (needs a git repo in `RC_DIR`) or `session`. |
| `RC_DIR` | `/workspace` | Folder sessions run in (inside the container). The Claude app labels each remote session with this folder's name, so pick something meaningful, e.g. `/home-lab`. |
| `RC_EXTRA_ARGS` | | Extra flags for `claude remote-control`. |
| `PUID` / `PGID` | `1000` | UID/GID of the `claude` user (build arg) and of mounted SMB files. |
| `INSTALL_GHIDRA` | `true` | Build arg; `false` drops Ghidra, GhidraMCP and the JDK. |
| `GHIDRA_MCP_ENABLED` | `true` | Runtime switch for the GhidraMCP headless server. |
| `GHIDRA_JAVA_OPTS` | `-Xmx4g -XX:+UseG1GC` | JVM options for GhidraMCP. |
| `DATA_DIR` | `./data` | Where `home/` and `workspace/` are stored. |

### MCP servers

Edit `config/mcp-servers.json`, or copy it to `config/mcp-servers.local.json`
(git-ignored, used instead when present) to keep personal changes out of git.
Put secrets in `.env` and reference them as `${NAME}`. The file is merged into
`~/.claude.json` on every start; servers you add by hand with
`docker exec -it claude-rc claude mcp add ...` are kept.

Skills placed in `config/skills/<name>/SKILL.md` are copied into `~/.claude/skills` at start.

### SMB / Home Assistant config mounts

Enable the overlay and fill in the `SMB1_*` / `SMB2_*` variables:

```bash
# .env
COMPOSE_FILE=docker-compose.yml:docker-compose.samba.yml
SMB1_NAME=ha-home
SMB1_SHARE=//192.0.2.10/config
SMB1_USERNAME=homeassistant
SMB1_PASSWORD=...
```

Each share appears at `$RC_DIR/<SMBn_NAME>`. For Home Assistant, install the
**Samba share** app and enable the `config` share. Its `allow_hosts` must
include the Docker host's address. The host needs CIFS support
(`apt install cifs-utils`).

## Security notes

- Everything Claude does from the app runs inside this container, with
  passwordless `sudo` inside it, network access to your LAN, and write access to
  mounted shares. Choose `RC_PERMISSION_MODE` with that in mind.
- `.env` values are visible to processes in the container (and so to Claude).
  Use scoped, least-privilege tokens where the service allows it.
- Nothing listens on the network: Remote Control connects outbound to Anthropic.
  The GhidraMCP server binds to `127.0.0.1` only.
- Images are pulled through `mirror.gcr.io` to avoid Docker Hub's anonymous rate limit.

## License

[GPL-3.0](LICENSE). Ghidra, GhidraMCP and the other tools the image downloads keep their own licenses.
