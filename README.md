# Pyinstabot-downloader
[![Release](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/release.yml/badge.svg)](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/release.yml)
[![CodeQL](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/github-code-scanning/codeql)
[![Tests and checks](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/tests.yml/badge.svg?branch=main&event=pull_request)](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/tests.yml)
[![Build](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/build.yml/badge.svg?branch=main&event=pull_request)](https://github.com/obervinov/pyinstabot-downloader/actions/workflows/build.yml)

![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/obervinov/pyinstabot-downloader?style=for-the-badge)
![GitHub last commit](https://img.shields.io/github/last-commit/obervinov/pyinstabot-downloader?style=for-the-badge)
![GitHub Release Date](https://img.shields.io/github/release-date/obervinov/pyinstabot-downloader?style=for-the-badge)
![GitHub issues](https://img.shields.io/github/issues/obervinov/pyinstabot-downloader?style=for-the-badge)
![GitHub repo size](https://img.shields.io/github/repo-size/obervinov/pyinstabot-downloader?style=for-the-badge)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/instaloader?style=for-the-badge)





## <img src="https://github.com/obervinov/_templates/blob/main/icons/book.png" width="25" title="about"> About this project
This project is a telegram bot that allows you to backup content from your Instagram profile to the Dropbox cloud or to the local filesystem.

Main functions:
- download the content of all posts from the profile
- download the content of one post by target link
- save the download content to the dropbox or to the local of filesystem


The vault is used for:
- storing confidential project configuration parameters
- storing the history of already uploaded shortcodes of posts
- storing information about user authorization events

<p align="center">
  <img src="doc/bot-preview.gif" width="1000" title="bot-preview">
  <img src="doc/instagram-profile.png" width="500" alt="instagram-profile">
</p>


## <img src="https://github.com/obervinov/_templates/blob/main/icons/stack.png" width="25" title="stack"> Repository map
```sh
.
├── CHANGELOG.md
├── Dockerfile
├── LICENSE
├── README.md
├── SECURITY.md
├── doc
│   ├── bot-preview.gif
│   └── instagram-profile.png
├── docker-compose.yml
├── requirements.txt
└── src
    ├── bot.py
    ├── configs
    │   ├── messages.json
    │   └── settings.py
    └── extensions
        ├── __init__.py
        ├── downloader.py
        └── uploader.py
```


## <img src="https://github.com/obervinov/_templates/blob/main/icons/requirements.png" width="25" title="requirements"> Requirements
- <img src="https://github.com/obervinov/_templates/blob/main/icons/vault.png" width="15" title="vault"> Vault server - [a storage of secrets for bot with kv v2 engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- <img src="https://github.com/obervinov/_templates/blob/main/icons/dropbox.ico" width="15" title="dropbox"> Dropbox api token - [instructions for generating a token of api](https://dropbox.tech/developers/generate-an-access-token-for-your-own-account)
- <img src="https://github.com/obervinov/_templates/blob/main/icons/telegram.png" width="15" title="telegram"> Telegram bot api token - [instructions for creating bot and getting a token of api](https://learn.microsoft.com/en-us/azure/bot-service/bot-service-channel-connect-telegram?view=azure-bot-service-4.0)
- <img src="https://github.com/obervinov/_templates/blob/main/icons/instagram.png" width="15" title="instagram"> Instagram username/password - [login and password from the instagram account, it is advisable to create a new account](https://www.instagram.com/accounts/emailsignup/)


## <img src="https://github.com/obervinov/_templates/blob/main/icons/build.png" width="25" title="build"> Environment variables
| Variable  | Description | Default value |
| ------------- | ------------- | ------------- |
| `LOGGER_LEVEL` | [The logging level of the logging module](https://docs.python.org/3/library/logging.html#logging-levels) | `INFO` |
| `BOT_NAME` | The name of the bot, used to determine the unique mount point in the vault | `pyinstabot-downloader` |
| `STORAGE_TYPE` | Type of target storage for saving uploaded content from instagram (`dropbox` or `local`) | `local` |
| `TEMPORARY_DIR` | Temporary directory for saving uploaded content from instagram | `tmp/` |
| `VAULT_ADDR`  | The address at which the vault server will be available to the bot | `http://vault-server:8200` |
| `VAULT_APPROLE_ID` | [Approle id created during vault setup](https://developer.hashicorp.com/vault/docs/auth/approle) | `None` |
| `VAULT_APPROLE_SECRET_ID`  | [Approle secret id created during vault setup](https://developer.hashicorp.com/vault/docs/auth/approle) | `None` |
| `INSTAGRAM_SESSION` | The path for storing the file with the instagram session | `.session` |
| `INSTAGRAM_USERAGENT`  | [User Agent to use for HTTP requests. Per default, Instaloader pretends being Chrome/92 on Linux](https://instaloader.github.io/cli-options.html#cmdoption-user-agent) | `None` |


## <img src="https://github.com/obervinov/_templates/blob/main/icons/config.png" width="25" title="config"> Prepare
### Target storage of the content
#### <img src="https://github.com/obervinov/_templates/blob/main/icons/dropbox.ico" width="18" title="dropbox"> If dropbox is going to be used as the target storage, you need to:
- [Create a dropbox account](https://www.dropbox.com/register)
- Generate an application token according to the instructions [here](https://dropbox.tech/developers/generate-an-access-token-for-your-own-account) and [here](https://developers.dropbox.com/ru-ru/oauth-guide)

[More documentation](https://www.dropbox.com/developers/documentation/python#overview)

#### <img src="https://github.com/obervinov/_templates/blob/main/icons/file.png" width="18" title="file"> If the local file system will be used as the target storage:
- Set to environment variable `TEMPORARY_DIR` the desired local path for saving content (for example: `/opt/backup/instagram`)

Such a strange variable name comes from the logic of the bots with different targets. Variable `TEMPORARY_DIR` is used as an intermediate buffer between the stage of downloading content from Instagram and then uploading it to the _target storage_.

If the target storage is **dropbox**, then files from the _temporary directory_ are simply deleted after uploading to the cloud.

If the target storage is a **local file system**, then any further steps for processing files will be redundant. The process simply downloads the content from Instagram immediately to the _destination directory_ (_temproary directory_), after which nothing happens to the files.

### Vault as a persistent storage of the configuration and history of the bot
 - Starting and basic configuration of **vault**
When using **docker-compose** a file
 ```bash

 ```




## <img src="https://github.com/obervinov/_templates/blob/main/icons/docker.png" width="25" title="docker"> How to run with docker-compose
1. Build and launch docker container with vault-server
```sh
docker-compose up -d vault-server
```

2. Configure the vault-server
```sh
# Go to the interactive shell of the vault container
docker exec -ti vault-server sh

# Init vault server
vault operator init

# Login in vault-server with root token
# ${VAULT_ROOT_TOKEN} - Root token for vault login. Substitute your own value instead of a variable. The root token was received in the output at the previous step
vault login ${VAULT_ROOT_TOKEN} -address=http://0.0.0.0:8200

# Enable secret engine - kv version 2
vault secrets enable -version=2 -path=secretv2 kv

# Enable auth with approle method
vault auth enable approle

### ${BOT_NAME} - your bot's name. Substitute your own value instead of a variable. For example: "pyinstabot-downloader"

# Write policy rules to file in container
tee ${BOT_NAME}-policy.htl <<EOF
path "secretv2/config" {
  capabilities = ["create", "read", "update", "list"]
}
path "secretv2/data/${BOT_NAME}-config/config" {
  capabilities = ["read", "list"]
}
path "secretv2/data/${BOT_NAME}-data/*" {
  capabilities = ["create", "read", "update", "list"]
}
path "secretv2/metadata/${BOT_NAME}-data/*" {
  capabilities = ["read", "list"]
}
path "secretv2/data/${BOT_NAME}-login-events/*" {
  capabilities = ["create", "read", "update"]
}
EOF

# Create policy for approle
vault policy write ${BOT_NAME}-policy ${BOT_NAME}-policy.htl

# Create approle for bot
vault write auth/approle/role/${BOT_NAME}-approle role_name="${BOT_NAME}-approle" policies="${BOT_NAME}-policy" secret_id_num_uses=0 token_num_uses=0 token_type=default token_ttl=720h token_policies="${BOT_NAME}-policy" bind_secret_id=true token_no_default_policy=true

# Create secret-id by approle (the secret-id received after executing the command will be required for the bot to work)
vault write auth/approle/role/${BOT_NAME}-approle/secret-id role_name="${BOT_NAME}-approle" metadata="bot=${BOT_NAME}"

# Read role-id (the role-id received after executing the command will be required for the bot to work)
vault read auth/approle/role/${BOT_NAME}-approle/role-id
```

3. Load the config for the bot (in the interactive shell of the vault container)
```sh
# Upload the bot configuration containing sensitive data to the vault
# ${TELEGRAM_API_TOKEN} - your bot's api token
# ${INSTAGRAM_USER} - username for authorization in the instagram
# ${INSTAGRAM_PASSWORD} - password for authorization in the instagram
# ${YOUR_TELEGRAM_ID} - telegram id of your account for authorization of messages sent by the bot (whitelist)
# ${DROPBOX_API_TOKEN} - token for access to the dropbox api
vault kv put secretv2/${BOT_NAME}-config/config b_token="${TELEGRAM_API_TOKEN}" i_user="${INSTAGRAM_USER}" i_pass="${INSTAGRAM_PASSWORD}" whitelist="${YOUR_TELEGRAM_ID}" d_token="${DROPBOX_API_TOKEN}"
### Exit the container shell ###
```
4. Set environment variables in the host OS (the required values must be obtained at the vault configuration step)
```sh
expot BOT_VAULT_APPROLE_ID="change_me"
expot BOT_VAULT_APPROLE_SECRET_ID="change_me"
```

5. Run bot
```sh
docker-compose up -d ${BOT_NAME}
```

6. View logs
```sh
docker logs -f ${BOT_NAME}
```

## <img src="https://github.com/obervinov/_templates/blob/main/icons/stack2.png" width="25" title="stack2"> How to run a bot locally without a docker
**You need an already running and configured vault to use the approle and kv v2 engine**
1. Install python requirements
```sh
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
```
2. Upload the bot configuration containing sensitive data to the vault
```sh
# ${TELEGRAM_API_TOKEN} - your bot's api token
# ${INSTAGRAM_USER} - username for authorization in the instagram
# ${INSTAGRAM_PASSWORD} - password for authorization in the instagram
# ${YOUR_TELEGRAM_ID} - telegram id of your account for authorization of messages sent by the bot (whitelist)
# ${DROPBOX_API_TOKEN} - token for access to the dropbox api
vault kv put secretv2/${BOT_NAME}-config/config b_token="${TELEGRAM_API_TOKEN}" i_user="${INSTAGRAM_USER}" i_pass="${INSTAGRAM_PASSWORD}" whitelist="${YOUR_TELEGRAM_ID}" d_token="${DROPBOX_API_TOKEN}
```
3. Set environment variables in the host OS (the required values must be obtained at the vault configuration step)
```sh
expot BOT_VAULT_APPROLE_ID="change_me"
expot BOT_VAULT_APPROLE_SECRET_ID="change_me"
```
4. Run bot
```sh
python3 bot.py
```
