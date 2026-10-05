# Termux command guide: from first run to deleting the server

Every command is run in Termux from the project folder:

```bash
cd ~/Cli_workbench
```

Hetzner bills by the hour while a server exists, **even when it is powered off or idle**. Deleting is the only way to stop the charge. Section 6 is the delete procedure; do it every time you finish.

## 0. One-time setup

```bash
pkg update && pkg upgrade
pkg install python git openssh nano
git clone https://github.com/keyng-david/Cli_workbench.git ~/Cli_workbench
cd ~/Cli_workbench
cp .env.example .env
chmod 600 .env
nano .env          # Ctrl+O, Enter to save; Ctrl+X to exit
```

Credentials come from [credentials.md](credentials.md). Pull updates later with `git pull`.

Stop Android from killing Termux during long operations:

```bash
termux-wake-lock           # (pkg install termux-api if the command is missing)
```

Also exempt Termux from battery optimization in Android Settings, and keep the Termux notification visible.

## 1. First deployment settings

In `.env` for the very first server:

```
RESTORE_MODE=fresh
RESTIC_INIT=true
```

After the first successful backup, change them to `RESTORE_MODE=auto` and `RESTIC_INIT=false` for every later server (see section 8).

## 2. Check the config (free, contacts nothing)

```bash
python3 workbench.py validate
```

Fix whatever it reports, then repeat until it says the configuration is valid.

## 3. Create the server (billing starts)

```bash
python3 workbench.py start
```

It creates the server, uploads the setup, and waits. Installation takes several minutes. After it prints that bootstrap runs under systemd, closing Termux is safe. Run `start` again later to wait for and reconcile the same server. It never creates a duplicate.

When it finishes:

- `ACCESS_MODE=cloudflare`: open `https://<PUBLIC_HOSTNAME>` and log in through the Access page.
- `ACCESS_MODE=ssh`: run `python3 workbench.py tunnel` in one Termux session and leave it open, then open `http://localhost:3001` in your phone browser.

## 4. While it runs

| Command | What it does |
|---|---|
| `python3 workbench.py status` | Server state, services, health. Also tells you whether a server still exists (cost check). |
| `python3 workbench.py logs` | Recent install, UI and tunnel logs. Use when something fails. |
| `python3 workbench.py login` | Codex sign-in by device code, on your phone. |
| `python3 workbench.py ssh` | Developer shell on the server (user `dev`). |
| `python3 workbench.py tunnel` | SSH-mode only: forwards the UI to `localhost:3001`. |
| `python3 workbench.py resume` | Start the UI and tunnel again after a backup. |
| `python3 workbench.py retry-bootstrap` | Retry a failed installation, then run `start` to wait. |

In the web UI's terminal, sign in to GitHub once: `gh auth login --hostname github.com --git-protocol https --web`, then `gh auth setup-git`.

## 5. Back up without deleting

```bash
python3 workbench.py backup --quiesce
python3 workbench.py resume
```

`--quiesce` stops running agent sessions, checks that your Git work is saved, backs up, verifies by reading it back, and resumes. Close any `workbench.py ssh` shells and tmux sessions first, because it refuses while processes of user `dev` remain.

## 6. Finish and delete the server (stops all server charges)

1. In your repositories, commit and push every branch. Delete is refused if there are uncommitted files, stashes or unpushed commits.
2. Close every shell: leave `python3 workbench.py ssh` (type `exit`), close tmux, and close the web UI's terminal tab.
3. Delete:

   ```bash
   python3 workbench.py destroy --quiesce --confirm cli-workbench
   ```

   Replace `cli-workbench` with your `WORKBENCH_NAME` if you changed it. It takes a fresh encrypted backup, reads it back to verify, then deletes the server. Keep Termux open and awake until it prints `Server deleted.`
4. Confirm there is no cost left:

   ```bash
   python3 workbench.py status
   ```

   It should say `No matching server exists.` Also open the [Hetzner Console](https://console.hetzner.com/), your project, and confirm **Servers** is empty. The only remaining cost is the small R2 storage.

### If the delete is refused

Read the message. The usual causes are unsaved Git work (push it), a shell still open (close it), or a backup problem (see [troubleshooting.md](troubleshooting.md)). The server is **not** deleted in that case and still bills. Fix the cause and repeat, or use the emergency option below.

### Emergency delete (permanently discards anything not backed up)

Only when you do not need the server's data, for example a failed test install:

```bash
python3 workbench.py destroy --discard-unbacked --confirm cli-workbench --confirm-id SERVER_ID
```

`SERVER_ID` is printed by `status` and the error message, and is shown in the Hetzner Console. You can also delete a server directly in the Console: select the server → **Delete**.

## 7. If `start` is interrupted or the server is "lost"

- Do not run it blindly again until you know what exists. Run `python3 workbench.py status`.
- Open the Hetzner Console and check **Servers**. If there is one, `start` reconciles it. If an error says the previous create outcome is unknown and the Console shows no server, follow the message (it tells you which state file to remove).

## 8. Next time (history restore)

After the first successful backup and destroy, set in `.env`:

```
RESTORE_MODE=auto
RESTIC_INIT=false
```

Keep `WORKBENCH_NAME`, `RESTIC_PASSWORD`, the bucket path and the `CLOUDCLI_VERSION`/`CODEX_VERSION` values unchanged. Then run `python3 workbench.py start`. Clone your projects back into the same `/workspace` paths. History is restored; code and dependencies are not.

## 9. Cost safety habits

- Never leave a server overnight "just in case". Back up and destroy.
- Run `python3 workbench.py status` at the end of every session.
- In Hetzner Console, set a budget or billing alert if one is offered under your account's billing settings.
- Use `WAIT_SECONDS` only to control how long `start` waits; a timeout leaves the server running and billing.
