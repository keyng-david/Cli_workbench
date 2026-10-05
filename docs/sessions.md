# Concurrent sessions and native notifications

## Multiple agent conversations

CloudCLI groups multiple conversations by project. Its inspected backend keeps a map of runs keyed by application session ID, rejecting a second in-flight run only for the same session. This supports independent concurrent conversations, including Codex.

Opening the same conversation in two browser tabs gives two views of one session. Create a **new session** for an independent task. Select task A, start it, then create/select task B, either from the sidebar or another browser tab. One CloudCLI instance is sufficient.

Upstream evidence:

- [Session management](https://cloudcli.ai/docs/features/session-management)
- [Run registry source](https://github.com/siteboon/claudecodeui/blob/main/server/modules/websocket/services/chat-run-registry.service.ts)
- [Architecture](https://cloudcli.ai/docs/cloudcli-development-resources/architecture)

The pinned runtime still needs the live two-session acceptance test. CPU/RAM and subscription/provider quotas affect concurrency. UI controls may vary by release.

## Avoid two agents editing one working tree

Use separate Git worktrees for independent editing tasks:

~~~bash
cd /workspace/mail-builder
git fetch origin
git worktree add -b fix/payment /workspace/mail-builder-payment origin/main
git worktree add -b fix/onboarding /workspace/mail-builder-onboarding origin/main
~~~

Add those directories as separate CloudCLI projects. Each has its own branch/worktree. Use separate app ports and install dependencies as needed. Push both branches before deletion; Workbench scans both directories.

Direct terminal Codex sessions also remain possible. Use tmux if an SSH terminal must survive disconnects, then finish and close it before backup. Direct CLI sessions may not emit CloudCLI notifications, so use CloudCLI chat for the notification tests.

Other agents are future work. CloudCLI may support them, but this release's AGENTS setting and native history backup support only Codex. Manually installing another binary does not add its state to backup.

## Native notifications first

CloudCLI's architecture documents web-push services, notification preferences, VAPID keys and subscriptions. That is infrastructure evidence, not a guarantee for every Codex question/approval event. Telegram is not configured.

Open the stable HTTPS URL in Android Chrome, sign in, install the PWA if offered, and enable CloudCLI/browser/Android notifications. Check battery restrictions if notifications are delayed. Preserve the hostname and CloudCLI DB across replacements.

| Live test | Observation to record |
|---|---|
| Completion with UI visible | Correct session completes |
| Completion with PWA backgrounded / phone locked | Notification arrives and opens useful context |
| Approval or clarification requested | Whether native push covers this state |
| Two concurrent tasks | Independent output and completion state |
| Mobile/Wi-Fi connection changes | Task continues and reconnect recovers state |
| Delete/restore on a new VPS | Old sessions resume after source directories return |
| Push after restore | Existing subscription works or resubscription is required |
| Access session expires | Notification opens the login flow successfully |

A completed turn is not proof that tests passed, code was pushed or a PR was accepted. Review before explicitly deleting.
