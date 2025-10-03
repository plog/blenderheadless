import os
import io
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

class GDriveManager:
    def __init__(self):
        SCOPES = ['https://www.googleapis.com/auth/drive']        
        
        # Debug environment variables
        env_vars = {
            "GOOGLE_PROJECT_ID": os.getenv("GOOGLE_PROJECT_ID"),
            "GOOGLE_PRIVATE_KEY_ID": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "GOOGLE_PRIVATE_KEY": os.getenv("GOOGLE_PRIVATE_KEY"),
            "GOOGLE_CLIENT_EMAIL": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID")
        }
        
        print("=== GDrive Environment Variables Debug ===")
        for key, value in env_vars.items():
            if value is None:
                print(f"❌ {key}: NOT SET")
            elif key == "GOOGLE_PRIVATE_KEY":
                print(f"✅ {key}: SET (length: {len(value)}, starts with: {value[:30]}...)")
                if not value.startswith('-----BEGIN PRIVATE KEY-----'):
                    print(f"⚠️  {key}: Does not start with '-----BEGIN PRIVATE KEY-----'")
                if '\\n' in value:
                    print(f"⚠️  {key}: Contains escaped newlines (\\n)")
            else:
                print(f"✅ {key}: {value}")
        print("=" * 45)
        
        # Check for missing variables
        missing = [k for k, v in env_vars.items() if v is None]
        if missing:
            raise ValueError(f"Missing environment variables: {missing}")
        
        # Process private key
        private_key = (env_vars["GOOGLE_PRIVATE_KEY"] or "").replace('\\n', '\n')
        if env_vars["GOOGLE_PRIVATE_KEY"] and '\\n' in env_vars["GOOGLE_PRIVATE_KEY"]:
            print("🔧 Converted escaped newlines in private key")
        
        # Use environment variables
        creds_info = {
            "type": "service_account",
            "project_id": env_vars["GOOGLE_PROJECT_ID"],
            "private_key_id": env_vars["GOOGLE_PRIVATE_KEY_ID"],
            "private_key": private_key,
            "client_email": env_vars["GOOGLE_CLIENT_EMAIL"],
            "client_id": env_vars["GOOGLE_CLIENT_ID"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{env_vars['GOOGLE_CLIENT_EMAIL']}"
        }
        
        try:
            self.creds = service_account.Credentials.from_service_account_info(
                creds_info, scopes=SCOPES
            )
            print("✅ Google Drive credentials created successfully")
        except Exception as e:
            print(f"❌ Failed to create credentials: {str(e)}")
            print(f"Private key first 100 chars: {private_key[:100]}...")
            raise
        
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
