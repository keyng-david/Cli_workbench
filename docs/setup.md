# PM setup and first deployment

Use this guide after Claude Code Cloud reviews the branch and passes the tests. Enter credentials directly into your local .env, not in a chat.

## 1. Choose browser access

Recommended daily mode: ACCESS_MODE=cloudflare, with a named tunnel and protected hostname such as agents.keyngdev.com. Browser/PWA use continues independently of Termux after installation. Read [DNS migration](dns.md) before changing nameservers.

For a first installation smoke test, ACCESS_MODE=ssh needs no domain or DNS changes. Tunnel fields may be blank. Run python3 workbench.py tunnel and open http://localhost:3001. The SSH connection must stay open, so this mode is for initial diagnosis rather than your eventual mobile workflow.

## 2. Hetzner and SSH

1. Create a dedicated project in Hetzner Cloud Console.
2. Create a read/write API token for it. Save as HCLOUD_TOKEN on the controller only.
3. Install Python, Git and OpenSSH in Termux. Generate a key if you do not already have one: ssh-keygen -t ed25519. Do not overwrite an existing key inadvertently.
4. Upload the PUBLIC .pub key to the same Hetzner project. Put its numeric ID in HCLOUD_SSH_KEY_ID and the matching local private-key path in SSH_PRIVATE_KEY.
5. For a passphrase-protected key, load it into ssh-agent first. Controller SSH uses BatchMode.
6. Confirm the chosen AMD64 server type/location is available and affordable. Defaults: cpx32, nbg1, ubuntu-24.04. There is no automatic fallback to a more expensive machine.

If Console does not show the SSH key ID, query it without exposing the token in a command argument:

~~~bash
python3 - <<'PY'
from workbench.config import read_env
from workbench.hetzner import Hetzner
c = read_env('.env')
for k in Hetzner(c['HCLOUD_TOKEN']).request('GET', '/ssh_keys')['ssh_keys']:
    print(k['id'], k['name'], k['fingerprint'])
PY
~~~

The controller creates a server with automatically assigned primary IPs. It creates no volumes, snapshots or floating IPs. Verify resources and billing after the first deletion. Powering off alone does not delete the server.

## 3. R2/S3 encrypted backup storage

1. Create a private bucket dedicated to workbench backups, with public access disabled.
2. Create S3 credentials scoped to that bucket, with object read/write/list/delete access needed by restic. R2 provides an S3 Access Key ID and Secret Access Key; these are not a dashboard API token.
3. Use the exact HTTPS S3 endpoint shown for your account. Ordinary R2 endpoints resemble ACCOUNT_ID.r2.cloudflarestorage.com; account/jurisdiction-specific endpoints may differ.
4. Set RESTIC_REPOSITORY=s3:https://ENDPOINT/BUCKET/cli-workbench, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. For R2 use AWS_DEFAULT_REGION=auto; other S3 services may require a different region.
5. Generate a random password and put it in RESTIC_PASSWORD:

~~~bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
~~~

Keep that password independently in a password manager. Losing it makes backups unreadable.

For the FIRST deployment use RESTORE_MODE=fresh and RESTIC_INIT=true. After the first successful backup, use auto and false on every subsequent deployment. Auto mode fails if backup access fails; it never silently starts empty.

Restic encrypts before uploading. Check your account's current storage/operation allowance and billing. Do not apply object-expiry lifecycle rules to restic's internal files; use restic's own retention tools.

## 4. Named tunnel and Access

1. Complete [DNS migration](dns.md), or start with SSH mode.
2. In Cloudflare Zero Trust create a named, remotely managed tunnel for this workbench.
3. Add a published application route: agents.keyngdev.com → http://127.0.0.1:3001.
4. Create a self-hosted Access application for that hostname, with an Allow policy for your email using one-time PIN or your identity provider. Do not use an everyone/bypass rule.
5. Copy the connector token into CLOUDFLARE_TUNNEL_TOKEN. If shown as part of an install command, copy only the token.
6. Set PUBLIC_HOSTNAME=agents.keyngdev.com and ACCESS_POLICY_CONFIRMED=true once the Access rule exists.
7. Use a private browser window to confirm Access challenges users and does not admit unrelated identities.

The confirmation variable is your assertion; the script cannot inspect your Cloudflare policy. One live VPS should use this tunnel. Independent replicas with different state must not share it.

## 5. Agent and GitHub login

Leave OPENAI_API_KEY blank to use Codex device login through your ChatGPT account. After startup run python3 workbench.py login and complete the URL/code flow on your phone. Enable device authentication in account settings if the official login flow requires it. Subscription limits still apply. Providing an API key uses separate API billing.

Leave GH_TOKEN blank to use gh auth login --web in CloudCLI's terminal. Alternatively supply a token scoped to the repositories needed for your work. The GitHub CLI credential is not included in this project's state backup; sign in again or supply a token next time.

CloudCLI/agents run as dev without sudo. They can access that user's code and agent/GitHub credentials. Cloud/backup/tunnel secrets remain root-owned; the Hetzner token and controller SSH private key never go to the VPS.

## 6. Start and use the workspace

~~~bash
cp .env.example .env
chmod 600 .env
nano .env
python3 workbench.py validate
python3 workbench.py start
~~~

Validation is local only. Installation may take several minutes. When the controller confirms bootstrap is under systemd, it continues even if Termux closes. Re-run start to reconcile/wait on the same server.

Open the URL, complete CloudCLI first-run registration/login, then agent login. The local health check does not prove DNS, Access, notifications or agent authentication work; use the [live checklist](testing.md).

In CloudCLI's terminal as dev:

~~~bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git config --global user.name 'David Agu'
git config --global user.email 'YOUR_GITHUB_COMMIT_EMAIL'
cd /workspace
gh repo clone keyng-david/mail-builder
~~~

If a GitHub token was supplied, check gh auth status instead of repeating login. Global Git preferences are disposable and must be configured on fresh servers.

Select/add the project directory in CloudCLI, select Codex and try a read-only task. Then test a pending coding task on a new branch. Follow the project's own dependency and secret setup instructions. Optional browser provisioning installs Chromium, but individual projects may need their matching Playwright browser version or MCP configuration.

## 7. Finish, preserve and delete

Finish tasks, commit/push every branch, export valuable ignored files/artifacts and exit external developer shells/tmux. Workbench does not auto-commit or judge PR correctness.

~~~bash
python3 workbench.py backup --quiesce
python3 workbench.py destroy --quiesce --confirm cli-workbench
~~~

The extra backup is useful for your first test; destroy takes a new verified backup itself. Keep Termux connected during backup/deletion. Failure prevents deletion, so check Console afterward.

Before the next server use RESTORE_MODE=auto and RESTIC_INIT=false. Clone repositories back to the same /workspace paths and authenticate as needed. Session history does not restore deleted source code or dependencies.
