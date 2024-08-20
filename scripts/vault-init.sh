# /bin/bash
# Description: Prepare vault for pyinstabot-downloader
vault secrets enable -path=pyinstabot-downloader kv-v2 
vault policy write pyinstabot-downloader vault/policy.hcl
vault auth enable -path=pyinstabot-downloader approle
vault write auth/pyinstabot-downloader/role/pyinstabot-downloader \
    token_policies=["pyinstabot-downloader"] \
    token_type=service \
    secret_id_num_uses=0 \
    token_num_uses=0 \
    token_ttl=1h \
    bind_secret_id=true \
    mount_point="pyinstabot-downloader" \
    secret_id_ttl=0
# End of snippet