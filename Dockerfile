# Claude Code Remote Control host: an always-on container you can start
# Claude Code sessions in from the Claude mobile app or claude.ai/code.
FROM mirror.gcr.io/eclipse-temurin:21-jdk AS jdk

FROM mirror.gcr.io/library/debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG UID=1000
ARG GID=1000
ARG NODE_MAJOR=22
ARG REA_VERSION=6.4.0
# Set to false to skip Ghidra, GhidraMCP and the JDK (saves ~1.5 GB)
ARG INSTALL_GHIDRA=true
ARG GHIDRA_URL=https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip
ARG GHIDRA_SHA256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
ARG GHIDRAMCP_VERSION=7.0.0-rc.2
ARG GHIDRAMCP_ZIP_SHA256=62db94e2687c734c34c2a85c32bc1b25e44d1e98baeba8980f17f28032614a8f
ARG GHIDRAMCP_WHEEL_SHA256=c4769b3d640698f022c65a88b7a30b2ba03e3a9af287120be4a065def5d404bf

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget git openssh-client gnupg jq unzip zip ripgrep less vim-tiny \
      procps iproute2 iputils-ping dnsutils sudo tini tmux python3 python3-venv python3-pip \
      build-essential tshark chromium fonts-liberation fonts-noto-color-emoji smbclient \
 && curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# uv + Python CLI tools, installed system-wide so the home volume can't shadow them
ENV UV_TOOL_DIR=/opt/uv/tools UV_TOOL_BIN_DIR=/usr/local/bin UV_PYTHON_INSTALL_DIR=/opt/uv/python
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh \
 && uv tool install --python 3.13 serena-agent \
 && uv tool install semgrep \
 && chmod -R a+rX /opt/uv

# Node CLI tools
RUN npm install -g "rea-agents@${REA_VERSION}" && npm cache clean --force

# Ghidra (headless) + GhidraMCP headless server and its MCP bridge
COPY --from=jdk /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk GHIDRA_HOME=/opt/ghidra GHIDRA_INSTALL_DIR=/opt/ghidra
RUN if [ "$INSTALL_GHIDRA" = "true" ]; then set -e; \
      curl -fsSL -o /tmp/ghidra.zip "$GHIDRA_URL"; \
      echo "$GHIDRA_SHA256  /tmp/ghidra.zip" | sha256sum -c -; \
      unzip -q /tmp/ghidra.zip -d /opt; mv /opt/ghidra_*_PUBLIC /opt/ghidra; \
      base="https://github.com/bethington/ghidra-mcp/releases/download/v${GHIDRAMCP_VERSION}"; \
      curl -fsSL -o /tmp/ghidramcp.zip "$base/GhidraMCP-${GHIDRAMCP_VERSION}.zip"; \
      echo "$GHIDRAMCP_ZIP_SHA256  /tmp/ghidramcp.zip" | sha256sum -c -; \
      mkdir -p /opt/ghidramcp; unzip -q -j /tmp/ghidramcp.zip 'GhidraMCP/lib/*.jar' -d /opt/ghidramcp; \
      mv /opt/ghidramcp/GhidraMCP-*.jar /opt/ghidramcp/GhidraMCP.jar; \
      whl=ghidra_mcp_bridge-7.0.0-py3-none-any.whl; \
      curl -fsSL -o "/tmp/$whl" "$base/$whl"; \
      echo "$GHIDRAMCP_WHEEL_SHA256  /tmp/$whl" | sha256sum -c -; \
      uv tool install "/tmp/$whl"; chmod -R a+rX /opt/uv; \
      rm -f /tmp/*.zip /tmp/*.whl; \
    else rm -rf /opt/java/openjdk; fi

# Unprivileged user; match UID/GID to the owner of any host folders you mount
RUN groupadd -g "$GID" claude && useradd -m -u "$UID" -g "$GID" -s /bin/bash claude \
 && echo 'claude ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/claude \
 && chmod 0440 /etc/sudoers.d/claude \
 && mkdir -p /workspace && chown claude:claude /workspace

COPY entrypoint.sh merge-config.py /opt/claude-rc/
RUN chmod 0755 /opt/claude-rc/entrypoint.sh

USER claude
# Folder sessions run in; the Claude app labels remote sessions with its name
ENV RC_DIR=/workspace
ENV HOME=/home/claude PATH=/home/claude/.local/bin:/opt/java/openjdk/bin:/usr/local/bin:/usr/bin:/bin \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/claude-rc/entrypoint.sh"]
