# Domain and DNS, step by step (Namecheap, Vercel, Cloudflare)

Goal: a permanent, private address such as `agents.example.com` that opens your workbench from your phone. For this, the domain's DNS must be managed by Cloudflare. DNS is the system that turns a name into a destination. "Nameservers" are the two addresses that say which company answers for the domain.

You only need this if you use `ACCESS_MODE=cloudflare`. `ACCESS_MODE=ssh` needs no domain at all, so the first server test can happen before any of this.

## Choose a path first

| | Path A (recommended) | Path B |
|---|---|---|
| What | Use a **separate, new, cheap domain** just for the workbench | Move your existing agency domain (for example `keyngdev.com`) to Cloudflare DNS |
| Risk to your agency website and email | **None.** You never touch that domain. | Real. A missed record can break the website or email. |
| Effort | About 15 minutes | 1 to 2 hours, plus waiting up to 24 hours |
| Cost | Roughly the yearly price of a cheap domain | Free |

Path A is safer and I recommend it for a tool that you are still testing. You can move to Path B later without changing the workbench, because only `PUBLIC_HOSTNAME` changes.

---

## Path A. A new domain just for the workbench

### A1. Get the domain

Option 1: register it inside Cloudflare (simplest, because the DNS is automatically on Cloudflare).

1. Log in at <https://dash.cloudflare.com/>.
2. In the left menu open **Domains** → **Register Domains** (the page may be titled Domain Registration). Search for a name you like (for example `keyng-workbench.com`). Cloudflare sells domains at cost with no markup.
3. Buy it. Cloudflare Registrar automatically uses Cloudflare DNS, so there is nothing to change. Skip straight to A3. ([Cloudflare confirms this](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/).)

Option 2: buy it at Namecheap, then point it at Cloudflare. Buy the domain, then follow **Path B steps B3 to B5** (the new domain has no records to preserve, so it is quick).

### A2. Hostname

Your hostname will be `agents.<your-new-domain>`, for example `agents.keyng-workbench.com`. You will enter it in two places: the Cloudflare tunnel route and `PUBLIC_HOSTNAME` in `.env`.

### A3. Continue with the tunnel

Go to [credentials.md](credentials.md) Part D and follow D1 to D4.

---

## Path B. Move the agency domain to Cloudflare DNS

Nothing here is automatic. Do not skip steps B1 and B2. Choose a quiet time (not during a client deadline).

### B1. Find out where your DNS lives today

1. Log in to Namecheap → **Domain List** → **Manage** next to the domain.
2. Look at the **Nameservers** drop-down:
   - **Namecheap BasicDNS** → your records live in Namecheap. Open the **Advanced DNS** tab.
   - **Custom DNS** with names such as `ns1.vercel-dns.com` → your records live in Vercel. In Vercel: **Domains** → click the domain → **DNS Records**.
   - **Custom DNS** with other names → your records live at that other provider. Stop and ask me.

   [Namecheap's page on this](https://www.namecheap.com/support/knowledgebase/article.aspx/767/10/how-to-change-dns-for-a-domain/).

### B2. Write down every record (your safety net)

1. Open the list of records at the place you found in B1. Take a screenshot of every page and save it. Also copy the values into a note: type, name, value, priority (for MX), and TTL. Do not forget the root (`@`), `www`, any other subdomains, **MX** (email), **TXT** (SPF, DKIM, DMARC, verification codes), **CAA**, **SRV**.
2. As a second record, in Termux:

   ```bash
   pkg install dnsutils
   D=yourdomain.com
   {
     for t in NS A AAAA MX TXT CAA DS; do echo "== $t"; dig +short $t $D; done
     for h in www mail; do echo "== CNAME $h"; dig +short CNAME $h.$D; done
     echo "== DMARC"; dig +short TXT _dmarc.$D
   } > ~/dns-before.txt
   cat ~/dns-before.txt
   ```

   Keep `~/dns-before.txt`. Run the same commands after the migration and compare.
3. DNSSEC check: if the `== DS` section above is empty, DNSSEC is off and you can ignore this. If it shows a value, DNSSEC is on. Turn it off at Namecheap first (Domain → **Advanced DNS** → DNSSEC toggle, or follow [Namecheap's DNSSEC page](https://www.namecheap.com/support/knowledgebase/article.aspx/9722/2232/managing-dnssec-for-domains-pointed-to-custom-dns/)), because changing nameservers while DNSSEC is on can make the whole domain unreachable. You turn it back on in Cloudflare later.
4. Test now and note the result: your website, `www`, and send/receive a test email.

### B3. Add the domain to Cloudflare

[Cloudflare's official steps](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/).

1. <https://dash.cloudflare.com/> → **Domains** → **Onboard a domain**.
2. Type the domain (for example `keyngdev.com`, with no `www`). Choose to let Cloudflare scan for records. Continue.
3. Choose the **Free** plan.
4. Cloudflare lists the records it found. **The scan is not guaranteed to be complete.** Compare each one with your B2 list. Add anything missing with **Add record**. Delete nothing you are unsure about.
5. For every record that makes your Vercel website work (the root `A` or `CNAME`, and `www`), set **Proxy status** to **DNS only** (grey cloud). Use the exact values listed for your project in Vercel → your project → **Settings → Domains**. Do not copy a generic address from a tutorial. Vercel itself [does not recommend a proxy in front of it](https://vercel.com/kb/guide/cloudflare-with-vercel).
6. Set all email records (MX, SPF/DKIM/DMARC TXT, mail hosts) to **DNS only**.
7. Cloudflare then shows two nameservers, for example `anna.ns.cloudflare.com` and `bob.ns.cloudflare.com`. Copy them exactly and keep this page open.

### B4. Switch the nameservers at Namecheap

1. Namecheap → **Domain List** → **Manage**.
2. In **Nameservers**, choose **Custom DNS**.
3. Enter the two Cloudflare nameservers. Remove any old ones. If the page says to keep only the nameservers, type only the names.
4. Click the green check mark to save.
5. Write down the time you did this and what the old nameservers were (you need them for a rollback).

The old DNS zone (Namecheap or Vercel) stays untouched, so people who still see the old answers while caches expire get the same working answers.

### B5. Wait and verify

1. Back in Cloudflare, click **Check nameservers now** if it appears. The change can take up to 24 hours. Cloudflare emails you when the domain becomes **Active**.
2. In Termux:

   ```bash
   dig +short NS yourdomain.com @1.1.1.1
   ```

   It should list the two Cloudflare names.
3. Repeat the B2 command block into `~/dns-after.txt` and compare: `diff ~/dns-before.txt ~/dns-after.txt`. Differences in NS are expected. Anything else needs explaining.
4. Re-test the website, `www`, and email (send and receive).
5. If you turned DNSSEC off in B2: in Cloudflare open your domain → **DNS** → **Settings** → **DNSSEC** → **Enable DNSSEC**, then copy the DS details to Namecheap as Cloudflare instructs. This is optional.

### B6. Rollback (if the website or email breaks)

1. Namecheap → **Domain List** → **Manage** → **Nameservers**.
2. Set them back to the original value you wrote down in B4 (BasicDNS, or the Vercel nameservers).
3. Wait for caches (up to 24 hours). The old zone was never changed, so service returns.
4. Compare `~/dns-before.txt` with the Cloudflare records to see what was missing, then try again.

### B7. Then the tunnel

When the domain is **Active** and the website and email still work, go to [credentials.md](credentials.md) Part D.

---

## Things to know for later

- **Server replacement:** the hostname points at the tunnel, not at a server address. A new server reconnects with the same tunnel token and no DNS edit is needed. Do not run two independent state copies behind the same tunnel at once.
- **Partial/CNAME setups** (keeping DNS elsewhere) need a paid Cloudflare plan, so this guide does not use them.
- This project never changes DNS automatically, and no one has audited or changed your real domain's records yet.

## Official references

- [Cloudflare full setup](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/)
- [Namecheap: change nameservers](https://www.namecheap.com/support/knowledgebase/article.aspx/767/10/how-to-change-dns-for-a-domain/)
- [Tunnel DNS records](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/)
- [Access self-hosted application](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [Vercel and Cloudflare](https://vercel.com/kb/guide/cloudflare-with-vercel)
