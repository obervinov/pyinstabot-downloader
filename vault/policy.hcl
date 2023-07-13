# for manage approle token
path "auth/token/lookup" {
  capabilities = ["read"]
}
# for manage approle token
path "auth/token/revoke" {
  capabilities = ["update"]
}
# for manage secret
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
# for manage secret
path "pyinstabot-downloader/config" {
  capabilities = ["update"]
}
# for manage bot configuration
path "pyinstabot-downloader/configuration/*" {
  capabilities = ["read", "list"]
}
# for manage bot configuration
path "pyinstabot-downloader/data/configuration/*" {
  capabilities = ["read", "list"]
}
# for manage bot configuration
path "pyinstabot-downloader/history/*" {
  capabilities = ["create", "read", "list", "update"]
}
# for manage bot configuration
path "pyinstabot-downloader/events/login/*" {
  capabilities = ["read", "list", "create", "update"]
}
