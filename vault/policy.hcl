path "auth/token/lookup" {
  capabilities = ["read"]
}
path "auth/token/renew" {
  capabilities = ["update"]
}
path "pyinstabot-downloader/configuration/data/*" {
  capabilities = ["read", "list"]
}
path "pyinstabot-downloader/history/data/*" {
  capabilities = ["create", "read", "list", "update"]
}
path "pyinstabot-downloader/events/login/*" {
  capabilities = ["read", "list", "create", "update"]
}