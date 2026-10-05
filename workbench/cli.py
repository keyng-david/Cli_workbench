"""Phone/laptop controller. Secrets travel over SSH stdin, never argv."""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import uuid
from .config import Error, REMOTE_KEYS, load
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
            raise Error(f"Remote command failed (exit {result.returncode}); use logs or administrative SSH for diagnosis")
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

    def start(self):
        server = self.current()
        if server is None:
            if self.state().get("instance") and not self.state().get("id"):
                raise Error("Previous create outcome is unknown. Inspect Hetzner Console; if no server exists, remove .workbench/<name>/instance.json before retrying")
            instance = uuid.uuid4().hex
            write_json(self.state_path, {"instance": instance})
            print("Creating Hetzner server. Billing begins when allocated.", flush=True)
            server = self.api.create(self.cfg, instance)
            write_json(self.state_path, {"id": server["id"], "instance": instance})
        print(f"Server {server['id']}: waiting for SSH/bootstrap. Re-run start if interrupted.", flush=True)
        deadline = time.monotonic() + int(self.cfg["WAIT_SECONDS"])
        deployed = False
        while time.monotonic() < deadline:
            server = self.api.get(server["id"])
            validate_server(server, self.cfg["WORKBENCH_NAME"], self.state()["instance"])
            try:
                status = self.ssh(server, "if test -f /var/lib/cli-workbench/ready; then echo ready; elif systemctl is-active --quiet workbench-bootstrap; then echo installing; elif test -f /opt/cli-workbench/config.json; then echo failed; else echo empty; fi", timeout=20).strip()
            except (Error, subprocess.TimeoutExpired):
                time.sleep(5)
                continue
            if status == "ready":
                print("Installed. Run status for current service health.")
                print("https://" + self.cfg["PUBLIC_HOSTNAME"] if self.cfg["ACCESS_MODE"] == "cloudflare" else "Run 'python3 workbench.py tunnel', then open http://localhost:3001")
                return
            if status == "failed":
                raise Error("Bootstrap incomplete/failed. Run logs, then retry-bootstrap after fixing the cause")
            if status == "empty" and not deployed:
                self.deploy(server)
                deployed = True
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
    for name in ("validate", "start", "status", "logs", "ssh", "tunnel", "login", "resume", "retry-bootstrap"):
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
