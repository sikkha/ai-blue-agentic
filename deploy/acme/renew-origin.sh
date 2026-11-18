#!/bin/sh
# Run only as the origin's systemd renewal service, with the existing CSR and key.
set -eu
umask 077

tls=/etc/ai-blue/tls
hostname=public.geopolitics.io
certificate="$tls/$hostname.crt"
csr="$tls/$hostname.csr"
certbot=/opt/ai-blue/acme/venv/bin/certbot

if openssl x509 -in "$certificate" -noout -checkend 2592000 >/dev/null 2>&1; then
    printf '%s\n' 'Origin certificate is valid for more than 30 days.'
    exit 0
fi

stage=$(mktemp -d "$tls/.renewal.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
(
    # ACME challenge files must be readable by the Nginx worker. The account
    # and logs are stored separately in private directories.
    umask 022
    "$certbot" certonly --quiet --webroot -w /var/www/ai-blue-acme \
        --non-interactive --csr "$csr" --config-dir /etc/ai-blue/acme \
        --work-dir /var/lib/ai-blue-acme/work --logs-dir /var/lib/ai-blue-acme/logs \
        --cert-path "$stage/cert.pem" --chain-path "$stage/chain.pem" \
        --fullchain-path "$stage/fullchain.pem"
)
openssl verify -verify_hostname "$hostname" -CApath /etc/ssl/certs \
    -untrusted "$stage/chain.pem" "$stage/cert.pem"
openssl x509 -in "$stage/cert.pem" -noout -pubkey > "$stage/cert.pub"
openssl pkey -in "$tls/$hostname.key" -pubout > "$stage/origin.pub"
cmp "$stage/cert.pub" "$stage/origin.pub"
cp -p "$certificate" "$stage/previous.crt"
chmod 0644 "$stage/fullchain.pem"
mv "$stage/fullchain.pem" "$certificate"
if ! nginx -t || ! systemctl reload nginx; then
    mv "$stage/previous.crt" "$certificate"
    nginx -t
    systemctl reload nginx
    exit 1
fi
printf '%s\n' 'Renewed the public origin certificate and reloaded Nginx.'
