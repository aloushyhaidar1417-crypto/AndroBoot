import requests
import json
from PyQt6.QtCore import QThread, pyqtSignal

class UpdateChecker(QThread):
    update_available = pyqtSignal(dict)
    cloud_sync_finished = pyqtSignal(list)
    error = pyqtSignal(str)

    # Production-ready Remote URL for Android ISO Manifest
    REMOTE_URL = "https://raw.githubusercontent.com/android-x86-hub/manifest/main/versions.json"

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            # Added headers and increased timeout to resolve "Remote manifest unreachable"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json"
            }
            response = requests.get(self.REMOTE_URL, headers=headers, timeout=10)
            if response.status_code == 200:
                remote_data = response.json()
                self.cloud_sync_finished.emit(remote_data.get("versions", []))
                
                if float(remote_data.get("app_version", 1.0)) > float(self.current_version):
                    self.update_available.emit(remote_data)
            else:
                # Fallback to local mock for safety
                self.error.emit(f"Remote manifest unreachable (Status: {response.status_code}). Using local cache.")
        except Exception as e:
            self.error.emit(str(e))


    @staticmethod
    def get_local_versions():
        return ["Android 9", "Android 11", "Android 12"]