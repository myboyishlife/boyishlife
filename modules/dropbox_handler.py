import dropbox
import os
import random
import logging

class DropboxHandler:
    def __init__(self, config):
        self.logger = logging.getLogger(__name__)
        self.client = dropbox.Dropbox(
            app_key=os.getenv("DROPBOX_APP_KEY"),
            app_secret=os.getenv("DROPBOX_APP_SECRET"),
            oauth2_refresh_token=os.getenv("DROPBOX_REFRESH_TOKEN")
        )
        self.conf = config

    def get_file(self, folder_type):
        """
        folder_type: 'ig', 'general', or 'image'
        """
        path_map = {
            'ig': self.conf['folder_video_ig'],
            'general': self.conf['folder_video_general'],
            'image': self.conf['folder_images']
        }
        path = path_map.get(folder_type)
        if not path: return None

        files = self._list_files(path)
        return random.choice(files) if files else None

    def _list_files(self, path):
        try:
            res = self.client.files_list_folder(path)
            return [entry for entry in res.entries if isinstance(entry, dropbox.files.FileMetadata)]
        except Exception as e:
            self.logger.error(f"Dropbox Error listing {path}: {e}")
            return []

    def download_file(self, file_metadata):
        local_path = f"temp_{file_metadata.name}"
        self.client.files_download_to_file(local_path, file_metadata.path_lower)
        return local_path

    def get_temp_link(self, file_metadata):
        return self.client.files_get_temporary_link(file_metadata.path_lower).link

    def delete_file(self, file_metadata):
        try:
            self.client.files_delete_v2(file_metadata.path_lower)
            self.logger.info(f"🗑️ Deleted {file_metadata.name} from Dropbox")
        except Exception as e:
            self.logger.error(f"Failed to delete {file_metadata.name}: {e}")