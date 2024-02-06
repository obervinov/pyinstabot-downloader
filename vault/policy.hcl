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

# Allowed to read bot configuration
path "pyinstabot-downloader/data/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed to read bot history
path "pyinstabot-downloader/metadata/history/*" {
  capabilities = ["read", "list"]
}

# Allowed to read users list
path "pyinstabot-downloader/metadata/configuration/*" {
  capabilities = ["read", "list"]
}

# Allowed to create, read, update, and list bot history
path "pyinstabot-downloader/data/history/*" {
  capabilities = ["create", "read", "list", "update"]
}

# Allowed to read and record security events by a bot
path "pyinstabot-downloader/data/events/*" {
  capabilities = ["read", "list", "create", "update"]
}
