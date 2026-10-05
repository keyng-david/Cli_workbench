# Preserve Namecheap + Vercel while adding Cloudflare Tunnel

Your domain can stay registered with Namecheap and hosted on Vercel while Cloudflare becomes its authoritative DNS provider. Changing nameservers affects DNS for the entire domain. It is safe only when the existing records are preserved correctly. This project never changes DNS automatically.

| Hostname | Destination | Proxy mode |
|---|---|---|
| keyngdev.com / @ | Exact values currently required by your Vercel project | DNS only |
| www.keyngdev.com | Exact Vercel CNAME target | DNS only |
| agents.keyngdev.com | TUNNEL_UUID.cfargotunnel.com | Proxied, protected by Access |
| Mail/other subdomains | Existing values preserved | As required; mail hosts normally DNS only |

Use Vercel Project Settings → Domains and the current authoritative zone. Do not paste a generic Vercel IP from a tutorial: project-specific targets can differ.

## Before switching

1. Inspect current nameservers in Namecheap. Vercel nameservers mean the live zone is in Vercel; Namecheap BasicDNS means it is in Namecheap Advanced DNS. Copy from the actual authoritative provider.
2. Export the zone and retain a readable inventory: type, name, value, TTL, priority. Include root, www, all other subdomains, MX, SPF, DKIM selectors, DMARC, CAA, SRV and verification TXT records. Automatic scanning can miss records.
3. Save current nameservers and DNSSEC/DS status for recovery.
4. Test your website, www and email as a baseline.
5. Add keyngdev.com to Cloudflare and compare every imported record with your inventory.
6. Set Vercel website records to **DNS only** (grey cloud). This uses Cloudflare for DNS without sending site traffic through a second reverse proxy.
7. If DNSSEC is enabled at the old provider, follow Cloudflare's migration instructions to remove/disable the old DS delegation before switching. A stale DS record can break resolution for the whole domain.

## One-time migration

1. Copy Cloudflare's two assigned nameservers into Namecheap's Custom DNS field. Domain registration remains at Namecheap.
2. Keep the old DNS zone and Vercel domain attachment intact during the transition. Both old and new zones should return equivalent website/email answers while caches expire.
3. Wait for Cloudflare to mark the zone active. Initial delegation takes time; do not assume an exact propagation duration.
4. Check root domain, www, Vercel domain status and email from more than one connection.
5. Re-enable DNSSEC using Cloudflare's new DS details if desired.
6. Add the named tunnel's published application hostname. Cloudflare normally creates its CNAME. Remove conflicting records only after confirming they are for the new workbench hostname.
7. Configure Access and verify unauthorized visitors cannot reach CloudCLI.

If the agency site fails, check copied A/AAAA/CNAME values and DNSSEC first. The deployment has not moved off Vercel. Correct the zone or deliberately roll back nameservers and matching DNSSEC delegation. Keep a written change log.

## Future server replacement

The hostname points to the persistent tunnel identity, not a VPS IP. Each replacement reconnects using that tunnel token. No new DNS edit or propagation cycle is needed. Do not run independent state copies behind the same tunnel simultaneously.

## Postpone domain changes if preferred

ACCESS_MODE=ssh supports an initial installation test without modifying the agency DNS. It requires a live SSH forwarding connection and is not the final PWA experience. This release does not expose the terminal/UI through an unprotected temporary URL.

Cloudflare partial DNS and separately delegated subdomain setups can have plan restrictions; they are not assumed by this guide.

## Official references

- [Cloudflare full setup](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/)
- [Tunnel DNS records](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/)
- [Access self-hosted application](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [Vercel guidance on Cloudflare](https://vercel.com/kb/guide/cloudflare-with-vercel)

The actual keyngdev.com zone has not been audited or modified during implementation.
