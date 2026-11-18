# deploy/

Production serves native sign-in at [public.geopolitics.io](https://public.geopolitics.io/). AI-Blue runs directly on the GCP VM as the systemd service `ai-blue-native.service`. The unit starts `main.py serve` with the Python virtual environment in `/opt/ai-blue/native-current` and binds to `127.0.0.1:8186`. Nginx terminates origin HTTPS and proxies the public hostname to that listener.

- `systemd/` holds the native app service template.
- `nginx/` holds the HTTPS reverse proxy and ACME challenge templates.
- `acme/` holds the systemd certificate renewal timer and service.
- `docker/` is an empty placeholder for possible future container packaging.

Inject credentials through the service environment or a secret manager. Keep live configuration on the server and deployment templates here.

The [native web authentication guide](native-auth.md) covers release preparation, verification, and the TLS overview rollback procedure.
