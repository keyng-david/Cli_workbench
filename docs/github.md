# GitHub: sign-in, Git identity and getting your code onto the server

Every server is brand new, so it starts with no GitHub login, no Git name/email and no code. CloudCLI's **Create New Project** screen asks for either a folder path on the server or a GitHub URL. This guide makes all three automatic.

## What is automated (and why GitHub login is not "backed up")

| Item | How it comes back on each new server |
|---|---|
| GitHub login | `GH_TOKEN` in your `.env`. The installer signs in with it and configures Git to use it. |
| Git name and email | `GIT_USER_NAME` and `GIT_USER_EMAIL` in `.env`. |
| Your code | `CLONE_REPOS` in `.env`: cloned into `/workspace/<repo>` automatically. |

The GitHub login is deliberately **not** in the encrypted backup. Putting a token in the backup would put a second copy of it in cloud storage. Because your `.env` supplies it each time, restoring it from backup is unnecessary. A token that expires is simply replaced in `.env`.

Restoring conversation history works best when the code is cloned to the **same path** as before (`/workspace/<repo>`). `CLONE_REPOS` does that for you.

## 1. Create a restricted GitHub token

Use a fine-grained token limited to the repositories you want the agent to touch. If it ever leaks, only those repositories are exposed, and it expires on its own.

1. Open <https://github.com/settings/personal-access-tokens/new> (GitHub → profile picture → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token).
2. **Token name:** `workbench`.
3. **Expiration:** 30 or 90 days. You will replace it when it expires.
4. **Resource owner:** the account that owns the repositories (you, or the organization). Organization-owned repositories may need an owner to approve the token.
5. **Repository access:** **Only select repositories**, then choose the repositories (for example `mail-builder`).
6. **Repository permissions:**
   - **Contents: Read and write** (clone, commit, push branches)
   - **Pull requests: Read and write** (open PRs)
   - **Metadata: Read** (added automatically)
   - Add **Workflows: Read and write** only if the agent must edit files in `.github/workflows`.
7. Click **Generate token** and copy it (starts with `github_pat_`). GitHub shows it only once.

The agent can use this token, so grant only what you need. Do not give it permission over repositories you would not let the agent change.

If the installer's sign-in step ever rejects a fine-grained token, create a classic token with the `repo` scope instead (worse isolation, so keep the expiry short).

## 2. Put it in `.env`

```
GH_TOKEN=github_pat_xxxxxxxx
GIT_USER_NAME=David Agu
GIT_USER_EMAIL=your-github-commit-email@example.com
CLONE_REPOS=keyng-david/mail-builder
```

- `CLONE_REPOS` takes a comma-separated list: `owner/repo,owner/other-repo`. Anything not shaped like `owner/repo` is rejected by `validate`.
- Use your real GitHub commit email, or your `ID+username@users.noreply.github.com` address from GitHub → Settings → Emails.
- All four lines are optional. Leave a line empty to skip it.

Then run `python3 workbench.py validate` and `start` as usual. The install log shows `Cloning keyng-david/mail-builder into /workspace/mail-builder`. If a clone fails, the install still finishes and prints a `WARNING` line; it does not block the workbench.

## 3. Open the project in CloudCLI

In **Create New Project**, put the folder path in **Workspace Path**: `/workspace/mail-builder` (the folder `CLONE_REPOS` created). Leave **GitHub URL** empty and click Next.

You can also paste a GitHub URL there. That works for private repositories only after the server is signed in to GitHub (which `GH_TOKEN` does), and not before.

## 4. If this server is already running without a token (manual, one time)

From Termux, open a shell on the server and sign in with the device code (no localhost redirect):

```bash
python3 workbench.py ssh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git config --global user.name "David Agu"
git config --global user.email "you@example.com"
cd /workspace
git clone https://github.com/keyng-david/mail-builder.git
exit
```

`gh` prints a short code and a link. Open the link on your phone and enter the code. Then use `/workspace/mail-builder` in CloudCLI. This is lost when the server is deleted, so prefer the `.env` method above.

Close that shell (`exit`) before running a backup or destroy, because they refuse while a developer shell is open.

## 5. Other ways to get files onto the server

- **Push from your phone to GitHub, then clone.** This is the safest way, and it keeps a copy outside the server.
- **Public repositories** need no token: `CLONE_REPOS` or the GitHub URL field works as is.
- **Files that are not in Git** (env files, assets): use `python3 workbench.py ssh` and paste them with an editor such as `nano`, or ask for an upload command to be added. They are not backed up. Only Git work is protected from deletion, so save anything you need to keep.
- **Secrets for your project** (`.env` files) are not part of the backup or the clone. Re-create them on each new server.

## 6. Before you destroy

Push every branch. `destroy --quiesce` refuses to delete a server that has uncommitted files, stashes, or commits not pushed to GitHub. That check is what protects your work.
