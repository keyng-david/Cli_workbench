# Troubleshooting and recovery

A failed install, timeout, disconnect or OS shutdown does not delete the server. Check Hetzner Console whenever the outcome is unclear.

## Interrupted start

Re-run start. Labels and local identity reconcile the same server. If systemd installation is running, it waits; after successful upload installation is independent of Termux.

If creation had an unknown result and no labelled server is visible, inspect Console and let the request settle. Only after verifying no server exists should you remove .workbench/NAME/instance.json and retry. Do not remove host-key records blindly. Multiple matching servers or conflicting identities require explicit reconciliation.

## Failed bootstrap

~~~bash
python3 workbench.py logs
python3 workbench.py retry-bootstrap
python3 workbench.py start
~~~

Retry uses the uploaded config, not local .env edits. Diagnose the first failure. Possible causes include package availability, network access, native dependencies, backup credentials or upstream incompatibility. A ready marker prevents using bootstrap retries as an upgrade.

For administrative diagnosis, obtain the IP/ID from Console and SSH as root with the same key, preserving host-key validation:

~~~bash
journalctl -u workbench-bootstrap -u workbench-cloudcli -u workbench-tunnel -n 200 --no-pager
python3 /opt/cli-workbench/remote/state.py status
~~~

Review/redact logs before sharing. Never post config.json, authentication files or tunnel tokens.

## UI offline

The ready marker records installation, not current health. Use status, then resume if services were left paused. Check tunnel hostname/service mapping, Access, DNS and loopback health separately. Ensure only one independent VPS uses this named tunnel.

## Backup/deletion refused

Commit and push all branches. Resolve untracked files and stashes. Check GitHub authentication; fresh fetch failures stop deletion. Close external developer shells/tmux jobs before quiescing.

For a specific remote state error, after finishing tasks an administrator can run:

~~~bash
python3 /opt/cli-workbench/remote/state.py backup manual-diagnostic
~~~

This also stops sessions and resumes services afterward. State symlinks require manual review.

If a backup succeeded but deletion failed/disconnected, run resume or repeat normal destroy to create a new receipt. Old receipts cannot authorize later deletion.

## Explicitly discard a failed or unwanted instance

~~~bash
python3 workbench.py destroy --discard-unbacked --confirm cli-workbench --confirm-id SERVER_ID
~~~

Use the exact numeric ID. This deliberately bypasses backup/Git checks and loses all unpreserved state. Ownership checks remain. It is never an automatic fallback. Manual Console deletion is also possible; verify the selected server and check billing resources afterward.

## Restore issues

- Existing snapshots in fresh mode: use auto for the next deployment.
- No matching snapshot in auto mode: check bucket/prefix/name; use fresh only for first use.
- Network/password/permission failure: correct it; do not start empty to hide it.
- Version mismatch: restore using the snapshot's versions, then test upgrades separately.
- Sessions but missing source: clone to the original /workspace path and restore the branch.
- Notifications after restore: verify Access, Android permissions and push subscription, and record whether resubscription is needed.

## Codex says `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`

Codex runs its commands inside a small sandbox (bubblewrap). Ubuntu 24.04 blocks that by default through an AppArmor setting, `kernel.apparmor_restrict_unprivileged_userns=1`, so every command fails before it runs. This is a known Codex-on-Ubuntu-24.04 problem, not a problem with your repository.

New servers fix it automatically: the installer writes `/etc/sysctl.d/60-workbench-userns.conf` with `kernel.apparmor_restrict_unprivileged_userns=0`. That is controlled by `RELAX_USERNS_RESTRICTION=true` in `.env` (the default).

The trade-off: it relaxes a kernel hardening setting on the whole server, so programs run by the `dev` user can use user namespaces. The server is disposable and single-purpose, so I accept that. If you prefer to keep the setting, use `RELAX_USERNS_RESTRICTION=false`, but then Codex commands will fail unless you change Codex's own sandbox setting in `~/.codex/config.toml`, which removes the sandbox instead.

Servers created before this fix need a new server. To verify on a server, open `python3 workbench.py ssh` and run `bwrap --unshare-net --ro-bind / / /bin/true`; no output means it works.

## Destroy or backup says `State symlink needs manual review: apply_patch`

Codex creates temporary links in `~/.codex/tmp`. The backup used to refuse any link, which blocked a normal destroy. The backup now skips `~/.codex/tmp` (temporary data) and still refuses links anywhere else. If you still see this message for another name, the server is not deleted and keeps billing. Look at the named path, and if you do not need the server's data use the emergency delete in [termux.md](termux.md) section 6.

## How do I check that my repositories were cloned?

```bash
python3 workbench.py status
```

The output has a `workspace_repos` list showing each cloned folder, its branch and the number of tracked files. An empty list means nothing was cloned. Run `python3 workbench.py logs` and look for `Cloning ...` or `WARNING: could not clone ...` lines.

## A repository was not cloned (retry without a new server)

On a running server:

```bash
python3 workbench.py clone
```

It retries every `CLONE_REPOS` entry and prints one line per repository: `cloned`, `exists`, or `FAILED owner/repo: <the real reason from Git>`. Then `python3 workbench.py status` should list it under `workspace_repos`.

To see Git's own output instead, open a shell with `python3 workbench.py ssh` and run:

```bash
git clone https://github.com/OWNER/REPO.git /workspace/REPO
gh auth status
```

Common reasons: `Repository not found` (the token does not include that repository), `Authentication failed` (token expired or missing), `could not read Username` (GitHub sign-in did not happen because `GH_TOKEN` was empty when the server was created). `GH_TOKEN` is only applied at server creation, so changing `.env` does not affect a server that is already running.
