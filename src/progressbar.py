######### THIS FILE FROM DRAW PORGRESSBAR RESPONSE #########
### MODULES AND VARS###
import math
import datetime
##################
### MODULES AND VARS###


class ProgressBar:


    def __init__(self, Vault = None, bot_name: str = None, username: str = None) -> None:
        self.Vault = Vault
        self.bot_name = bot_name
        self.username = username
        self.posts_already_downloaded = 0
        self.success_count = 0
        self.faild_count = 0
        self.shortcodes_stat = list()
        


    def get(self, posts_count: int = 0, state: str = 'in_progress'):
        
        vault_path = f"{self.bot_name}-data/{self.username}"
        shortcodes_stats = self.Vault.vault_read_secrets(vault_path)

        for key, value in shortcodes_stats.items():

            if value == 'success':
                self.success_count = self.success_count + 1
            else:
                self.faild_count = self.faild_count + 1
        
        self.posts_already_downloaded = int(self.success_count) + int(self.faild_count)
        procentage = math.ceil((self.posts_already_downloaded / posts_count) * 100)

        # generating a string for response and logging
        progressbar_dowloaded_posts = ("\r[" + "\u25FE" * int(procentage) + "\u25AB" * int((100 - procentage)) + "]" +  str(procentage) + "%")

        if state != "finally":
            response_stats = f"\u23F3 Posts from account <b>{self.username}</b> already downloaded: <b>{self.posts_already_downloaded}</b> of <b>{posts_count}</b>\nSuccess: <i>{self.success_count}</i> / faild: <i>{self.faild_count}</i>\n{progressbar_dowloaded_posts}\n"
            response_ratelimit = f"\u23F0 Ratelimit pause applied in {datetime.datetime.now().strftime('%H:%M:%S')}"
            response = f"{response_stats}{response_ratelimit}"
        else:
            response = f"\u2615 <b>{self.posts_already_downloaded}</b> of <b>{posts_count}</b> posts from account <b>{self.username}</b> has been downloaded\nsuccess: <b>{self.success_count}</b>\nfaild: <b>{self.faild_count}</b>\n{progressbar_dowloaded_posts}"
            
        return response 
