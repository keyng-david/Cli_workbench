# Persistence and deletion

## What is saved

Restic encrypts a consistent staged bundle before uploading it:

- /home/dev/.codex: native conversation history, indexes, configuration and supporting SQLite databases.
- /home/dev/.cloudcli: app database/settings/project and session index, notification identity/subscriptions and other state under that directory.
- projects.json: checked paths, branch names and commit IDs, without remote URLs that might contain tokens.
- manifest.json: schema, workbench identity, version pins and file checksums.

CloudCLI's session index points to native provider IDs and transcript paths. Keeping the UI database alone does not restore the agent's resumable history.

PERSIST_CODEX_AUTH=false excludes only the root Codex auth.json and removes it on restore. It does not promise a credential-free bundle: CloudCLI's DB, configurations and conversations may contain credentials. All backups are encrypted.

Not saved: source repos, project .env files, app databases, dependencies, GitHub CLI login, global Git config, SSH keys, browser profiles/downloads, arbitrary home files, screenshots outside saved state or live processes. Export valuable ignored files/artifacts separately.

## Backup and normal deletion

1. Refuse backup during bootstrap.
2. Stop CloudCLI/tunnel and provider children. --quiesce explicitly permits interrupting active work; finish tasks first.
3. Refuse remaining dev processes, including external SSH/tmux agents.
4. Inspect Git worktrees below /workspace. Refuse dirty/untracked files, stashes, missing remotes, failed fetches or local branch/HEAD commits not reachable from freshly fetched remote branches.
5. Copy state, using SQLite backup() to include committed WAL records; check DB integrity. Reject state symlinks for manual review.
6. Generate file checksums and create a tagged restic snapshot.
7. Restore that exact new snapshot into a temporary directory, decrypt and validate checksums/inventory/versions.
8. Return a receipt bound to server ID, instance identity and a fresh operation nonce.
9. Backup resumes services. Destroy validates the receipt, rechecks the server and deletes it.

Failure blocks normal deletion and attempts to resume services. If the controller disconnects after preparation, use resume or repeat destroy. Keep Termux connected during these operations.

Git checks do not cover ignored/non-Git files, local-only tag names or files outside /workspace, and do not prove tests or PR acceptance. Do not modify state through a separate administrative connection during deletion.

## Restore

First deployment: fresh + RESTIC_INIT=true. Subsequent deployments: auto + false. Fresh refuses existing matching snapshots; auto requires one and fails on storage/authentication errors.

Restore happens before CloudCLI starts. Workbench name and CloudCLI/Codex pins must match the snapshot. Re-clone projects to their original paths and restore the desired branch/commit. An administrator can read /var/lib/cli-workbench/restored-projects.json for the inventory.

Native history survives; running processes do not. Resume the conversation after restoring its source directory. Notification continuity additionally depends on the same origin, valid push subscription and Android/browser settings.

## Retention

No periodic backup, automatic pruning or bucket expiry is configured. Only explicit backup/destroy saves new history; an abruptly lost server can lose work since the last backup. Restic deduplicates data, but storage/operation charges may still apply.

Use restic's documented snapshots/check/forget/prune operations deliberately from a trusted machine. Never delete arbitrary objects inside its repository. Keep the encryption password independently. Restore with recorded versions before testing upgrades; there is no automatic migration engine.

[Restic setup documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)
