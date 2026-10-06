"""Strict, non-executable dotenv configuration."""
import os
import re
import ipaddress
from pathlib import Path

class Error(RuntimeError):
    pass

DEFAULTS = {
    "WORKBENCH_NAME": "cli-workbench", "CLOUD_PROVIDER": "hetzner",
    "AGENTS": "codex", "HCLOUD_SERVER_TYPE": "cpx32",
    "HCLOUD_LOCATION": "nbg1", "HCLOUD_IMAGE": "ubuntu-24.04",
    "SSH_PRIVATE_KEY": "~/.ssh/id_ed25519", "SSH_SOURCE_CIDR": "0.0.0.0/0",
    "ACCESS_MODE": "cloudflare", "PUBLIC_HOSTNAME": "",
    "CLOUDFLARE_TUNNEL_TOKEN": "", "ACCESS_POLICY_CONFIRMED": "false",
    "CLOUDCLI_VERSION": "1.37.3", "CODEX_VERSION": "0.156.1",
    "PNPM_VERSION": "10.17.1", "OPENAI_API_KEY": "", "GH_TOKEN": "",
    "RESTORE_MODE": "auto", "RESTIC_INIT": "false",
    "PERSIST_CODEX_AUTH": "false", "AWS_DEFAULT_REGION": "auto",
    "INSTALL_BROWSER": "false", "PLAYWRIGHT_VERSION": "1.55.1",
    "SWAP_MB": "2048", "WAIT_SECONDS": "1200",
    "RELAX_USERNS_RESTRICTION": "true", "GIT_USER_NAME": "", "GIT_USER_EMAIL": "", "CLONE_REPOS": "",
}
REQUIRED = {"HCLOUD_TOKEN", "HCLOUD_SSH_KEY_ID", "RESTIC_REPOSITORY",
            "RESTIC_PASSWORD", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
REMOTE_KEYS = (set(DEFAULTS) | REQUIRED) - {
    "HCLOUD_TOKEN", "HCLOUD_SSH_KEY_ID", "SSH_PRIVATE_KEY",
    "HCLOUD_SERVER_TYPE", "HCLOUD_LOCATION", "HCLOUD_IMAGE", "WAIT_SECONDS",
}

REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")

def parse_repos(value):
    """CLONE_REPOS: comma-separated owner/repo names, validated so they can never act as options."""
    repos = [item.strip() for item in value.split(",") if item.strip()]
    for repo in repos:
        if not REPO.fullmatch(repo) or repo.split("/")[1] in (".", ".."):
            raise Error(f"CLONE_REPOS entry must look like owner/repo: {repo}")
    return repos

def read_env(path):
    values = {}
    for number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise Error(f"Invalid configuration at line {number}")
        if key in values:
            raise Error(f"Duplicate configuration key: {key}")
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise Error(f"Unclosed quote at line {number}")
            value = value[1:-1]
        values[key] = value
    return values

def load(path, full=True):
    values = read_env(path)
    unknown = values.keys() - (DEFAULTS.keys() | REQUIRED)
    if unknown:
        raise Error("Unknown configuration keys: " + ", ".join(sorted(unknown)))
    cfg = DEFAULTS | values
    cfg.update({k: os.environ[k] for k in DEFAULTS.keys() | REQUIRED if k in os.environ})
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,39}", cfg["WORKBENCH_NAME"]):
        raise Error("WORKBENCH_NAME must be 3-40 lowercase letters, digits or hyphens")
    if cfg["CLOUD_PROVIDER"] != "hetzner" or cfg["AGENTS"] != "codex":
        raise Error("This release implements CLOUD_PROVIDER=hetzner and AGENTS=codex only")
    for key in ("ACCESS_POLICY_CONFIRMED", "RESTIC_INIT", "PERSIST_CODEX_AUTH", "INSTALL_BROWSER", "RELAX_USERNS_RESTRICTION"):
        if cfg[key] not in ("true", "false"):
            raise Error(f"{key} must be true or false")
    for key in ("CLOUDCLI_VERSION", "CODEX_VERSION", "PNPM_VERSION", "PLAYWRIGHT_VERSION"):
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", cfg[key]):
            raise Error(f"{key} must be an exact version")
    for key, low, high in (("SWAP_MB", 0, 8192), ("WAIT_SECONDS", 30, 7200)):
        if not cfg[key].isdigit() or not low <= int(cfg[key]) <= high:
            raise Error(f"{key} must be between {low} and {high}")
    parse_repos(cfg["CLONE_REPOS"])
    if cfg["ACCESS_MODE"] not in ("cloudflare", "ssh"):
        raise Error("ACCESS_MODE must be cloudflare or ssh")
    if cfg["RESTORE_MODE"] not in ("fresh", "auto"):
        raise Error("RESTORE_MODE must be fresh or auto")
    if full:
        missing = [k for k in sorted(REQUIRED) if not cfg.get(k)]
        if missing:
            raise Error("Missing configuration: " + ", ".join(missing))
        if not cfg["HCLOUD_SSH_KEY_ID"].isdigit():
            raise Error("HCLOUD_SSH_KEY_ID must be a numeric key ID")
        if not cfg["RESTIC_REPOSITORY"].startswith("s3:https://"):
            raise Error("RESTIC_REPOSITORY must use s3:https://endpoint/bucket/prefix")
        if len(cfg["RESTIC_PASSWORD"]) < 20:
            raise Error("Use a random RESTIC_PASSWORD of at least 20 characters")
        if cfg["ACCESS_MODE"] == "cloudflare":
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", cfg["PUBLIC_HOSTNAME"]):
                raise Error("Set PUBLIC_HOSTNAME without https:// or a path")
            if not cfg["CLOUDFLARE_TUNNEL_TOKEN"] or cfg["ACCESS_POLICY_CONFIRMED"] != "true":
                raise Error("Configure the tunnel and Access policy before setting ACCESS_POLICY_CONFIRMED=true")
        try:
            ipaddress.ip_network(cfg["SSH_SOURCE_CIDR"], strict=False)
        except ValueError as exc:
            raise Error("SSH_SOURCE_CIDR must be a CIDR network") from exc
        if not Path(cfg["SSH_PRIVATE_KEY"]).expanduser().is_file():
            raise Error("SSH_PRIVATE_KEY does not exist")
    return cfg
