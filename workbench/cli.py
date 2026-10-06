"""Phone/laptop controller. Secrets travel over SSH stdin, never argv."""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from .config import Error, REMOTE_KEYS, load, parse_repos
from .hetzner import Hetzner

ROOT = Path(__file__).resolve().parents[1]

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
    tmp.replace(path)

def validate_server(server, name, instance=None):
    labels = server.get("labels", {})
    if labels.get("managed-by") != "cli-workbench" or labels.get("workbench") != name:
        raise Error("Server ownership labels do not match; refusing operation")
    if not labels.get("instance") or (instance and labels["instance"] != instance):
        raise Error("Server instance identity does not match")
    return server

def validate_receipt(receipt, server, nonce):
    if (receipt.get("server_id") != server["id"] or receipt.get("nonce") != nonce
            or receipt.get("instance") != server["labels"]["instance"]
            or receipt.get("verified") is not True
            or len(receipt.get("snapshot", "")) != 64):
        raise Error("Backup receipt is invalid; refusing deletion")

def notify(title, text):
    """Best-effort Termux notification (needs the termux-api package and app)."""
    exe = shutil.which("termux-notification")
    if exe:
        try:
            subprocess.run([exe, "--title", title, "--content", text], timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass

class Controller:
    def __init__(self, cfg, state_dir):
        self.cfg, self.dir = cfg, state_dir
        self.api = Hetzner(cfg["HCLOUD_TOKEN"])
        self.state_path = state_dir / "instance.json"

    def state(self):
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {}

    def current(self):
        servers = self.api.servers(self.cfg["WORKBENCH_NAME"])
        if len(servers) > 1:
            raise Error("Multiple matching servers found; resolve in Hetzner Console")
        if not servers:
            return None
        server = validate_server(servers[0], self.cfg["WORKBENCH_NAME"], self.state().get("instance"))
        write_json(self.state_path, {"id": server["id"], "instance": server["labels"]["instance"]})
        return server

    def ssh_args(self, server):
        ip = server["public_net"]["ipv4"]["ip"]
        if not ip:
            raise Error("Server has no IPv4 address yet")
        return ["ssh", "-i", str(Path(self.cfg["SSH_PRIVATE_KEY"]).expanduser()),
                "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
                "-o", "StrictHostKeyChecking=accept-new", "-o",
                "UserKnownHostsFile=" + str(self.dir / (str(server["id"]) + "-known_hosts")),
                "root@" + ip]

    def ssh(self, server, command, data=None, capture=True, timeout=3600):
        result = subprocess.run(self.ssh_args(server) + [command], input=data,
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None, timeout=timeout)
        if result.returncode:
            lines = (result.stderr or b"").decode(errors="replace").strip().splitlines()
            reason = f": {lines[-1]}" if lines else ""
            raise Error(f"Remote command failed (exit {result.returncode}){reason}")
        return result.stdout.decode() if capture else ""

    def remote(self, server, action, *args):
        return self.ssh(server, shlex.join(["python3", "/opt/cli-workbench/remote/state.py", action, *args]))

    def deploy(self, server):
        config = {k: self.cfg[k] for k in REMOTE_KEYS if k in self.cfg}
        config.update(server_id=server["id"], instance=server["labels"]["instance"])
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for file in sorted((ROOT / "remote").glob("*")):
                if file.is_file() and file.suffix in (".py", ".sh"):
                    archive.add(file, arcname="remote/" + file.name)
            raw = json.dumps(config).encode()
            info = tarfile.TarInfo("config.json")
            info.size, info.mode = len(raw), 0o600
            archive.addfile(info, io.BytesIO(raw))
        self.ssh(server, "umask 077; mkdir -p /opt/cli-workbench; tar xzf - -C /opt/cli-workbench", buffer.getvalue())
        self.ssh(server, "systemd-run --unit=workbench-bootstrap --collect /bin/bash /opt/cli-workbench/remote/bootstrap.sh")
        print("Bootstrap now runs under systemd and continues if Termux closes.", flush=True)

    def check_key(self):
        """Free pre-flight: the local private key must match the Hetzner key the server will trust."""
        path = Path(self.cfg["SSH_PRIVATE_KEY"]).expanduser()
        try:
            result = subprocess.run(["ssh-keygen", "-y", "-P", "", "-f", str(path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        except FileNotFoundError:
            raise Error("ssh-keygen not found; install OpenSSH (Termux: pkg install openssh)") from None
        if result.returncode:
            raise Error(f"Cannot read {path}: it is passphrase-protected or not a valid private key. "
                        "Create a dedicated key with an EMPTY passphrase (see docs/credentials.md Part B)")
        local = result.stdout.decode().split()[:2]
        remote = self.api.ssh_key(self.cfg["HCLOUD_SSH_KEY_ID"]).get("public_key", "").split()[:2]
        if not local or local != remote:
            raise Error(f"HCLOUD_SSH_KEY_ID {self.cfg['HCLOUD_SSH_KEY_ID']} is a different key from {path}. "
                        "Upload this key's .pub file in Hetzner (Security > SSH keys), put its ID in .env, then retry")
        print(f"SSH key OK: {path.name} matches Hetzner key {self.cfg['HCLOUD_SSH_KEY_ID']}.")

    def check_github(self):
        """Free pre-flight: can GH_TOKEN (or no token, for public repos) see every CLONE_REPOS entry?"""
        repos, token = parse_repos(self.cfg["CLONE_REPOS"]), self.cfg["GH_TOKEN"]
        if not repos:
            print("CLONE_REPOS is empty; nothing to clone.")
            return
        problems = []
        for repo in repos:
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "cli-workbench"}
            if token:
                headers["Authorization"] = "Bearer " + token
            try:
                with urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/" + repo, headers=headers), timeout=30) as response:
                    info = json.loads(response.read())
                access = "read and write" if info.get("permissions", {}).get("push") else "read only"
                print(f"OK {repo}: visible, {access}" + ("" if token else " (no GH_TOKEN: public access only)"))
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    problems.append(f"{repo}: GH_TOKEN was rejected (typo, expired or revoked)")
                elif exc.code == 404:
                    problems.append(f"{repo}: not found" + (" or this token has no access to it. Add the repository to the token's Repository access" if token else ", or it is private and GH_TOKEN is empty"))
                else:
                    problems.append(f"{repo}: GitHub returned HTTP {exc.code}")
            except (urllib.error.URLError, TimeoutError) as exc:
                raise Error("Could not reach GitHub to check CLONE_REPOS") from exc
        if problems:
            raise Error("CLONE_REPOS check failed:\n  " + "\n  ".join(problems))

    def start(self):
        server = self.current()
        if server is None:
            if self.state().get("instance") and not self.state().get("id"):
                raise Error("Previous create outcome is unknown. Inspect Hetzner Console; if no server exists, remove .workbench/<name>/instance.json before retrying")
            self.check_key()
            self.check_github()
            instance = uuid.uuid4().hex
            write_json(self.state_path, {"instance": instance})
            print("Creating Hetzner server. Billing begins when allocated.", flush=True)
            server = self.api.create(self.cfg, instance)
            write_json(self.state_path, {"id": server["id"], "instance": instance})
        print(f"Server {server['id']}: waiting for SSH/bootstrap. Re-run start if interrupted.", flush=True)
        begin = time.monotonic()
        deadline = begin + int(self.cfg["WAIT_SECONDS"])
        deployed, last, last_print = False, None, 0.0

        def report(message):
            nonlocal last, last_print
            now = time.monotonic()
            if message != last or now - last_print >= 30:
                elapsed = int(now - begin)
                print(f"[{elapsed // 60:02d}:{elapsed % 60:02d}] {message}", flush=True)
                last, last_print = message, now

        probe = ("if test -f /var/lib/cli-workbench/ready; then echo ready; "
                 "elif systemctl is-active --quiet workbench-bootstrap; then echo \"installing|$(journalctl -u workbench-bootstrap -o cat --no-pager 2>/dev/null | grep '^==> ' | tail -1)\"; "
                 "elif test -f /opt/cli-workbench/config.json; then echo failed; else echo empty; fi")
        while time.monotonic() < deadline:
            try:
                server = self.api.get(server["id"])
            except Error as exc:
                if "HTTP 404" in str(exc):
                    self.state_path.unlink(missing_ok=True)
                    raise Error("The server no longer exists (deleted outside this tool). State cleared; run start to create a new one") from None
                raise
            validate_server(server, self.cfg["WORKBENCH_NAME"], self.state()["instance"])
            if server.get("status") != "running":
                report(f"Hetzner server status: {server.get('status')}")
                time.sleep(5)
                continue
            try:
                status = self.ssh(server, probe, timeout=20).strip()
            except (Error, subprocess.TimeoutExpired) as exc:
                reason = "timed out" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
                hint = ""
                if time.monotonic() - begin > 180 and "Permission denied" in reason:
                    hint = " (the SSH key does not match HCLOUD_SSH_KEY_ID; run destroy and fix the key)"
                report(f"Server is up; SSH not ready yet: {reason}{hint}")
                time.sleep(5)
                continue
            kind, _, detail = status.partition("|")
            if kind == "ready":
                report("Installed.")
                notify("Workbench ready", self.cfg["PUBLIC_HOSTNAME"] or "Run tunnel")
                try:
                    info = json.loads(self.remote(server, "status"))
                    for repo in info.get("workspace_repos", []):
                        print(f"Repo ready: {repo['path']} ({repo.get('branch', '?')}, {repo.get('tracked_files', '?')} files)")
                    for line in info.get("clone_log", []):
                        if line.startswith("FAILED"):
                            print("WARNING " + line)
                except (Error, ValueError, subprocess.SubprocessError):
                    pass
                print("Run status for current service health.")
                print("https://" + self.cfg["PUBLIC_HOSTNAME"] if self.cfg["ACCESS_MODE"] == "cloudflare" else "Run 'python3 workbench.py tunnel', then open http://localhost:3001")
                return
            if kind == "failed":
                notify("Workbench install failed", "Run logs")
                raise Error("Bootstrap incomplete/failed. Run logs, then retry-bootstrap after fixing the cause")
            if kind == "empty" and not deployed:
                report("SSH connected. Uploading installer...")
                self.deploy(server)
                deployed = True
            elif kind == "installing":
                report("Installing: " + (detail.replace("==> ", "") or "starting"))
            time.sleep(5)
        raise Error("Startup wait expired; server still bills. Re-run start/status; do not create a duplicate")

    def destroy(self, server, args):
        if args.confirm != self.cfg["WORKBENCH_NAME"]:
            raise Error("Pass --confirm " + self.cfg["WORKBENCH_NAME"])
        if args.discard_unbacked:
            if args.confirm_id != str(server["id"]):
                raise Error("Discarding state requires --confirm-id " + str(server["id"]))
            print("Explicitly discarding all unbacked server data.", flush=True)
        else:
            if not args.quiesce:
                raise Error("Finish tasks and push code, then pass --quiesce to stop sessions and verify backup")
            nonce = uuid.uuid4().hex
            receipt = json.loads(self.remote(server, "prepare-destroy", nonce).splitlines()[-1])
            validate_receipt(receipt, server, nonce)
            print("Verified encrypted backup: " + receipt["snapshot"], flush=True)
        fresh = self.api.get(server["id"])
        validate_server(fresh, self.cfg["WORKBENCH_NAME"], server["labels"]["instance"])
        self.api.delete(server["id"])
        for _ in range(30):
            if not self.api.servers(self.cfg["WORKBENCH_NAME"]):
                self.state_path.unlink(missing_ok=True)
                print("Server deleted. Backup storage charges, if any, remain.")
                return
            time.sleep(2)
        raise Error("Delete submitted but absence not confirmed. Check Console/status")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Disposable coding workspaces; see docs/setup.md")
    parser.add_argument("--env", default=".env")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "start", "status", "logs", "ssh", "tunnel", "login", "resume", "retry-bootstrap", "check-key", "check-github", "clone"):
        sub.add_parser(name)
    backup = sub.add_parser("backup")
    backup.add_argument("--quiesce", action="store_true")
    destroy = sub.add_parser("destroy")
    destroy.add_argument("--quiesce", action="store_true")
    destroy.add_argument("--confirm")
    destroy.add_argument("--discard-unbacked", action="store_true")
    destroy.add_argument("--confirm-id")
    args = parser.parse_args(argv)
    os.umask(0o077)
    cfg = load(args.env)
    state_dir = Path(args.env).resolve().parent / ".workbench" / cfg["WORKBENCH_NAME"]
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.command == "validate":
        print("Configuration valid. Credentials and services have not been contacted.")
        return
    with (state_dir / "controller.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Error("Another controller command is running") from exc
        ctl = Controller(cfg, state_dir)
        if args.command == "check-key":
            ctl.check_key()
            return
        if args.command == "check-github":
            ctl.check_github()
            return
        if args.command == "start":
            ctl.start()
            return
        server = ctl.current()
        if not server:
            print("No matching server exists.")
            return
        if args.command == "status":
            print(f"Server {server['id']} | {server['status']} | created {server['created']}")
            print(ctl.remote(server, "status"))
        elif args.command == "destroy":
            ctl.destroy(server, args)
        elif args.command == "backup":
            if not args.quiesce:
                raise Error("Backup stops sessions temporarily; finish work and pass --quiesce")
            print(ctl.remote(server, "backup", uuid.uuid4().hex))
        elif args.command == "clone":
            print(ctl.remote(server, "clone"))
        elif args.command == "resume":
            print(ctl.remote(server, "resume"))
        elif args.command == "retry-bootstrap":
            ctl.ssh(server, "systemd-run --unit=workbench-bootstrap --collect /bin/bash /opt/cli-workbench/remote/bootstrap.sh")
            print("Bootstrap restarted with uploaded configuration. Run start to wait.")
        elif args.command == "logs":
            ctl.ssh(server, "journalctl -u workbench-bootstrap -u workbench-cloudcli -u workbench-tunnel -n 100 --no-pager", capture=False)
        elif args.command in ("ssh", "login"):
            command = "su - dev" if args.command == "ssh" else "su - dev -c 'codex login --device-auth'"
            # Options precede the destination so OpenSSH cannot treat them as a command.
            base = ctl.ssh_args(server)
            subprocess.run(base[:-1] + ["-t", base[-1], command], check=True)
        elif args.command == "tunnel":
            print("Keep this SSH connection open; browse http://localhost:3001")
            base = ctl.ssh_args(server)
            subprocess.run(base[:-1] + ["-N", "-o", "ExitOnForwardFailure=yes", "-L", "127.0.0.1:3001:127.0.0.1:3001", base[-1]], check=True)

def entry():
    try:
        main()
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Error: " + str(exc), file=__import__("sys").stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("Interrupted. Any created server continues billing; run status/start to recover.")
        raise SystemExit(130)
