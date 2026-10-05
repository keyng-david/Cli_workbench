# Configuration reference

The parser accepts one KEY=value per line, optional matching quotes and full-line comments. No shell expansion, interpolation, escape processing or inline comments. Unknown/duplicate keys are errors. Exported variables override the file. Keep real .env files mode 600 and out of Git.

| Variable | Meaning |
|---|---|
| WORKBENCH_NAME | Stable lowercase identifier, 3–40 characters; labels and backup tag |
| CLOUD_PROVIDER / AGENTS | hetzner / codex only in v1 |
| HCLOUD_TOKEN | Dedicated project read/write API token; controller only |
| HCLOUD_SSH_KEY_ID | Numeric ID of the uploaded public SSH key |
| SSH_PRIVATE_KEY | Matching local key path; tilde expanded here |
| SSH_SOURCE_CIDR | Installed UFW SSH allow rule; default 0.0.0.0/0 for mobile connectivity |
| HCLOUD_SERVER_TYPE | Available AMD64 type, default cpx32 |
| HCLOUD_LOCATION | Location, default nbg1 |
| HCLOUD_IMAGE | Ubuntu 24.04 AMD64 required; OS/architecture checked remotely |
| WAIT_SECONDS | Startup wait, 30–7200; timeout leaves server running |
| SWAP_MB | Fresh-server swap size, 0–8192, default 2048 |
| ACCESS_MODE | cloudflare or ssh |
| PUBLIC_HOSTNAME | Hostname without scheme/path, required in cloudflare mode |
| CLOUDFLARE_TUNNEL_TOKEN | Named tunnel connector token |
| ACCESS_POLICY_CONFIRMED | Operator assertion that hostname is Access-protected |
| CLOUDCLI_VERSION | Exact package pin; default 1.37.3 |
| CODEX_VERSION | Exact package pin; default 0.156.1 |
| PNPM_VERSION | Exact package pin; default 10.17.1 |
| OPENAI_API_KEY | Optional; imported through stdin by Codex login |
| GH_TOKEN | Optional; imported by GitHub CLI, not backed up |
| RESTIC_REPOSITORY | s3:https://endpoint/bucket/prefix |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY | S3/R2 object credentials |
| AWS_DEFAULT_REGION | auto for R2; service-specific elsewhere |
| RESTIC_PASSWORD | Random encryption password, at least 20 characters |
| RESTORE_MODE | fresh refuses existing snapshots; auto requires/restores one |
| RESTIC_INIT | true allows first repository creation only with fresh |
| PERSIST_CODEX_AUTH | Include Codex root auth.json when true; default false |
| INSTALL_BROWSER | Install optional Chromium and system libraries |
| PLAYWRIGHT_VERSION | Optional exact pin, default 1.55.1 |

Node uses NodeSource's signed Node 22 apt repository. Cloudflared uses Cloudflare's signed apt repository. Other OS tools, GitHub CLI and restic use apt. These packages are not bit-for-bit pinned; record resolved versions before release. Top-level npm pins do not lock every transitive dependency. Live install compatibility still needs validation.

CloudCLI uses loopback port 3001, WORKSPACES_ROOT=/workspace and DATABASE_PATH=/home/dev/.cloudcli/auth.db. Stable paths make restored session references useful. The service runs as dev, without sudo.

CloudCLI's database and conversations may hold credentials even with PERSIST_CODEX_AUTH=false. Treat backups and the encryption password as sensitive.

Editing local .env affects the next newly created server. It does not change an existing server's root-owned uploaded JSON. retry-bootstrap reuses that JSON. For failed first installation, repair the remote config through trusted administrative SSH or explicitly discard the failed instance and start again. Do not use bootstrap retries as an upgrade mechanism.
