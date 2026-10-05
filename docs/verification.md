# Verification ledger

## 2026-10-05 implementation

Core commit: d84c80d62e2fef3514e31c8688f230e99a64a17a.

[GitHub Actions run 37312938668](https://github.com/keyng-david/Cli_workbench/actions/runs/37312938668) passed on Ubuntu 24.04, Python 3.12.14 and restic 0.16.4:

- 22 tests passed, no skips.
- Real encrypted restic round trip, wrong-password rejection and Workbench backup/receipt/restore passed.
- SQLite committed WAL content and credential exclusion passed.
- Real local Git dirty/unpushed/stash checks passed.
- Wrong server, stale receipt, unknown create outcome and failed-backup deletion guards passed.
- Python compilation, Bash syntax and ShellCheck passed.

An earlier local run passed 18 tests and skipped restic before the execution service stopped responding. GitHub CI then verified the committed implementation, including the restic tests.

Package installation/CloudCLI HTTP smoke testing is added in a later commit; record its run below when complete.

## Still required

- Claude Code Cloud independent review.
- Full Ubuntu/systemd/SSH/UFW/bootstrap acceptance on a disposable VM.
- Actual Hetzner provisioning/recovery/deletion.
- PM DNS/Access setup and unauthorized-access check.
- Real Codex/GitHub authentication and pending-task workflow.
- Two live Codex sessions, Android notification/reconnect tests.
- Actual destroy/recreate with resumed conversations and push subscription behavior.

No live VPS or DNS resources were changed during implementation.

## Record each later test

Date, commit SHA, environment/resolved versions, command/scenario, outcome, evidence link, failure/fix and any remaining limitation. Do not mark a skipped or mocked integration as live verification.
