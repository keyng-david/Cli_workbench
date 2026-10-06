#!/usr/bin/env python3
"""Install using JSON configuration; user secrets are never sourced as shell."""
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import time
import urllib.request
from state import BASE, CONFIG, DEV_HOME, State, dev_run, run

def write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)

def own_dev(path):
    uid, gid = pwd.getpwnam("dev").pw_uid, pwd.getpwnam("dev").pw_gid
    for directory, dirs, files in os.walk(path, followlinks=False):
        os.chown(directory, uid, gid, follow_symlinks=False)
        for name in dirs + files:
            os.chown(Path(directory) / name, uid, gid, follow_symlinks=False)

def stage(text):
    print('==> ' + text, flush=True)

def main():
    cfg = json.loads(CONFIG.read_text())
    packages = [f"@cloudcli-ai/cloudcli@{cfg['CLOUDCLI_VERSION']}",
                f"@openai/codex@{cfg['CODEX_VERSION']}", f"pnpm@{cfg['PNPM_VERSION']}"]
    stage('[5/8] Installing CloudCLI and Codex (takes a few minutes)')
    dev_run(["npm", "install", "--prefix", "/opt/workbench-packages", "--no-audit", "--no-fund", *packages], timeout=1800)
    for name in ("cloudcli", "codex", "pnpm"):
        link = Path("/usr/local/bin") / name
        link.unlink(missing_ok=True)
        link.symlink_to(Path("/opt/workbench-packages/node_modules/.bin") / name)
    stage('[6/8] Restoring/initialising encrypted backup storage')
    state = State(cfg)
    state.restore()
    for name in (".codex", ".cloudcli", ".config/gh"):
        (DEV_HOME / name).mkdir(parents=True, exist_ok=True)
    config_path = DEV_HOME / ".codex/config.toml"
    if not config_path.exists():
        write(config_path, 'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\ncli_auth_credentials_store = "file"\n')
    own_dev(DEV_HOME)
    if cfg.get("OPENAI_API_KEY"):
        dev_run(["codex", "login", "--with-api-key"], input=cfg["OPENAI_API_KEY"] + "\n", timeout=60)
    if cfg.get("GH_TOKEN"):
        dev_run(["gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--with-token"], input=cfg["GH_TOKEN"] + "\n", timeout=60)
        dev_run(["gh", "auth", "setup-git"], timeout=30)
    stage('[7/8] Configuring services, firewall and swap')
    if cfg.get("GIT_USER_NAME"):
        dev_run(["git", "config", "--global", "user.name", cfg["GIT_USER_NAME"]], timeout=30)
    if cfg.get("GIT_USER_EMAIL"):
        dev_run(["git", "config", "--global", "user.email", cfg["GIT_USER_EMAIL"]], timeout=30)
    for repo in [r.strip() for r in cfg.get("CLONE_REPOS", "").split(",") if r.strip()]:
        owner, _, name = repo.partition("/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+", repo) or name in (".", ".."):
            stage(f"Skipping invalid CLONE_REPOS entry: {repo}")
            continue
        target = Path("/workspace") / name
        if (target / ".git").exists():
            continue
        stage(f"Cloning {repo} into {target}")
        result = subprocess.run(
            ["runuser", "-u", "dev", "--", "env", "HOME=/home/dev", "GIT_TERMINAL_PROMPT=0",
             "git", "clone", "--", f"https://github.com/{repo}.git", str(target)],
            cwd="/workspace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900)
        with (BASE / "clone.log").open("a") as log:
            if result.returncode:
                lines = (result.stderr or "").strip().splitlines()
                reason = lines[-1] if lines else f"exit {result.returncode}"
                token = cfg.get("GH_TOKEN")
                reason = reason.replace(token, "***") if token else reason
                log.write(f"FAILED {repo}: {reason}\n")
                stage(f"WARNING: could not clone {repo}: {reason}")
            else:
                log.write(f"cloned {repo} -> {target}\n")
    unit = """[Unit]
Description=CLI Workbench CloudCLI
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=dev
Group=dev
WorkingDirectory=/workspace
Environment=HOME=/home/dev
Environment=HOST=127.0.0.1
Environment=PORT=3001
Environment=WORKSPACES_ROOT=/workspace
Environment=DATABASE_PATH=/home/dev/.cloudcli/auth.db
Environment=NODE_ENV=production
ExecStart=/usr/local/bin/cloudcli
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
"""
    write(Path("/etc/systemd/system/workbench-cloudcli.service"), unit, 0o644)
    if cfg["ACCESS_MODE"] == "cloudflare":
        write(Path("/etc/cli-workbench/tunnel-token"), cfg["CLOUDFLARE_TUNNEL_TOKEN"])
        write(Path("/etc/systemd/system/workbench-tunnel.service"), """[Unit]
Description=CLI Workbench Cloudflare Tunnel
After=network-online.target workbench-cloudcli.service
Wants=network-online.target
[Service]
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token-file /etc/cli-workbench/tunnel-token
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
[Install]
WantedBy=multi-user.target
""", 0o644)
    write(Path("/etc/ssh/sshd_config.d/00-workbench.conf"), "PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n", 0o644)
    run(["sshd", "-t"])
    run(["systemctl", "reload", "ssh"])
    run(["ufw", "default", "deny", "incoming"])
    run(["ufw", "default", "allow", "outgoing"])
    run(["ufw", "allow", "from", cfg["SSH_SOURCE_CIDR"], "to", "any", "port", "22", "proto", "tcp"])
    run(["ufw", "--force", "enable"])
    if cfg.get("RELAX_USERNS_RESTRICTION", "true") == "true":
        # Ubuntu 24.04 blocks Codex's bubblewrap sandbox ("bwrap: loopback: Failed RTM_NEWADDR")
        # unless unprivileged user namespaces are allowed. Applies to this disposable single-purpose VM only.
        write(Path("/etc/sysctl.d/60-workbench-userns.conf"), "kernel.apparmor_restrict_unprivileged_userns=0\n", 0o644)
        try:
            run(["sysctl", "--system"])
        except RuntimeError:
            stage("WARNING: could not apply the user-namespace setting; Codex sandbox may fail")
    swap = int(cfg["SWAP_MB"])
    if swap:
        if not Path("/swapfile").exists():
            run(["fallocate", "-l", f"{swap}M", "/swapfile"])
        Path("/swapfile").chmod(0o600)
        if "/swapfile" not in run(["swapon", "--show=NAME", "--noheadings"]).split():
            run(["mkswap", "/swapfile"])
            run(["swapon", "/swapfile"])
        if "/swapfile " not in Path("/etc/fstab").read_text():
            with Path("/etc/fstab").open("a") as stream:
                stream.write("\n/swapfile none swap sw 0 0\n")
    if cfg["INSTALL_BROWSER"] == "true":
        version = cfg["PLAYWRIGHT_VERSION"]
        dev_run(["npm", "install", "--prefix", "/opt/workbench-packages", f"playwright@{version}"], timeout=1200)
        run(["node", "/opt/workbench-packages/node_modules/playwright/cli.js", "install-deps", "chromium"], timeout=1200)
        dev_run(["node", "/opt/workbench-packages/node_modules/playwright/cli.js", "install", "chromium"], timeout=1200)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "workbench-cloudcli"])
    if cfg["ACCESS_MODE"] == "cloudflare":
        run(["systemctl", "enable", "workbench-tunnel"])
    stage('[8/8] Starting services and waiting for health check')
    state.services("start")
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:3001/health", timeout=3) as response:
                if response.status == 200:
                    (BASE / "ready").write_text("ok\n")
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("CloudCLI health check failed; inspect systemd logs")

if __name__ == "__main__":
    main()
