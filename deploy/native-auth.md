# Native web authentication

FastAPI owns the login and session boundary. Nginx forwards the site on an HTTPS origin; Cloudflare provides proxied DNS and edge TLS. The app uses a separate SQLite database for account, session and login-attempt records. Existing trace databases are left intact. Each new account gets its own notes, trace database, runtime settings, upload directory and live tool approval queue. Administrators manage accounts and their own workspace settings. Account administration does not grant access to other users’ workspace data.

## Authorization map

| Routes | Policy |
| --- | --- |
| `GET /`, `/assets/*` | Public login shell and compiled assets. No workspace data in the bundle. |
| `POST /api/auth/login` | No session required. Exact browser origin, credentials and login limits apply. |
| `GET /api/auth/session`, `POST /api/auth/logout` | Active session. Logout also requires CSRF verification. |
| `GET`, `POST /api/auth/users`; `PATCH /api/auth/users/{id}` | Active administrator session. Writes require CSRF verification. |
| `/api/settings` | Active administrator session. Settings apply to that administrator’s own workspace. |
| `/api/workspace/*`, `/api/sessions/*`, `/api/meters` | Active session, confined to the account’s own records. |
| `/api/chat`, `/api/uploads`, `/api/approvals/*`, `/api/turns/*`, `/api/workspace/graph/build` | Active session with administrator-assigned agent access. Turn and approval IDs are scoped to the account. |
| API documentation, schema and registration | No routes are published. |

Every authenticated write requires both the configured origin and the session’s CSRF token. Native web mode excludes `bash` from the enabled tools and the per-account registry because shell execution can escape file-level workspace isolation. The existing offline CLI retains its tool configuration.

## Prepare a release

1. Build the frontend and install `requirements.txt`, `requirements-ui.txt` and, if needed, `requirements-rag.txt` in the isolated release. Run Python and frontend CI on the release to be installed.
2. Stage the reviewed release under `/opt/ai-blue/releases/` and point `/opt/ai-blue/native-current` at it. Install `deploy/systemd/ai-blue-native.service` using a dedicated `ai-blue-native` service account. It binds to `127.0.0.1:8186`, uses private state under `/var/lib/ai-blue-native`, and runs alongside the previous service on port 8180. Use one Uvicorn worker because live agent turns and approvals are in memory. Keep provider keys in the root-only service environment file outside Git.
3. Run the following command from the new release using its virtual environment. Enter the password at the terminal. It is never passed as an argument. The first open applies the versioned SQLite migration. Bootstrap is valid only while the account database is empty.

   ```sh
   sudo -u ai-blue-native env AIBLUE_AUTH_DIR=/var/lib/ai-blue-native/auth .venv/bin/python main.py bootstrap-admin <username>
   ```

   Save a protected backup of `accounts.sqlite3` before future migrations. Provision other accounts in the Users screen. Give agent access only to the intended accounts. Do not seed account data by copying the existing shared notes or trace directories. A release operator can review and import selected notes into individual accounts separately if authorized.

## Origin and cutover

- Preserve the existing Nginx configuration, release/service definition, and overview plus its TLS rollback template. Do not use the staged Cloudflare Access JWT proxy or install its verifier service for native authentication.
- Install the hostname-specific origin certificate signed from the existing CSR. Approve and verify TCP 443 ingress restricted to Cloudflare’s published IP ranges. Create `/etc/ai-blue/cloudflare-real-ip.conf` with `set_real_ip_from` entries for those ranges only. Rate limits use the validated client IP passed by Nginx. Keep the backend port private. [Cloudflare proxy networks](https://www.cloudflare.com/ips/)
- Keep DNS proxied. In the approved window, first verify origin HTTPS with the static overview, then enable Cloudflare Full (strict) and HTTP-to-HTTPS redirection scoped to `public.geopolitics.io`. Bypass edge caching for the hostname’s HTML and API. Leave internal and research rules in place. [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
- Validate the native backend on loopback before replacing the existing public vhost with `deploy/nginx/ai-blue-native.conf`. Run `nginx -t` before a graceful reload. Test the login shell and signed-out API denial from an external client, valid team sign-in and workspace, uploads, SSE and approvals, and direct-origin rejection. Verify the internal and research sites again. Real model calls require provider credentials.
- For rollback while Cloudflare uses Full (strict), restore `/opt/ai-blue/access-stage/public-geopolitics.overview-tls.conf.template` to `/etc/nginx/conf.d/public-geopolitics.conf`, validate with `nginx -t` and reload Nginx. Verify the static overview and API 404 before restoring the prior backend service definition if needed. Keep the native account database and per-account workspace files for a later attempt. The earlier HTTP-only overview backup is suitable only after reverting the hostname’s origin TLS mode.

## Login limits and certificate renewal

Login attempts are limited to five per username and validated client IP in a 15-minute window. A successful sign-in clears that pair’s count. There is no global, username-only, or IP-only lockout bucket. Argon2 work is bounded separately by a concurrency limit. A different account on the same shared IP, or the same account signing in from another IP, is unaffected by a locked pair.

For the Let's Encrypt origin certificate, retain the managed ACME challenge location on both HTTP and HTTPS in each public-host vhost, including the TLS overview rollback. Install `deploy/nginx/ai-blue-acme-challenge.conf` at `/etc/ai-blue/acme-challenge.conf` and serve only the validation files in `/var/www/ai-blue-acme`. The `deploy/acme/` units run the CSR-based renewal check daily and replace the certificate only after validating its hostname, chain, and key match. Keep the ACME account and certificate key private on the VM. Validate renewal against the Let's Encrypt staging CA before cutover.
