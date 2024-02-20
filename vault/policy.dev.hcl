# Allowed to look up the approle token
path "auth/token/lookup" {
  capabilities = ["read"]
}

# Allowed to revoke the approle token
path "auth/token/revoke" {
  capabilities = ["update"]
}

# Allowed to look up its own approle token
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# Allowed to connect a mount point and update settings
path "pyinstabot-downloader-dev/config" {
  capabilities = ["update"]
}

# Allowed to list bot configurations
path "pyinstabot-downloader-dev/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed to read other configurations
path "pyinstabot-downloader-dev/data/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed read and write of bot data
path "pyinstabot-downloader-dev/data/data/*" {
  capabilities = ["read", "list", "create", "update"]
}



# Allowed to read bot history (!!!deprecated after migration to database!!!)
path "pyinstabot-downloader-dev/metadata/history/*" {
  capabilities = ["read", "list"]
}

# Allowed to create, read, update, and list bot history (!!!deprecated after migration to database!!!)
path "pyinstabot-downloader-dev/data/history/*" {
  capabilities = ["create", "read", "list", "update"]
}

# Allowed to read and record security events by a bot (!!!deprecated after v2.1.0 !!!)
path "pyinstabot-downloader-dev/data/events/*" {
  capabilities = ["read", "list", "create", "update"]
}
