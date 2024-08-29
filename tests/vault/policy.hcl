
# Operations for pytest
# Allow read access to retrieve the token using approle
path "auth/token/lookup" {
  capabilities = ["read"]
}

# Operations for pytest
# Allow updating capabilities for token revocation after creating and testing approle
path "auth/token/revoke" {
  capabilities = ["update"]
}

# Operations for the module
# Enable read access for self-lookup with tokens
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# Operations for pytest
# Allow read, create or update operations on the pytest path
path "sys/mounts/pytest" {
  capabilities = ["read", "create", "update"]
}

# Operations for pytest
# Allow reading database credentials for a role 
path "database/creds/pytest" {
  capabilities = ["read"]
}

###############################################################

# Operations for the module
# Read and update namespace configuration
path "pyinstabot-downloader/config" {
  capabilities = ["read", "list", "update"]
}

# Operations for the module
# Work with secret application data
path "pyinstabot-downloader/data/configuration/*" {
  capabilities = ["create", "read", "update", "list"]
}

# Operations for the module
# Work with secret event data
path "pyinstabot-downloader/data/data/*" {
  capabilities = ["create", "read", "update", "list"]
}

# Allowed to read bot history
path "pyinstabot-downloader/metadata/history/*" {
  capabilities = ["read", "list"]
}

# Allowed to create, read, update, and list bot history
path "pyinstabot-downloader/data/history/*" {
  capabilities = ["create", "read", "list", "update"]
}

# Allowed to read and list of user configurations
path "pyinstabot-downloader/metadata/configuration/users" {
  capabilities = ["read", "list"]
}

# Allow reading database credentials for a role 
path "database/creds/pyinstabot-downloader"{
  capabilities = ["read"]
}
