#!/usr/bin/env bash
# Run on an expendable Linux review runner with Node 22, npm, Python and curl.
# Uses temporary state, no cloud credentials and no model calls.
set -euo pipefail
workbench_tmp="$(mktemp -d)"
workbench_pid=""
cleanup() {
  if test -n "$workbench_pid"; then
    kill -- "-$workbench_pid" 2>/dev/null || true
    wait "$workbench_pid" 2>/dev/null || true
  fi
  rm -rf "$workbench_tmp"
}
trap cleanup EXIT
mkdir -p "$workbench_tmp/home" "$workbench_tmp/workspace"
cloudcli_version="$(python3 -c 'from workbench.config import DEFAULTS; print(DEFAULTS["CLOUDCLI_VERSION"])')"
codex_version="$(python3 -c 'from workbench.config import DEFAULTS; print(DEFAULTS["CODEX_VERSION"])')"
npm install --prefix "$workbench_tmp/packages" --no-audit --no-fund \
  "@cloudcli-ai/cloudcli@$cloudcli_version" "@openai/codex@$codex_version"
env HOME="$workbench_tmp/home" "$workbench_tmp/packages/node_modules/.bin/codex" --version
env HOME="$workbench_tmp/home" HOST=127.0.0.1 PORT=31987 \
  WORKSPACES_ROOT="$workbench_tmp/workspace" DATABASE_PATH="$workbench_tmp/home/auth.db" \
  NODE_ENV=production \
  setsid "$workbench_tmp/packages/node_modules/.bin/cloudcli" >"$workbench_tmp/runtime.log" 2>&1 &
workbench_pid="$!"
for _ in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:31987/health >/dev/null; then
    echo 'Pinned Codex executable and CloudCLI HTTP health smoke test passed.'
    exit 0
  fi
  if ! kill -0 "$workbench_pid" 2>/dev/null; then
    cat "$workbench_tmp/runtime.log"
    exit 1
  fi
  sleep 2
done
cat "$workbench_tmp/runtime.log"
echo 'CloudCLI health timeout' >&2
exit 1
