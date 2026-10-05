# Getting every credential, step by step (beginner guide)

This is the click-by-click companion to [setup.md](setup.md). Do the parts in order. Part A–C are enough for the first test (`ACCESS_MODE=ssh`). Part D (Cloudflare tunnel + login protection + your domain) can wait until the first test works.

Dashboard menus change from time to time. If a button is named slightly differently, look for the closest match. Official pages used for this guide are linked at each step.

**Rules for secrets**

- Type or paste secrets only into the `.env` file on your phone (Termux). Never paste them into a chat, including this one.
- Several secrets are shown only once. Copy each one into a password manager or straight into `.env` immediately.
- Keep a scratch list while you go, so you know what is still missing:

| `.env` variable | Comes from | Done |
|---|---|---|
| `HCLOUD_TOKEN` | Part A | |
| `HCLOUD_SSH_KEY_ID` | Part B | |
| `SSH_PRIVATE_KEY` | Part B | |
| `RESTIC_REPOSITORY` | Part C | |
| `AWS_ACCESS_KEY_ID` | Part C | |
| `AWS_SECRET_ACCESS_KEY` | Part C | |
| `RESTIC_PASSWORD` | Part C | |
| `CLOUDFLARE_TUNNEL_TOKEN`, `PUBLIC_HOSTNAME` | Part D (later) | |

---

## Part 0. Prepare Termux

```bash
pkg update
pkg install python git openssh nano
```

Keep the project inside Termux's own home folder (`~/Cli_workbench`), not in `/sdcard`, because `.env` must have private permissions (`chmod 600`), which shared storage does not support.

---

## Part A. Hetzner account and API token → `HCLOUD_TOKEN`

Hetzner is the company that rents you the temporary server. [Official page](https://docs.hetzner.com/cloud/api/getting-started/generating-api-token/).

1. Go to <https://console.hetzner.com/> and register. You must verify your email and usually a payment method or ID check before you can create servers.
2. Create a project: from the project list choose **New project**, name it `cli-workbench`, and open it. Use a dedicated project so the token can only touch this one.
3. In the left menu click **Security**, then **API tokens** in the top menu.
4. Click **Generate API token**.
5. Description: `workbench`. Permission: **Read & Write** (it must be able to create and delete servers).
6. Click to generate, then copy the token immediately. Hetzner will never show it again. If you lose it, delete it and generate another.
7. In `.env`: `HCLOUD_TOKEN=paste_it_here`

---

## Part B. SSH key → `SSH_PRIVATE_KEY` and `HCLOUD_SSH_KEY_ID`

An SSH key is a pair of files: a private one that stays on your phone, and a public one that you give to Hetzner so the new server lets you in.

1. In Termux make a key. Use a dedicated filename so you cannot overwrite an existing key:

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/workbench_ed25519 -C "workbench"
   ```

   When asked for a passphrase, press Enter twice to leave it empty. The controller connects non-interactively, and a passphrase would block it unless you set up `ssh-agent`. The key lives only in Termux's private storage and only opens servers in your Hetzner project.

2. Show the PUBLIC key (the one ending `.pub`) and copy the whole line, starting with `ssh-ed25519` (long-press in Termux to select and copy):

   ```bash
   cat ~/.ssh/workbench_ed25519.pub
   ```

   Never share the file without `.pub`.

3. In Hetzner Console, open your `cli-workbench` project → **Security** → **SSH keys** → **Add SSH key**. Paste the line, name it `termux`, and save.

4. Find the key's numeric ID. Do this after you have created `.env` with `HCLOUD_TOKEN` filled in (see Part E step 1), from the repository folder:

   ```bash
   python3 - <<'PY'
   from workbench.config import read_env
   from workbench.hetzner import Hetzner
   c = read_env('.env')
   for k in Hetzner(c['HCLOUD_TOKEN']).request('GET', '/ssh_keys')['ssh_keys']:
       print(k['id'], k['name'])
   PY
   ```

   The number printed beside `termux` is the ID, for example `12345678`.

5. In `.env`:

   ```
   HCLOUD_SSH_KEY_ID=12345678
   SSH_PRIVATE_KEY=~/.ssh/workbench_ed25519
   ```

---

## Part C. Backup storage (Cloudflare R2) → bucket, keys and password

The server is deleted when you are done. Your Codex conversation history is encrypted and saved in a bucket so the next server can restore it. R2 is Cloudflare's storage; it has a free allowance but requires an account with a payment method.

### C1. Cloudflare account and enabling R2

1. Register at <https://dash.cloudflare.com/sign-up> and verify your email. A domain is not needed for R2.
2. In the left menu open **R2 object storage** (Storage & databases → R2). Follow the prompts to enable R2. It asks for a payment method; check the pricing page shown there for the current free allowance. Cloudflare's own page says R2 must be purchased/enabled before an API token can be created.

### C2. Create the private bucket

1. In **R2 object storage** → **Overview**, click **Create bucket**.
2. Name: `cli-workbench-backups` (lowercase, no spaces). Leave location on Automatic. Create it.
3. Do NOT turn on a public URL or custom domain. Buckets are private by default. [Docs](https://developers.cloudflare.com/r2/buckets/create-buckets/).

### C3. Account ID → needed for `RESTIC_REPOSITORY`

1. The Account ID is a 32-character string. It is on the R2 **Overview** page under **Account Details**, next to the S3 API address. It also appears in the browser address bar after `dash.cloudflare.com/`.
2. The S3 endpoint is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. If you chose an EU/US/FedRAMP *jurisdiction* when creating the bucket, use `<ACCOUNT_ID>.eu.r2...` (or `.us.`/`.fedramp.`) instead. Copy it exactly from the Account Details panel.

### C4. Create S3 access keys → `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`

[Official page](https://developers.cloudflare.com/r2/api/tokens/).

1. R2 **Overview** → under **Account Details** click **Manage** beside **API Tokens**.
2. Click **Create Account API token** (or **User API token**; either works).
3. Token name: `workbench-backups`.
4. Permission: **Object Read & Write**.
5. Under *Specify bucket(s)* choose **Apply to specific buckets only** and select `cli-workbench-backups`.
6. Create the token. The next screen shows:
   - **Access Key ID** → `AWS_ACCESS_KEY_ID`
   - **Secret Access Key** → `AWS_SECRET_ACCESS_KEY`

   Copy both now; the secret is shown only once. Ignore the other "Token value" shown on that screen: it is not what restic needs.

### C5. Choose the restic password → `RESTIC_PASSWORD`

This password encrypts your backups. If you lose it, the backups cannot be read by anyone, including you. Generate it in Termux:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Save it in a password manager now (and in `.env`).

### C6. Put it in `.env`

```
RESTIC_REPOSITORY=s3:https://ACCOUNT_ID.r2.cloudflarestorage.com/cli-workbench-backups/cli-workbench
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=auto
RESTIC_PASSWORD=...
RESTORE_MODE=fresh
RESTIC_INIT=true
```

The three parts of the repository value are: `s3:https://` + your endpoint host + `/` + bucket name + `/` + a folder name (`cli-workbench`). Replace `ACCOUNT_ID` with your real 32-character ID. Do not set an expiry or lifecycle rule on the bucket.

---

## Part D. Cloudflare Tunnel + login protection (do this after the first test works)

This gives you a permanent, HTTPS address such as `agents.yourdomain.com` that only you can open. It needs a domain whose DNS is on Cloudflare, so read [dns.md](dns.md) first. Changing nameservers affects your whole domain (including your website and email), so do not rush it.

Skip Part D entirely for the first test by using `ACCESS_MODE=ssh`.

### D1. Turn on Zero Trust (free plan)

1. In the Cloudflare dashboard, find **Zero Trust** (sometimes under **Networking** or **Cloudflare One**). First-time use asks for a team name (anything, such as `keyng`) and a plan. Choose the **Free** plan; it may still ask for a payment method.

### D2. Create the tunnel → `CLOUDFLARE_TUNNEL_TOKEN`

[Official page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).

1. Dashboard → **Networking** → **Tunnels** → **Create a tunnel**. Choose the **Cloudflared** type if asked.
2. Name it `cli-workbench` and click **Create Tunnel**.
3. The next page offers install commands for different operating systems. **Do not run them.** The workbench installs the connector itself. Find the command that looks like `cloudflared service install eyJhIjoi...` (or `--token eyJ...`). The long string starting `eyJ` is the token. Copy only that string.
4. In `.env`: `CLOUDFLARE_TUNNEL_TOKEN=eyJ...`
5. The page will say it is waiting for a connection. That is expected, because no server exists yet. If it forces you to continue, you can leave the tunnel unconnected and add the route from its settings later.

### D3. Add the hostname route

1. **Networking** → **Tunnels** → click `cli-workbench` → **Routes** tab → **Add route** → **Published application**.
2. Subdomain: `agents`. Domain: pick your domain from the dropdown (it appears only if the domain is active on Cloudflare).
3. Service URL: `http://127.0.0.1:3001`
4. Save. Cloudflare creates the DNS record itself.
5. In `.env`: `PUBLIC_HOSTNAME=agents.yourdomain.com` (no `https://`, no slash).

### D4. Lock it with an Access login (important)

Without this step, anyone who guesses the address can reach your coding terminal. [Official page](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).

1. Zero Trust → **Access controls** → **Applications** → **Create new application**.
2. Choose **Self-hosted and private**.
3. Click **Add public hostname**, pick your domain, and enter subdomain `agents` (matching Part D3).
4. Under **Access policies** create a policy: name `me only`, action **Allow**, rule **Emails** → your own email address. Attach it. (Access is deny-by-default, so everyone else is blocked.)
5. Under login methods, **One-time PIN** is the simplest: Cloudflare emails you a code each time. Save the application.
6. Test: open `https://agents.yourdomain.com` in a private browser window. You should see a Cloudflare login asking for your email, not the workbench. (The page behind it will say bad gateway until a server is running; that is fine.)
7. Only now set `ACCESS_POLICY_CONFIRMED=true` in `.env`. The script cannot check this for you; the flag is your promise that it is protected.

---

## Part E. Assemble `.env` and test without spending money

1. In Termux:

   ```bash
   cd ~/Cli_workbench
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```

   `nano` tips: arrow keys move, **Ctrl+O** then Enter saves, **Ctrl+X** exits. On the Termux extra-keys row, tap **CTRL**.

2. First-test values for access (no Cloudflare needed):

   ```
   ACCESS_MODE=ssh
   ```

3. Leave `OPENAI_API_KEY=` and `GH_TOKEN=` empty. You will log in from inside the workbench later (see setup.md section 5).
4. Check the file (contacts nothing, costs nothing):

   ```bash
   python3 workbench.py validate
   ```

   It prints the first problem it finds, such as `Missing configuration: ...`. Fix it and run again until it says `Configuration valid`.
5. Only when validation passes, continue with `python3 workbench.py start` as described in [setup.md](setup.md). Starting creates a billable server. Hetzner bills by the hour, and the server is deleted with `destroy`.

If any step does not match what you see on screen, send me a description or a screenshot description (with secrets hidden) and I will adjust the guide.
