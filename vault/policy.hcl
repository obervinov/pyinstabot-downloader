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

# Allowed to read and generate credentials in database engine
path "pyinstabot-downloader-database/creds" {
  capabilities = ["read", "list", "update"]
}

# Allowed read and write of bot data (!!! deprecated after https://github.com/obervinov/users-package/issues/41)
path "pyinstabot-downloader/data/data/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Allow read users data for metric-server (!!! deprecated after v2.3.0 because it will be transferred to the database)
path "pyinstabot-downloader/metadata/data/users" {
  capabilities = ["list"]
}
