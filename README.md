# CLI Workbench

Disposable cloud coding workspaces controlled from your phone or laptop. CloudCLI provides the browser/mobile UI; agent history is encrypted to R2/S3 before the VPS is deleted.

**Initial implementation: pending Claude Code Cloud review and live VPS acceptance.** No real credentials are included.

Version 1 supports Hetzner, Ubuntu 24.04 AMD64, Codex and unmodified CloudCLI. It provides named Cloudflare Tunnel access, native notification support through CloudCLI, restic backups, and explicit deletion guarded by Git and backup checks. Additional cloud providers and multiple agent installers are extension points; unsupported selections currently fail validation. Telegram is postponed.

## Documentation

- [PM setup and credentials](docs/setup.md)
- [Namecheap, Vercel and DNS](docs/dns.md)
- [Configuration reference](docs/configuration.md)
- [Persistence and deletion](docs/persistence.md)
- [Concurrent sessions and notifications](docs/sessions.md)
- [Testing and Claude review handoff](docs/testing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [Verification ledger](docs/verification.md)

## Quick start

Read the setup guide first. Keep the checkout in Termux's private home directory, not Android shared storage.

~~~bash
pkg install python git openssh
git clone --branch feat/initial-workbench https://github.com/keyng-david/Cli_workbench.git
cd Cli_workbench
cp .env.example .env
chmod 600 .env
nano .env
python3 workbench.py validate
python3 workbench.py start
~~~

Use the default branch after this implementation is merged. Linux/macOS controllers need Python 3.10+ and OpenSSH. Use WSL on Windows. No Node installation is needed on the controller.

Start allocates a billable server, uploads the checkout's remote code/configuration over SSH, and launches a systemd installation job. Once uploaded, installation continues if Termux closes. Re-run start to reconcile the same server. First installation can take several minutes.

Open the HTTPS URL, complete CloudCLI first-run registration/login and authenticate Codex if no API key was supplied:

~~~bash
python3 workbench.py login
~~~

Then sign into GitHub from CloudCLI's developer terminal if needed:

~~~bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
cd /workspace
gh repo clone keyng-david/mail-builder
~~~

## Commands

| Command after python3 workbench.py | Purpose |
|---|---|
| validate | Check configuration locally; no service authentication |
| start | Create/reconcile server and wait for bootstrap |
| status | Server and remote service/HTTP health |
| logs | Recent installation/UI/tunnel logs |
| login | Codex device login |
| ssh | Developer shell |
| tunnel | Local SSH forwarding for SSH access mode |
| backup --quiesce | Stop sessions, verify Git, back up, read back and resume |
| resume | Resume paused UI/tunnel services |
| retry-bootstrap | Retry incomplete installation using uploaded configuration |
| destroy --quiesce --confirm cli-workbench | Verify a new backup, then delete |

Global options precede the command: python3 workbench.py --env ~/private/workbench.env status.

Finish tasks, push every branch, export ignored files/artifacts and close external developer shells before passing --quiesce. That flag explicitly permits stopping running agent processes. Workbench does not auto-commit or decide whether a PR is accepted.

Before the second deployment, set RESTORE_MODE=auto and RESTIC_INIT=false. Keep the backup password, workbench name and version pins stable. Clone projects back to their original /workspace paths; history does not restore code or dependencies.

## Checks

~~~bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q workbench remote workbench.py
bash -n remote/bootstrap.sh
~~~

Install restic for the real encryption/restore tests. CI also runs ShellCheck. Tests create no cloud resources. Do not run remote/bootstrap.sh on a workstation/shared review host: it modifies the OS, users, firewall and services.

## Upstream

This project orchestrates [CloudCLI](https://github.com/siteboon/claudecodeui), [Codex](https://github.com/openai/codex) and restic without modifying them. Their licenses remain applicable. Inspected CloudCLI source declares AGPL-3.0-or-later and includes agent dependencies, including Codex. Only Codex installation/persistence is explicitly supported by this project's first release.
