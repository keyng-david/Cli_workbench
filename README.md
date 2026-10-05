# CLI Workbench

Disposable cloud workspaces for coding agents, with CloudCLI providing the browser and mobile interface.

## Project status

Planning and implementation have started. No provisioning scripts have been released or tested yet.

## Initial scope

- Hetzner provisioning controlled from Termux or another terminal.
- Codex installed initially; architecture designed for additional cloud providers and multiple coding agents later.
- Documented `.env.example` for configuration, with secrets excluded from Git.
- CloudCLI native notifications tested before considering Telegram.
- Encrypted backup and restore of CloudCLI state and provider-native session state.
- Explicit destroy command that verifies backups before deleting the VPS.
- Automated checks intended to run in Claude Code Cloud before live VPS testing.

## Domain configuration

The existing agency website remains hosted on Vercel. A Cloudflare DNS migration, if chosen, must preserve all current website, email, and verification records. Keep Vercel website records DNS-only; route only the workbench hostname through Cloudflare Tunnel and Access. Do not change nameservers until the existing records have been audited and copied.

## Documentation plan

The implementation branch will add configuration, installation, persistence, security, testing, and troubleshooting guides alongside the scripts. Features will be marked verified only after testing.
