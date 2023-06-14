path "auth/token/lookup" {
  capabilities = ["read"]
}
path "auth/token/renew" {
  capabilities = ["update"]
}
path "auth/token/revoke" {
  capabilities = ["update"]
}
path "pyinstabot-downloaderconfiguration/data/*" {
  capabilities = ["read", "list"]
}
path "pyinstabot-downloaderhistory/data/*" {
  capabilities = ["create", "read", "list", "update"]
}
path "pyinstabot-downloaderevents/login/*" {
  capabilities = ["read", "list", "create", "update"]
}