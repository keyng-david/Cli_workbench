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

First run the free key check. It contacts Hetzner (no server, no cost) and confirms your Termux key is the one Hetzner will install on the server:

```bash
python3 workbench.py check-key
```

It must print `SSH key OK`. `start` runs the same check automatically before creating anything.

```bash
python3 workbench.py start
```

It creates the server, uploads the setup, and then prints a progress line whenever something changes, plus a reminder every 30 seconds so you can see it is alive:

```
Server 169004814: waiting for SSH/bootstrap. Re-run start if interrupted.
[00:35] Server is up; SSH not ready yet: Remote command failed (exit 255): Connection refused
[01:10] SSH connected. Uploading installer...
[01:25] Installing: [1/8] Installing system packages
[04:40] Installing: [5/8] Installing CloudCLI and Codex (takes a few minutes)
[09:15] Installed.
```

**How long it takes.** Every `start` builds a brand-new server from scratch, so every start repeats the installation. I have not timed a real server yet, so treat this as an estimate: roughly 5 to 15 minutes, mostly stage 1 (system packages) and stage 5 (CloudCLI and Codex download). Please send me your real timings after the first full run. Restoring your history does not shorten it. If the wait ever becomes a nuisance, a saved Hetzner image of a finished server could skip most of it, at the cost of a small monthly storage fee. I have not built that.

**The eight stages** are: 1 system packages, 2 package sources, 3 Node.js and cloudflared, 4 user and workspace, 5 CloudCLI and Codex, 6 backup storage restore/init, 7 services, firewall and swap, 8 start and health check.

**If it prints the same "SSH not ready yet" line for more than about 3 minutes**, read the reason after the colon:
- `Permission denied (publickey)`: the key on the server is not the one in `SSH_PRIVATE_KEY`. Check that `HCLOUD_SSH_KEY_ID` is the ID of the key you made in Termux, then `destroy` and start again.
- `Connection refused` or `timed out` for under 3 minutes is normal while the server boots.

**Closing Termux.** After the line `Bootstrap now runs under systemd and continues if Termux closes.` you may leave. To check later: open Termux and run `python3 workbench.py start` again. It does not create a second server; it shows the same progress lines and finishes with the address. Or run `python3 workbench.py logs`. In cloudflare mode, the tunnel turns **Healthy** in the Cloudflare dashboard only at the end, at stage 8. Before then the address shows a Cloudflare error 1033. That is normal and not a fault.

**Optional phone notification when it finishes.** `pkg install termux-api`, then install the free **Termux:API** app from the same source as Termux (F-Droid), and allow notifications. `start` then sends a notification when the install is ready or has failed. Without it, nothing changes.

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

If `login` prints `Software caused connection abort` or `Broken pipe`, your phone's connection dropped (Android put Termux to sleep or the network changed). The device-code sign-in dies with the connection, so run `python3 workbench.py login` again and finish it within 15 minutes. Run `termux-wake-lock` first, and keep Termux open until it says you are signed in.

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

- If you delete the server yourself in the Hetzner Console while `start` is waiting, `start` now says the server no longer exists and clears its state. Just run `start` again for a new one.
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
