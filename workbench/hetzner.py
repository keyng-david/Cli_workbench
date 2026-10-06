"""Hetzner API adapter; resource-creating requests are never blindly retried."""
import json
import urllib.error
import urllib.parse
import urllib.request
from .config import Error

class Hetzner:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, data=None):
        request = urllib.request.Request(
            "https://api.hetzner.cloud/v1" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise Error(f"Hetzner {method} {path.split('?')[0]} returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise Error("Hetzner request failed; reconcile with status/start before retrying creation") from exc

    def servers(self, name):
        selector = urllib.parse.quote(f"managed-by=cli-workbench,workbench={name}")
        results, page = [], 1
        while True:
            data = self.request("GET", f"/servers?label_selector={selector}&per_page=50&page={page}")
            results.extend(data["servers"])
            page = data.get("meta", {}).get("pagination", {}).get("next_page")
            if not page:
                return results

    def ssh_key(self, key_id):
        return self.request("GET", f"/ssh_keys/{int(key_id)}")["ssh_key"]

    def get(self, server_id):
        return self.request("GET", f"/servers/{int(server_id)}")["server"]

    def create(self, cfg, instance):
        return self.request("POST", "/servers", {
            "name": cfg["WORKBENCH_NAME"], "server_type": cfg["HCLOUD_SERVER_TYPE"],
            "location": cfg["HCLOUD_LOCATION"], "image": cfg["HCLOUD_IMAGE"],
            "ssh_keys": [int(cfg["HCLOUD_SSH_KEY_ID"])],
            "labels": {"managed-by": "cli-workbench", "workbench": cfg["WORKBENCH_NAME"], "instance": instance},
            "public_net": {"enable_ipv4": True, "enable_ipv6": True},
            "user_data": "#cloud-config\nssh_pwauth: false\ndisable_root: false\n",
        })["server"]

    def delete(self, server_id):
        return self.request("DELETE", f"/servers/{int(server_id)}")
