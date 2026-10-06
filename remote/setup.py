#!/usr/bin/env python3
"""Install using JSON configuration; user secrets are never sourced as shell."""
import json
import os
from pathlib import Path
import pwd
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
