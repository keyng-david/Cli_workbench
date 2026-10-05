# Architecture and extension points

The controller is Python standard-library code in workbench/, using a small Hetzner API adapter and OpenSSH. It owns resource identity, creation/reconciliation, upload and deletion. The provider token and SSH private key stay on the phone/laptop.

Remote bootstrap installs packages and services on dedicated Ubuntu 24.04 AMD64. After upload, systemd owns installation, so closing Termux does not stop it. CloudCLI and Codex run as dev at fixed /home/dev and /workspace paths. The UI listens on loopback; cloudflared connects outward. Root holds backup/tunnel config; dev has no sudo grant.

Remote state operations stop writers, snapshot native/UI state, encrypt to S3/R2 and verify a full read-back before normal deletion. Provider paths and package versions are part of the persistence contract.

## Identity and recovery

A local operation lock prevents overlapping commands from the same checkout. The server has managed-by, workbench and unique instance labels. A pending identity is saved before the create API call. Unknown outcomes block blind recreation. Deletion checks labels and a new backup receipt for the exact instance.

Local state is .workbench/NAME/, with restricted permissions. SSH known-hosts files are scoped to the server ID. First contact uses accept-new (trust on first use); compare the initial host fingerprint through a trusted Hetzner channel if stronger validation is required. Changed keys for a known instance are rejected.

One controller and one live server per workbench are supported. There is no distributed lock across phones/laptops. Do not run independent state copies under one tunnel.

## Security boundary

Administrative root SSH uses the uploaded public key; dev has no SSH key or sudo permission. The ssh command enters a developer shell through the administrative connection. Agent/GitHub credentials belong to dev and are accessible to its tasks. This is a personal workspace, not a hostile-code or multi-tenant security sandbox.

UFW protects incoming ports after bootstrap; the initial OS SSH policy applies before then. For protection from allocation time, configure a provider firewall separately. Workbench does not create that resource. CloudCLI remains bound to loopback even without the tunnel.

## Extending

Add cloud-provider list/get/create/delete operations in a new adapter, then explicit config validation and resource-safety tests.

An agent adapter should include installer/authentication behavior, pinned versions, native state paths, credential rules and resume tests. Add persistence and tests alongside installation before advertising multi-agent support.

CloudCLI is installed unmodified. Its current package includes Codex and other provider dependencies. Explicit CLI pinning supports terminal use but does not mean the npm dependency tree contains no other agent packages. Respect upstream licenses when distributing modified versions or images.

## Intentional v1 limits

No DNS automation, idle deletion, Telegram, periodic backup, full source backup, persistent disk, multi-machine replication, automatic upgrade engine or automatic task acceptance. Backup/deletion currently needs an intact controller/SSH connection. A partial upload can need retry on the same server.
