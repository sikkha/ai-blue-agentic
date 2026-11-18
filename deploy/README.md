# deploy/

Deployment infrastructure, kept separate from application source.

    docker/   Dockerfiles, and docker-compose files if needed
    nginx/    reverse-proxy configuration

Rules:
- No secrets or real credentials in any file here. Inject via environment or a secret manager.
- Production configuration templates may live here; real values do not.

The [native web authentication guide](native-auth.md) covers the database, service, TLS proxy, verification, and rollback. The Nginx template is staged for review before production cutover.
