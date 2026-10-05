#!/usr/bin/env bash
set -euo pipefail
umask 077
export DEBIAN_FRONTEND=noninteractive
cd /opt/cli-workbench
test "$(id -u)" = 0
test "$(dpkg --print-architecture)" = amd64
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
cloud-init status --wait >/dev/null 2>&1 || test -f /var/lib/cloud/instance/boot-finished
mkdir -p /var/lib/cli-workbench
exec 9>/var/lib/cli-workbench/bootstrap.lock
flock -n 9
if test -f /var/lib/cli-workbench/ready; then
  echo 'Already installed; use resume to start services.'
  exit 0
fi
apt-get update
apt-get install -y ca-certificates curl gnupg build-essential python3 git gh restic ufw tmux unzip pkg-config
install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o /tmp/workbench-node-key
gpg --batch --yes --dearmor -o /etc/apt/keyrings/nodesource.gpg /tmp/workbench-node-key
chmod 0644 /etc/apt/keyrings/nodesource.gpg
echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main' > /etc/apt/sources.list.d/nodesource.list
curl --fail --silent --show-error --location https://pkg.cloudflare.com/cloudflare-main.gpg -o /etc/apt/keyrings/cloudflare-main.gpg
chmod 0644 /etc/apt/keyrings/cloudflare-main.gpg
echo 'deb [signed-by=/etc/apt/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/cloudflared.list
apt-get update
apt-get install -y nodejs cloudflared
id dev >/dev/null 2>&1 || useradd --create-home --shell /bin/bash dev
install -d -o dev -g dev -m 0755 /workspace
install -d -o dev -g dev -m 0755 /opt/workbench-packages
python3 remote/setup.py
echo 'Bootstrap complete. Open the protected URL and finish agent/GitHub login.'
