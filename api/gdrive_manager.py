import os
import io
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

class GDriveManager:
    def __init__(self):
        SCOPES = ['https://www.googleapis.com/auth/drive']        
        # Use environment variables
        creds_info = {
            "type": "service_account",
            "project_id":     os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key":    (os.getenv("GOOGLE_PRIVATE_KEY") or "").replace('\\n', '\n'),
            "client_email":   os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id":      os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL')}"
        }
        self.creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
        
        self.service = build('drive', 'v3', credentials=self.creds)

    def list_files(self, query="trashed=false", page_size=20):
        """List files in Google Drive matching the query and download them in background."""
        results = self.service.files().list(
            q=query,
            pageSize=page_size,
            fields="files(id, name, mimeType, size, modifiedTime)"
        ).execute()
        files = results.get('files', [])

        # Download all files in background
        import threading
        def download_all():
            for f in files:
                try:
                    self.download_file(f['id'], f['name'])
                except Exception as e:
                    # Optionally log or print error
                    pass

        threading.Thread(target=download_all, daemon=True).start()
        return files

    def download_file(self, file_id, filename=None, dest_dir="/workspace/uploads"):
        """Download file by file_id to dest_dir, overwriting if exists."""
        file = self.service.files().get(fileId=file_id).execute()
        if not filename:
            filename = file['name']
        os.makedirs(dest_dir, exist_ok=True)
        dest_path  = os.path.join(dest_dir, filename)
        request    = self.service.files().get_media(fileId=file_id)
        fh         = io.FileIO(dest_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done       = False
        while not done:
            status, done = downloader.next_chunk()
        fh.close()
        return dest_path

# Example usage:
# gdm = GDriveManager()
# files = gdm.list_files()
# for f in files:
#     print(f"{f['id']} {f['name']}")
# gdm.download_file(file_id="your_file_id_here")
