# /bin/bash
# Description: Prepare vault for pyinstabot-downloader

# Prepare kv2 engine
vault secrets enable -path=pyinstabot-downloader kv-v2 

# Prepare approle
vault policy write pyinstabot-downloader vault/policy.hcl
vault auth enable -path=pyinstabot-downloader approle
vault write auth/pyinstabot-downloader/role/pyinstabot-downloader \
    token_policies=["pyinstabot-downloader"] \
    token_type=service \
    secret_id_num_uses=0 \
    token_num_uses=0 \
    token_ttl=24h \
    bind_secret_id=true \
    mount_point="pyinstabot-downloader" \
    secret_id_ttl=0

# Prepare db engine
vault secrets enable -path=pyinstabot-downloader-database database
vault write pyinstabot-downloader-database/config/postgresql \
    plugin_name=postgresql-database-plugin \
    allowed_roles="pyinstabot-downloader" \
    verify_connection=false \
    connection_url="postgresql://{{username}}:{{password}}@localhost:5432/pyinstabot-downloader?sslmode=disable" \
    username="postgres" \
    password="changeme"
vault write pyinstabot-downloader-database/roles/pyinstabot-downloader \
    db_name=postgresql \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON SCHEMA public TO \"{{name}}\"; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"{{name}}\"; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"{{name}}\";" \
    revocation_statements="REVOKE ALL PRIVILEGES ON SCHEMA public FROM \"{{name}}\"; REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"; REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM \"{{name}}\"; DROP ROLE \"{{name}}\";" \
    default_ttl="24h" \
    max_ttl="72h"
# End of snippet
