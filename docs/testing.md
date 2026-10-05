# Review, automated tests and live acceptance

## Claude Code Cloud handoff

Review PR #1 / branch feat/initial-workbench. Read README, architecture, persistence and this file before running commands. Use fake credentials and isolated temporary directories for tests. Do not provision a VPS, modify DNS or run remote/bootstrap.sh on the shared Claude environment.

Suggested instruction to Claude:

> Review this entire implementation for correctness and security, concentrating on create/retry/reconcile behavior, SSH argument handling, credential separation, partial bootstrap recovery, SQLite consistency, native/UI state restore, and deletion failure paths. Run the automated suite and package smoke test. Fix defects on the branch, add regression tests for meaningful failures, and update docs/verification.md with exact commands, commit SHA and outcomes. Do not claim live VPS, DNS or Android notification verification. Flag any checks your cloud environment cannot run so the PM can perform them on the disposable VPS.

## Automated commands

On a disposable Ubuntu review runner:

~~~bash
sudo apt-get update
sudo apt-get install -y git restic shellcheck
python3 -m unittest discover -s tests -v
python3 -m compileall -q workbench remote workbench.py
bash -n remote/bootstrap.sh scripts/smoke-runtime.sh
shellcheck -e SC1091 remote/bootstrap.sh scripts/smoke-runtime.sh
~~~

Python 3.10+ is required. No pip dependencies. The suite uses temporary local Git repositories, SQLite databases and encrypted restic repositories. Real restic tests skip when the executable is unavailable; a skipped encryption test is not full acceptance.

With Node 22/npm/curl/setsid available:

~~~bash
bash scripts/smoke-runtime.sh
~~~

This installs pinned CloudCLI/Codex packages into a temporary directory, checks the CLI executable, starts the UI against temporary home/database/workspace paths and checks its loopback HTTP health. It performs no model call and needs no credentials. Package downloads/lifecycle scripts still require a trusted disposable review runner.

GitHub Actions runs the unit/integration checks and the package smoke test. Read the actual logs; green unit tests alone do not prove full bootstrap or mobile notifications work.

## Required review cases

- No executable dotenv evaluation, secret command-line arguments, provider secrets in cloud-init or agent service environment.
- Unknown creation outcome cannot create a duplicate silently; interrupted polling resumes the same labelled instance.
- Multiple/conflicting resources rejected; deletion rechecks instance identity.
- Failed Git fetch, dirty/untracked files, stashes, detached/unpushed commits and stale backup receipts block normal deletion.
- Actual SQLite WAL content preserved; nested files included in checksum inventory.
- Wrong password/corrupt backup/missing backup/version mismatch fail without empty-state fallback.
- Restic round trip exercises the Workbench backup/restore implementation, not just the restic executable.
- Root/agent ownership and fixed paths are correct; no accidental root agent process.
- Setup failures and repeat installation behavior do not expose the UI or silently lose state.
- Shell syntax/static checks, exact package installation and documented commands agree.

Full OS provisioning needs a disposable Ubuntu 24.04 AMD64 VM with systemd. A normal container/cloud sandbox may not provide systemd, UFW, swapon or cloud-init. Do not pretend mocked service commands are a full VM test.

## PM live checklist

Use a dedicated Hetzner project, private backup prefix and a small task.

1. Collect credentials via setup.md; validate config.
2. Optionally start with SSH access mode before touching agency DNS.
3. Start once; close Termux only after upload/systemd confirmation; reopen and reconcile the same server.
4. Check Console for exactly one instance, correct type and expected billing resources.
5. Confirm UI is inaccessible on public port 3001; loopback health works.
6. Configure stable HTTPS/Access and prove an unauthorized identity cannot enter.
7. Finish CloudCLI registration, Codex device login and GitHub login.
8. Clone a test repo under /workspace, configure Git identity, run a real task, test it and push its branch.
9. Start two independent Codex sessions, preferably in separate worktrees; confirm both progress.
10. Verify background/locked-phone completion push, clarification/approval behavior and reconnect.
11. Deliberately leave one uncommitted change; verify normal destroy refuses it. Preserve and push the change.
12. Close developer shells, take a backup, then destroy normally. Confirm the server is absent in Console.
13. Change to RESTORE_MODE=auto and RESTIC_INIT=false. Create a replacement with the same name, versions, backup prefix and tunnel.
14. Re-clone the same project paths, restore branches, sign in as needed. Open and resume a prior conversation.
15. Test push notifications again after restore. Record whether phone resubscription is needed.
16. Delete the replacement and check remaining paid resources.

Do not test deliberate destruction on useful unpushed work. Record actual observations in verification.md, including any failures and fixes.
