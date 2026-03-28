import sys
import os
# Ensure the project root is in the system path for correct module importing
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Ensure the working directory is always the project root
os.chdir(project_root)

from PyQt6.QtWidgets import QApplication
from ui.main_window import AndroidLoaderApp

def setup_folders():
    """Ensure necessary directories exist."""
    folders = ['images', 'disks', 'core', 'ui', 'snapshots', 'projects', 'core/engine']
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
        # Ensure code directories are treated as Python packages
        if folder in ['core', 'ui']:
            init_file = os.path.join(folder, '__init__.py')
            if not os.path.exists(init_file):
                with open(init_file, 'w') as f:
                    pass

if __name__ == "__main__":
    setup_folders()
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Consistent look across platforms
    
    window = AndroidLoaderApp()
    window.show()
    
    sys.exit(app.exec())
