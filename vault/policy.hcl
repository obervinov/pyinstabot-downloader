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
path "pyinstabot-downloader/config" {
  capabilities = ["update"]
}

# Allowed to list bot configurations
path "pyinstabot-downloader/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed to read other configurations
path "pyinstabot-downloader/data/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed read and write of bot data (!!!deprecated after https://github.com/obervinov/users-package/issues/41!!!)
path "pyinstabot-downloader/data/data/*" {
  capabilities = ["read", "list", "create", "update"]
}



# Allowed to read bot history (!!!deprecated after migration to database!!!)
path "pyinstabot-downloader/metadata/history/*" {
  capabilities = ["read", "list"]
}

# Allowed to create, read, update, and list bot history (!!!deprecated after migration to database!!!)
path "pyinstabot-downloader/data/history/*" {
  capabilities = ["create", "read", "list", "update"]
}

# Allowed to read and record security events by a bot (!!!deprecated after v2.1.0 !!!)
path "pyinstabot-downloader/data/events/*" {
  capabilities = ["read", "list", "create", "update"]
}
