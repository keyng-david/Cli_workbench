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
