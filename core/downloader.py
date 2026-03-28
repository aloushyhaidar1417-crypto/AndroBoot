import requests
import os
import time
from PyQt6.QtCore import QThread, pyqtSignal

class DownloadThread(QThread):
    progress = pyqtSignal(int)
    status_updated = pyqtSignal(dict)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, dest_path):
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        retries = 3
        for attempt in range(retries):
            try:
                start_time = time.time()
                last_update_time = start_time
                # allow_redirects=True is critical for SourceForge and other mirrors
                response = requests.get(self.url, stream=True, timeout=20, allow_redirects=True)
                
                # Validate Content-Type to prevent saving HTML error pages as ISOs
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    raise Exception("Invalid download: Server returned HTML instead of an ISO image.")
                
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)

                with open(self.dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 64): # 64KB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            current_time = time.time()
                            # Update UI every 0.5 seconds to ensure smoothness
                            if current_time - last_update_time >= 0.5:
                                elapsed = current_time - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                percent = int((downloaded / total_size) * 100) if total_size > 0 else 0
                                
                                remaining_bytes = total_size - downloaded
                                eta_seconds = remaining_bytes / speed if speed > 0 else 0
                                
                                self.status_updated.emit({
                                    "percent": percent,
                                    "speed": f"{speed / (1024*1024):.2f} MB/s",
                                    "eta": self.format_eta(eta_seconds),
                                    "size": f"{downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB"
                                })
                                last_update_time = current_time
                
                self.finished.emit(self.dest_path)
                return
            except Exception as e:
                if attempt == retries - 1:
                    self.error.emit(str(e))
                else:
                    time.sleep(2) # Wait before retry
                    continue

    def format_eta(self, seconds):
        if seconds <= 0: return "calculating..."
        if seconds < 60:
            return f"{int(seconds)}s left"
        minutes = int(seconds // 60)
        rem_seconds = int(seconds % 60)
        return f"{minutes}m {rem_seconds}s left"
