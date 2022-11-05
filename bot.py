######### THIS MAIN FUNCTION FROM TELEGRAM BOT AND ENTRYPOINT FROM DOCKER #########
import os
from logger import log, logging
from vault import VaultClient
from users import UsersAuth
from telegram import TelegramBot
from src.instagram import InstagramDownloader
from src.dropbox import DropboxDownloader

bot_name = os.environ.get('BOT_NAME', 'pyinstabot-downloader')
vault_mount_point = os.environ.get('BOT_VAULT_MOUNT_PATH', 'secretv2')
vault_addr = os.environ.get('BOT_VAULT_ADDR', 'http://vault-server:8200')
vault_approle_id = os.environ.get('BOT_VAULT_APPROLE_ID', 'not set')
vault_approle_secret_id = os.environ.get('BOT_VAULT_APPROLE_SECRET_ID', 'not set')
instagram_session_file = os.environ.get('BOT_INSTAGRAM_SESSION_FILE', 'instaloader/.instaloader.session')
ratelimit_timeout = int(os.environ.get('BOT_INSTA_RATE_LIMIT_TIMEOUT', 15))
ratelimit_max_timeout = int(os.environ.get('BOT_INSTA_RATE_LIMIT_MAX_TIMEOUT', 360))
### MODULES AND VARS###


### Vault class ###
Vault = VaultClient(vault_addr, vault_approle_id, vault_approle_secret_id, vault_mount_point)
### Secret data ###
instagram_user = Vault.vault_read_secrets(f"{bot_name}-config/config", "i_user")
instagram_pass = Vault.vault_read_secrets(f"{bot_name}-config/config", "i_pass")
dropbox_token = Vault.vault_read_secrets(f"{bot_name}-config/config", "d_token")
### Secret data ###
### Vault class ###

### Telegram class ###
Telegram = TelegramBot(bot_name, Vault)
telegram_bot = Telegram.telegram_bot
### Telegram class ###

### UsersAuth class ###
Users_auth = UsersAuth(Vault, bot_name)
### UsersAuth class ###

### Dropbox class ###
Dropbox = DropboxDownloader(dropbox_token, 8, 4, 120)
### Dropbox class ###

### InstagramDownloader class ###
Instagram = InstagramDownloader(Vault, instagram_user, instagram_pass, instagram_session_file, bot_name, Dropbox, telegram_bot)
### InstagramDownloader class ###

### Logger initialization ###
logging.getLogger('bot.bot').setLevel(logging.INFO)
### Logger initialization ###

### Printing environment variables ###
log.info(f"Variables:\n+BOT_NAME: {bot_name}\n+BOT_HOME_PATH: {os.getcwd()}\n+BOT_VAULT_MOUNT_PATH: {vault_mount_point}\n+BOT_VAULT_ADDR: {vault_addr}\n+BOT_INSTAGRAM_SESSION_FILE: {instagram_session_file}\n+BOT_INSTA_RATE_LIMIT_TIMEOUT: {ratelimit_timeout}\n+BOT_INSTA_RATE_LIMIT_MAX_TIMEOUT: {ratelimit_max_timeout}")
### Printing environment variables ###


###### DECORATORS #######
### Start command ###
@telegram_bot.message_handler(commands=['start'])
def start_message(message):
    
    access_status = access_status = Users_auth.check_permission(message.chat.id)

    if access_status == "success":
      log.info(f"sending startup message in chat {message.chat.id}")
      telegram_bot.send_message(message.chat.id, f"Hi, <b>{message.chat.username}</b>! \u270B\nAccess for your account - allowed \U0001F513\n\U0001F4F1Bot functions:\n  \U0001F4CC Upload post content by instagram link to dropbox cloud.\n  \U0001F4CC Uploading all posts content by instagram profile-link to dropbox cloud.\n <i>Just send link </i>\u270C")
    
    else:
      log.error(f"403: access denied for chat_id: {message.from_user.id} username: {message.from_user.username} first_name: {message.from_user.first_name} last_name: {message.from_user.last_name}")



### Get all posts in instagram account regex ###
@telegram_bot.message_handler(regexp="^https://(www\.)?instagram.com/(?!p/)(?!reel/).*$")
def profile_get_all_posts(message):

    access_status = access_status = Users_auth.check_permission(message.chat.id)

    if access_status == "success":
      profile_username = str(message.text).split("/")[3].split("?")[0]
      log.info(f"Decorator.profile_get_all_posts() --> call Instagram.download_all_posts()")
      Instagram.download_all_posts(profile_username, ratelimit_timeout, ratelimit_max_timeout, message.chat.id)

    else:
      log.error(f"403: access denied for chat_id: {message.from_user.id} username: {message.from_user.username} first_name: {message.from_user.first_name} last_name: {message.from_user.last_name}")



### Download post per instagram-link by regex input text ###
@telegram_bot.message_handler(regexp="^https://www.instagram.com/(p|reel)/.*")
def profile_get_link_post(message):

    access_status = access_status = Users_auth.check_permission(message.chat.id)

    if access_status == "success":
      ### Get shortcode value 
      shortcode = str(message.text).split("/")[4]
      log.info(f"Decorator.profile_get_link_post() --> call Instagram.download_post()")
      response = Instagram.download_post(shortcode)
      telegram_bot.send_message(message.chat.id, response)

    else:
      log.error(f"403: access denied for chat_id: {message.from_user.id} username: {message.from_user.username} first_name: {message.from_user.first_name} last_name: {message.from_user.last_name}")



###### START TELEGRAM BOT ######
def main():
    while True:
      try:        
        log.info("starting telegram bot.polling process")
        telegram_bot.polling()
      except Exception as e:
        log.error(f"telegram bot.polling process exception: {e}")

if __name__ == "__main__":
    main()
###### START TELEGRAM BOT ######
