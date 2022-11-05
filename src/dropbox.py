######### THIS FILE FROM DROPBOX API COMMAND #########
### MODULES AND VARS###
import os
import dropbox
from logger import log
### MODULES AND VARS###


class DropboxDownloader:


    def __init__(self, dropbox_token: str = None, max_connections: int = 3, max_retries_on_error: int = 3, timeout: int = 60) -> None:
      self.homepath = os.getcwd()
      
      try:
        dropbox_session = dropbox.create_session(max_connections=max_connections, proxies=None)
        self.dropbox_object = dropbox.Dropbox(dropbox_token, max_retries_on_error=max_retries_on_error, max_retries_on_rate_limit=None, user_agent=None, session=dropbox_session, headers=None, timeout=timeout)
    
      except Exception as ex:
        log.error(f"[class.{__class__.__name__}] creating dropbox session faild: {ex}")



    def upload_file(self, upload_dir_name: str = None , dropbox_dir_name: str = None):
      
      files = []
      local_path_profile_content = f"{self.homepath}/{upload_dir_name}"
      log.info(f"[class.{__class__.__name__}] starting upload files from {upload_dir_name}")
        
      for r, d, f in os.walk(local_path_profile_content):
        for file in f:
          files.append(os.path.join(r, file))

        for f in files:
          filename = f.split("/")
          len_filename = len(filename)
          dropbox_filename = "/" + dropbox_dir_name + "/" + filename[len_filename-1]

          if ".txt" in filename[len_filename-1]:
            os.remove(f)

          else:
            with open(f, 'rb') as file_transfer:
              try:
                upload_file = self.dropbox_object.files_upload(file_transfer.read(), dropbox_filename, autorename=True)
                log.info(f"[class.{__class__.__name__}] file {upload_file.name} has been uploaded")
                # extract metainfo of object
                id = upload_file.id
                size = upload_file.size

              except Exception as ex:
                log.error(f"[class.{__class__.__name__}] uploading picture to dropbox api faild: {ex}")
                break
            
            file_transfer.close()
            os.remove(f)
            status = "success"
            response = f"{id} successful transfering {size} bytes"

        if len(os.listdir(local_path_profile_content) ) == 0:
            os.rmdir(local_path_profile_content)
            
        return status, response