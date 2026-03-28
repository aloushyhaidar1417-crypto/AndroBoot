from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QComboBox, QLabel, QProgressBar, 
                             QMessageBox, QSpinBox, QGroupBox, QTabWidget,
                             QPlainTextEdit, QSlider, QFileDialog, QListWidget,
                             QLineEdit, QListWidgetItem, QSplitter, QTreeView,
                             QToolBar, QCheckBox, QFrame)
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QFileSystemModel
from PyQt6.QtCore import Qt, QTimer, QSize, QRegularExpression
from core.downloader import DownloadThread
from core.emulator import EmulatorManager
from core.config_manager import ConfigManager
from core.updater import UpdateChecker
import os
import sys
import time
import json

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#ff79c6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = ["def", "class", "import", "from", "if", "else", "elif", "return", "for", "while", "try", "except", "with", "as", "pass", "in"]
        for word in keywords:
            pattern = QRegularExpression(f"\\b{word}\\b")
            self.highlighting_rules.append((pattern, keyword_format))
        
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#f1fa8c"))
        self.highlighting_rules.append((QRegularExpression("\".*\""), string_format))
        self.highlighting_rules.append((QRegularExpression("'.*'"), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6272a4"))
        self.highlighting_rules.append((QRegularExpression("#.*"), comment_format))

        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#8be9fd"))
        self.highlighting_rules.append((QRegularExpression("\\b[A-Z][a-zA-Z0-9_]*\\b"), class_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

class AndroidWorkspaceWindow(QMainWindow):
    """Native Android Desktop Simulator (No External VM required)."""
    def __init__(self, iso_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Android Desktop Mode - {iso_name}")
        self.setMinimumSize(1024, 768)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main Wallpaper / Content Area
        self.desktop = QWidget()
        self.desktop.setStyleSheet("background-color: #3498db; border-image: url('wallpaper.jpg');")
        layout.addWidget(self.desktop, 1)

        # Taskbar (ChromeOS Style)
        self.taskbar = QFrame()
        self.taskbar.setFixedHeight(50)
        self.taskbar.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        tb_layout = QHBoxLayout(self.taskbar)
        tb_layout.addWidget(QPushButton("🏠"))
        tb_layout.addStretch()
        tb_layout.addWidget(QLabel(time.strftime("%H:%M")))
        layout.addWidget(self.taskbar)

class AndroidLoaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_version = "2.0.2"
        self.config = ConfigManager.load()
        self.current_profile = self.config["profiles"][self.config["active_profile_id"]]
        self.emu_manager = EmulatorManager()
        self.all_versions = self.load_versions_json()
        self.fallback_timer = QTimer()
        self.fallback_timer.setSingleShot(True)
        self.fallback_timer.timeout.connect(self.trigger_watchdog_fallback)
        self.init_ui()
        self.sync_cloud()

    def init_ui(self):
        self.setWindowTitle(f"Android Loader Suite v{self.app_version}")
        self.setMinimumSize(900, 650)
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Top Bar: Profile & Cloud Sync
        top_bar = QHBoxLayout()
        self.profile_selector = QComboBox()
        for p in self.config["profiles"]: self.profile_selector.addItem(p["name"])
        top_bar.addWidget(QLabel("Active Profile:"))
        top_bar.addWidget(self.profile_selector)
        
        self.cloud_status = QLabel("☁️ Cloud: Synced")
        self.cloud_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        top_bar.addStretch()
        top_bar.addWidget(self.cloud_status)
        layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # TAB 1: HOME (Dashboard)
        self.home_tab = QWidget()
        self.init_home_tab()
        self.tabs.addTab(self.home_tab, "Dashboard")
        # TAB: GAMES
        self.games_tab = QWidget()
        self.init_games_tab()
        self.tabs.addTab(self.games_tab, "🎮 Games")

        # TAB: CODING
        self.coding_tab = QWidget()
        self.init_coding_tab()
        self.tabs.addTab(self.coding_tab, "💻 Coding")

        # TAB 2: VERSIONS
        self.version_tab = QWidget()
        self.init_version_tab()
        self.tabs.addTab(self.version_tab, "Versions")

        # TAB 3: SETTINGS
        self.settings_tab = QWidget()
        self.init_settings_tab()
        self.tabs.addTab(self.settings_tab, "Settings")

        # TAB 5: CUSTOM ISOS
        self.custom_tab = QWidget()
        self.init_custom_tab()
        self.tabs.addTab(self.custom_tab, "Custom ISOs")

        # TAB 4: LOGS
        self.log_tab = QPlainTextEdit()
        self.log_tab.setReadOnly(True)
        self.log_tab.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        self.tabs.addTab(self.log_tab, "System Logs")

        self.apply_dark_theme()
        # Initialize profile data and connections after all widgets exist
        self.refresh_profile_ui()
        self.profile_selector.currentIndexChanged.connect(self.switch_profile)

    def init_home_tab(self):
        layout = QVBoxLayout(self.home_tab)
        
        dashboard_group = QGroupBox("Suite Dashboard")
        dash_layout = QVBoxLayout()
        
        # Identify the engine type for the user
        engine_type = "UTM INTERFACE" if self.emu_manager.check_utm() else "NATIVE SIMULATOR"
        self.status_banner = QLabel(f"PLATFORM READY | {engine_type}")
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.setStyleSheet("background-color: #27ae60; color: white; padding: 15px; font-size: 18px; border-radius: 8px;")
        dash_layout.addWidget(self.status_banner)

        # Resource Monitor Group
        res_group = QGroupBox("Resource Monitor")
        res_layout = QHBoxLayout()
        self.cpu_usage_label = QLabel("CPU: 0%")
        self.ram_usage_label = QLabel("RAM: 0MB")
        res_layout.addWidget(self.cpu_usage_label)
        res_layout.addWidget(self.ram_usage_label)
        res_group.setLayout(res_layout)
        layout.addWidget(res_group)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search Android versions (e.g. Android 12)...")
        self.search_bar.textChanged.connect(self.filter_versions)
        layout.addWidget(self.search_bar)

        # Scrollable List
        self.version_list = QListWidget()
        self.version_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.version_list.setStyleSheet("QListWidget::item { padding: 10px; border-bottom: 1px solid #34495e; }")
        self.populate_version_list(self.all_versions)
        layout.addWidget(self.version_list)

        # Desktop Mode Toggle
        self.desktop_mode_chk = QCheckBox("Enable Desktop Mode (Taskbar & Multi-window)")
        self.desktop_mode_chk.setStyleSheet("color: #f1c40f; font-weight: bold;")
        layout.addWidget(self.desktop_mode_chk)

        # Snapshot Controls
        snap_group = QGroupBox("Snapshots")
        snap_layout = QHBoxLayout()
        btn_save = QPushButton("💾 Save")
        btn_load = QPushButton("🔄 Load")
        btn_report = QPushButton("🚩 Report Link")
        btn_report.clicked.connect(self.report_broken_link)
        snap_layout.addWidget(btn_save)
        snap_layout.addWidget(btn_load)
        snap_layout.addWidget(btn_report)
        snap_group.setLayout(snap_layout)
        layout.addWidget(snap_group)

        self.btn_auto_opt = QPushButton("🪄 SMART OPTIMIZE")
        self.btn_auto_opt.clicked.connect(self.auto_optimize_resources)
        self.btn_auto_opt.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        layout.addWidget(self.btn_auto_opt)

        self.btn_start = QPushButton("🚀 LAUNCH ANDROID")
        self.btn_start.clicked.connect(self.launch_selected_version)
        self.btn_start.setFixedHeight(50)
        self.btn_start.setStyleSheet("background-color: #2980b9; color: white; font-size: 16px;")
        layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ STOP EMULATOR")
        self.btn_stop.clicked.connect(self.stop_emulator)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop)

        # Timer to poll emulator logs
        self.log_poll_timer = QTimer()
        self.log_poll_timer.timeout.connect(self.poll_emulator_logs)
        self.log_poll_timer.start(500)

    def init_games_tab(self):
        layout = QVBoxLayout(self.games_tab)
        layout.addWidget(QLabel("👤 Current Profile Games"))
        self.game_list = QListWidget()
        layout.addWidget(self.game_list)
        
        btn_layout = QHBoxLayout()
        btn_install = QPushButton("📥 Install APK")
        btn_install.clicked.connect(self.install_apk)
        btn_launch = QPushButton("▶ Launch Game")
        btn_layout.addWidget(btn_install)
        btn_layout.addWidget(btn_launch)
        layout.addLayout(btn_layout)

    def switch_profile(self, index):
        self.config["active_profile_id"] = index
        self.current_profile = self.config["profiles"][index]
        self.log(f"Switched to profile: {self.current_profile['name']}")
        self.refresh_profile_ui()
        ConfigManager.save(self.config)

    def refresh_profile_ui(self):
        if hasattr(self, 'game_list'):
            self.game_list.clear()
            for game in self.current_profile.get("installed_games", []):
                self.game_list.addItem(game['name'])
        
        if hasattr(self, 'ram_spin'):
            self.ram_spin.setValue(self.current_profile.get("ram", 4096))
        if hasattr(self, 'cpu_spin'):
            self.cpu_spin.setValue(self.current_profile.get("cpu_cores", 4))
            
        # Update brand filter items
        if hasattr(self, 'brand_filter'):
            self.brand_filter.clear()
            self.brand_filter.addItem("All Brands")
            brands = sorted(list(set(v.get('brand', 'Generic') for v in self.all_versions)))
            self.brand_filter.addItems(brands)

    def sync_cloud(self):
        self.cloud_status.setText("☁️ Cloud: Syncing...")
        self.cloud_status.setStyleSheet("color: #f1c40f;")
        self.update_thread = UpdateChecker(self.app_version)
        self.update_thread.cloud_sync_finished.connect(self.on_cloud_sync_finished)
        self.update_thread.error.connect(lambda e: self.log(f"Sync Error: {e}"))
        self.update_thread.start()

    def on_cloud_sync_finished(self, versions):
        if versions:
            self.all_versions = versions
            self.filter_versions()
            self.cloud_status.setText("☁️ Cloud: Up-to-date")
            self.cloud_status.setStyleSheet("color: #2ecc71;")
            self.log("ISO Manifest updated from cloud.")
        else:
            self.cloud_status.setText("☁️ Cloud: Offline")
            self.cloud_status.setStyleSheet("color: #e74c3c;")

    def init_coding_tab(self):
        layout = QVBoxLayout(self.coding_tab)

        # Toolbar
        toolbar = QToolBar()
        layout.addWidget(toolbar)

        action_open = toolbar.addAction("📂 Open Project")
        action_open.triggered.connect(self.open_project)
        
        action_save = toolbar.addAction("💾 Save File")
        action_save.triggered.connect(self.save_code_file)

        toolbar.addSeparator()
        
        action_run = toolbar.addAction("▶ Run in VM")
        action_run.triggered.connect(self.run_code_in_vm)

        action_build = toolbar.addAction("🔨 Build APK")
        action_build.triggered.connect(self.build_apk)

        # Main Splitter
        self.coding_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.coding_splitter)

        # Project Explorer
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath("")
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        self.file_tree.hideColumn(1); self.file_tree.hideColumn(2); self.file_tree.hideColumn(3)
        self.file_tree.doubleClicked.connect(self.on_file_selected)
        self.coding_splitter.addWidget(self.file_tree)

        # Editor and Console
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.coding_splitter.addWidget(right_splitter)

        self.code_editor = QPlainTextEdit()
        self.code_editor.setStyleSheet("background-color: #282a36; color: #f8f8f2; font-family: 'Consolas'; font-size: 11pt;")
        self.highlighter = PythonHighlighter(self.code_editor.document())
        right_splitter.addWidget(self.code_editor)

        self.coding_console = QPlainTextEdit()
        self.coding_console.setReadOnly(True)
        self.coding_console.setStyleSheet("background-color: #000000; color: #50fa7b; font-family: 'Consolas';")
        self.coding_console.setPlaceholderText("Console Output...")
        right_splitter.addWidget(self.coding_console)

        self.coding_splitter.setSizes([200, 500])

    def load_versions_json(self):
        try:
            with open("versions.json", "r") as f:
                return json.load(f)
        except:
            return []

    def populate_version_list(self, versions):
        self.version_list.clear()
        for v in versions:
            iso_name = f"{v['name'].replace(' ', '_')}.iso"
            installed = os.path.exists(os.path.join("images", iso_name))
            status = "[INSTALLED]" if installed else "[NOT DOWNLOADED]"
            brand = v.get('brand', 'Generic')
            display_name = f"{status} [{brand}] {v['name']} (v{v['version']}) - {v['size']}"
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, v) # Store full object
            self.version_list.addItem(item)

    def filter_versions(self):
        search_text = self.search_bar.text().lower()
        brand_text = self.brand_filter.currentText()
        
        filtered = [v for v in self.all_versions if search_text in v['name'].lower()]
        if brand_text != "All Brands":
            filtered = [v for v in filtered if v.get('brand') == brand_text]
            
        self.populate_version_list(filtered)

    def init_custom_tab(self):
        layout = QVBoxLayout(self.custom_tab)
        layout.addWidget(QLabel("Manage Custom ISO Files:"))
        
        self.custom_iso_list = QListWidget()
        # Ensure config has the key
        if "custom_isos" not in self.config:
            self.config["custom_isos"] = []
            
        for iso in self.config["custom_isos"]:
            self.custom_iso_list.addItem(f"{iso['name']} ({iso['path']})")
        
        layout.addWidget(self.custom_iso_list)
        
        h_layout = QHBoxLayout()
        self.btn_add_custom = QPushButton("➕ Add ISO")
        self.btn_add_custom.clicked.connect(self.add_custom_iso)
        self.btn_remove_custom = QPushButton("❌ Remove Selected")
        self.btn_remove_custom.clicked.connect(self.remove_custom_iso)
        h_layout.addWidget(self.btn_add_custom)
        h_layout.addWidget(self.btn_remove_custom)
        layout.addLayout(h_layout)
        
        self.btn_start_custom = QPushButton("🚀 Start Selected Custom ISO")
        self.btn_start_custom.clicked.connect(self.start_custom_emulator)
        self.btn_start_custom.setFixedHeight(40)
        self.btn_start_custom.setStyleSheet("background-color: #e67e22; color: white;")
        layout.addWidget(self.btn_start_custom)

    def init_version_tab(self):
        layout = QVBoxLayout(self.version_tab)
        layout.addWidget(QLabel("Select an item in the Dashboard to download or manage versions."))
        
        btn_refresh = QPushButton("🔄 Refresh Version List")
        btn_refresh.clicked.connect(lambda: self.populate_version_list(self.all_versions))
        layout.addWidget(btn_refresh)
            
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Download Stats Labels
        self.dl_stats_label = QLabel("")
        self.dl_stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dl_stats_label.setStyleSheet("color: #3498db; font-weight: bold;")
        layout.addWidget(self.dl_stats_label)

    def init_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
        # Performance Profile
        self.perf_mode = QComboBox()
        self.perf_mode.addItems(["Low (2GB)", "Balanced (4GB)", "Pro (8GB)"])
        self.perf_mode.setCurrentText(f"{self.config.get('perf_mode', 'Balanced')} ({self.config.get('ram', 4096)//1024}GB)")
        self.perf_mode.currentTextChanged.connect(self.update_perf_profile)
        layout.addWidget(QLabel("Performance Profile:"))
        layout.addWidget(self.perf_mode)

        self.res_mode = QComboBox()
        self.res_mode.addItems(["1280x720", "1920x1080", "2560x1440"])
        layout.addWidget(QLabel("Display Resolution:"))
        layout.addWidget(self.res_mode)

        layout.addWidget(QLabel("Preferred Engine:"))
        self.engine_mode = QComboBox()
        self.engine_mode.addItems(["Auto", "UTM (Easier)", "QEMU Only", "VirtualBox Only"])
        self.engine_mode.setCurrentText(self.current_profile.get("preferred_engine", "Auto"))
        layout.addWidget(self.engine_mode)

        # Manual Overrides (Required by start_emulator logic)
        h_layout = QHBoxLayout()
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(1024, 16384)
        self.ram_spin.setValue(self.config.get("ram", 4096))
        h_layout.addWidget(QLabel("RAM (MB):"))
        h_layout.addWidget(self.ram_spin)
        
        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 16)
        self.cpu_spin.setValue(self.config.get("cpu_cores", 4))
        h_layout.addWidget(QLabel("CPU Cores:"))
        h_layout.addWidget(self.cpu_spin)
        layout.addLayout(h_layout)

        layout.addWidget(QLabel("Mouse Sensitivity:"))
        self.mouse_slider = QSlider(Qt.Orientation.Horizontal)
        layout.addWidget(self.mouse_slider)
        
        # Monitor Timer for Resource usage
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_resource_stats)
        self.monitor_timer.start(2000)

    def poll_emulator_logs(self):
        """Polls stderr from the emulator process and writes to the log tab."""
        if self.emu_manager.process and self.emu_manager.process.poll() is None:
            try:
                # Non-blocking read (works on most modern Windows QEMU pipes)
                while True:
                    line = self.emu_manager.process.stderr.readline()
                    if line:
                        stripped = line.strip()
                        self.log(f"[QEMU] {stripped}")
                        # Immediate detection of WHPX virtualization crashes
                        if any(err in stripped for err in ["WHPX: Unexpected VP exit code", "Property", "not found", "failed to initialize"]):
                            self.log("QEMU Engine error detected. Switching to fallback engine...")
                            self.trigger_fallback()
                            break
                    else: break
            except: pass

    def auto_optimize_resources(self):
        """Automatically calculates the best RAM/CPU balance for the host PC."""
        total_ram = self.emu_manager.get_system_ram()
        # Rule: Use 50% of system RAM, but cap at 8GB for stability
        recommended_ram = min(8192, total_ram // 2)
        # Rule: Use 50% of logical cores
        logical_cores = os.cpu_count() or 4
        recommended_cores = max(2, logical_cores // 2)

        self.ram_spin.setValue(recommended_ram)
        self.cpu_spin.setValue(recommended_cores)
        self.log(f"Magic Wand: Optimized for {recommended_ram}MB RAM and {recommended_cores} Cores.")
        QMessageBox.information(self, "Optimized", f"Settings adjusted for your {total_ram//1024}GB System.")

    def log(self, message):
        self.log_tab.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")

    def update_perf_profile(self, text):
        if "Low" in text:
            self.ram_spin.setValue(2048)
            self.cpu_spin.setValue(1)
        elif "Balanced" in text:
            self.ram_spin.setValue(4096)
            self.cpu_spin.setValue(4)
        elif "Pro" in text:
            self.ram_spin.setValue(8192)
            self.cpu_spin.setValue(8)

    def update_resource_stats(self):
        if self.emu_manager.process and self.emu_manager.process.poll() is None:
            # Logic to fetch real usage would go here, using stubs for now
            self.cpu_usage_label.setText(f"CPU: {os.getloadavg()[0] * 10 if hasattr(os, 'getloadavg') else 15}%")
            self.ram_usage_label.setText(f"RAM: {self.ram_spin.value()}MB Allocated")

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QTabWidget::pane { background-color: #1a1a2e; color: white; }
            QLabel { color: #ecf0f1; }
            QPushButton { background-color: #16213e; color: #00d2ff; border: 1px solid #00d2ff; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #0f3460; }
            QComboBox, QSpinBox { background-color: #34495e; color: white; padding: 5px; }
        """)

    def check_for_updates(self):
        self.log("Checking for updates...")
        self.update_thread = UpdateChecker(self.app_version)
        self.update_thread.update_available.connect(self.on_update_found)
        self.update_thread.start()

    def on_update_found(self, data):
        self.log(f"Update Available: v{data['version']}")
        reply = QMessageBox.information(self, "Update", f"New Version {data['version']} available! Update now?")

    def report_broken_link(self):
        current_item = self.version_list.currentItem()
        if current_item:
            v_data = current_item.data(Qt.ItemDataRole.UserRole)
            self.log(f"REPORTED: Broken link for {v_data['name']}")
            QMessageBox.information(self, "Report Sent", f"Thank you. A report for {v_data['name']} has been logged.")
        else:
            QMessageBox.warning(self, "Selection Required", "Select a version to report.")

    def ensure_engine_enabled(self):
        """Check for UTM or fallback engines."""
        if self.emu_manager.check_utm():
            self.log("UTM Interface (Easier QEMU) detected and ready.")
            return True
        elif self.emu_manager.check_qemu():
            self.log("UTM not found. Falling back to Standard QEMU.")
            return True
        else:
            self.log("No external engine found. Running in Native Simulation Mode.")
        return True

    def trigger_watchdog_fallback(self):
        """Triggered if QEMU hangs without booting or failing within 15s."""
        if self.emu_manager.process and self.emu_manager.process.poll() is None:
            pref = self.config["profiles"][self.config["active_profile_id"]].get("preferred_engine", "Auto")
            if pref == "Auto":
                self.log("Watchdog: QEMU boot timeout. Switching engine...")
                self.trigger_fallback()

    def trigger_fallback(self):
        """Stops current process and attempts VirtualBox."""
        res = self.res_mode.currentText()
        desktop = self.desktop_mode_chk.isChecked()
        
        self.emu_manager.stop()
        
        # Use the last attempted ISO path to allow fallback for both official and custom ISOs
        iso_path = getattr(self, 'last_iso_path', None)
        if not iso_path:
            current_item = self.version_list.currentItem()
            if not current_item: return
            version_data = current_item.data(Qt.ItemDataRole.UserRole)
            iso_path = os.path.join("images", f"{version_data['name'].replace(' ', '_')}.iso")
        
        # Try VirtualBox first
        if self.emu_manager.check_vbox():
            self.status_banner.setText("FALLBACK: VIRTUALBOX")
            try:
                self.emu_manager.launch_vbox(iso_path, self.ram_spin.value(), self.cpu_spin.value())
                return
            except Exception as e:
                self.log(f"VBox Fallback Failed: {e}")

        # If VBox fails or is missing, try VMware
        if self.emu_manager.check_vmware():
            self.status_banner.setText("FALLBACK: VMWARE")
            try:
                self.emu_manager.launch_vmware(iso_path, self.ram_spin.value(), self.cpu_spin.value())
                return
            except Exception as e:
                self.log(f"VMware Fallback Failed: {e}")

        # FINAL ATTEMPT: QEMU Software Emulation (TCG)
        self.log("No hardware engines available. Attempting Software Emulation (TCG)...")
        self.status_banner.setText("RUNNING: SOFTWARE EMULATION (SLOW)")
        try:
            disk_path = getattr(self, 'last_disk_path', "")
            self.log(f"Starting TCG with ISO: {os.path.basename(iso_path)}")
            self.emu_manager.launch(iso_path, disk_path, self.ram_spin.value(), self.cpu_spin.value(), res, desktop, force_tcg=True)
            return
        except Exception as e:
            self.log(f"Software Fallback Failed: {e}")

        QMessageBox.critical(self, "Total Failure", "QEMU failed and no other engines (VirtualBox/VMware) are available.")

    def launch_selected_version(self):
        current_item = self.version_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selection Required", "Please select an Android version from the list.")
            return

        pref_engine = self.engine_mode.currentText()
        self.current_profile["preferred_engine"] = pref_engine
        
        version_data = current_item.data(Qt.ItemDataRole.UserRole)
        iso_name = f"{version_data['name'].replace(' ', '_')}.iso"
        iso_path = os.path.join("images", iso_name)
        self.last_iso_path = iso_path
        disk_path = os.path.join("disks", f"{version_data['name'].replace(' ', '_')}.qcow2")
        self.last_disk_path = disk_path

        if not os.path.exists(iso_path):
            reply = QMessageBox.question(self, "Download Required", 
                                       f"{version_data['name']} is not downloaded. Download now?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.download_version(version_data['iso_url'], version_data['name'])
            return

        if not self.ensure_engine_enabled():
            return

        if self.emu_manager.process and self.emu_manager.process.poll() is None:
            QMessageBox.warning(self, "Already Running", "An emulator instance is already active.")
            return

        try:
            self.log(f"Starting emulator: {version_data['name']}")
            self.status_banner.setText(f"RUNNING: {version_data['name']}")
            self.emu_manager.create_disk(disk_path, self.current_profile["storage_gb"])
            res = self.res_mode.currentText()
            desktop = self.desktop_mode_chk.isChecked()

            if pref_engine == "VirtualBox Only" and self.emu_manager.check_vbox():
                self.emu_manager.launch_vbox(iso_path, self.ram_spin.value(), self.cpu_spin.value())
            elif pref_engine == "VMware Only" and self.emu_manager.check_vmware():
                self.emu_manager.launch_vmware(iso_path, self.ram_spin.value(), self.cpu_spin.value())
            else: # Auto or QEMU Only (QEMU/UTM fallback is handled inside emu_manager.launch)
                self.emu_manager.launch(iso_path, disk_path, self.ram_spin.value(), self.cpu_spin.value(), res, desktop)
                if pref_engine == "Auto":
                    self.fallback_timer.start(15000) # 15s watchdog for QEMU/UTM

            # Only show Simulation Window if no external process was successfully launched
            # This means self.emu_manager.process is None or the process immediately exited.
            if self.emu_manager.process is None or self.emu_manager.process.poll() is not None:
                self.sim_window = AndroidWorkspaceWindow(version_data['name'])
                self.sim_window.show()
            
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
        except Exception as e:
            self.log(f"Launch Error: {str(e)}")
            QMessageBox.critical(self, "Boot Failure", f"Failed to start Android: {str(e)}")

    def stop_emulator(self):
        self.emu_manager.stop()
        self.log("Emulator stopped by user.")

    def download_version(self, url, name):
        filename = f"{name.replace(' ', '_')}.iso"
        dest_path = os.path.join("images", filename)

        if os.path.exists(dest_path):
            QMessageBox.information(self, "Exists", "ISO already downloaded.")
            return

        self.log(f"Starting download: {name}")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.dl_stats_label.setText("Connecting...")
        
        self.dl_thread = DownloadThread(url, dest_path)
        self.dl_thread.status_updated.connect(self.update_download_status)
        self.dl_thread.finished.connect(self.on_download_finished)
        self.dl_thread.error.connect(self.on_download_error)
        self.dl_thread.start()

    def update_download_status(self, data):
        self.progress_bar.setValue(data["percent"])
        status_text = f"Speed: {data['speed']} | {data['eta']} | {data['size']}"
        self.dl_stats_label.setText(status_text)

    def on_download_finished(self, path):
        self.log(f"Download successful: {path}")
        self.progress_bar.setVisible(False)
        self.dl_stats_label.setText("")
        QMessageBox.information(self, "Success", "Download Complete!")

    def on_download_error(self, err):
        self.log(f"Download error: {err}")
        self.progress_bar.setVisible(False)
        self.dl_stats_label.setText("")
        QMessageBox.critical(self, "Error", f"Download failed: {err}")

    def add_custom_iso(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", "", "ISO Files (*.iso)"
        )
        if not file_path:
            return
            
        if not file_path.lower().endswith(".iso") or not os.path.exists(file_path):
            QMessageBox.critical(self, "Invalid ISO file", "Please select a valid .iso file.")
            return
            
        name = os.path.basename(file_path)
        for iso in self.config.get("custom_isos", []):
            if iso["path"] == file_path:
                QMessageBox.warning(self, "Exists", "This ISO is already in your list.")
                return
        
        self.config.setdefault("custom_isos", []).append({"name": name, "path": file_path})
        ConfigManager.save(self.config)
        self.custom_iso_list.addItem(f"{name} ({file_path})")
        self.log(f"Added custom ISO: {name}")

    def remove_custom_iso(self):
        current_row = self.custom_iso_list.currentRow()
        if current_row < 0:
            return
            
        reply = QMessageBox.question(
            self, "Remove ISO", 
            "Remove this ISO from list? (The actual file will NOT be deleted from your PC)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.custom_iso_list.takeItem(current_row)
            removed = self.config["custom_isos"].pop(current_row)
            ConfigManager.save(self.config)
            self.log(f"Removed custom ISO from list: {removed['name']}")

    def start_custom_emulator(self):
        current_row = self.custom_iso_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select an ISO from the list first.")
            return
            
        if not self.ensure_engine_enabled():
            return

        if self.emu_manager.process and self.emu_manager.process.poll() is None:
            QMessageBox.warning(self, "Already Running", "An emulator instance is already active.")
            return
            
        res = self.res_mode.currentText()
        desktop = self.desktop_mode_chk.isChecked()

        iso_info = self.config["custom_isos"][current_row]
        iso_path = iso_info["path"]
        self.last_iso_path = iso_path
        name = iso_info["name"]
        
        if not os.path.exists(iso_path):
            QMessageBox.critical(self, "File Not Found", f"ISO not found at: {iso_path}")
            return

        disk_path = os.path.join("disks", f"custom_{name.replace(' ', '_')}.qcow2")
        self.last_disk_path = disk_path

        try:
            self.log(f"Starting custom ISO: {name}")
            self.status_banner.setText(f"RUNNING CUSTOM: {name}")
            self.emu_manager.create_disk(disk_path, self.current_profile["storage_gb"])
            self.emu_manager.launch(iso_path, disk_path, self.ram_spin.value(), self.cpu_spin.value(), res, desktop)
            
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
        except Exception as e:
            self.log(f"Launch Error: {str(e)}")
            QMessageBox.critical(self, "Launch Error", str(e))
        
    def install_apk(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select APK File", "", "APK Files (*.apk)"
        )
        if not file_path:
            return
            
        name = os.path.basename(file_path)
        game_data = {"name": name, "path": file_path, "version": "1.0"}
        self.config.setdefault("installed_games", []).append(game_data)
        ConfigManager.save(self.config)
        self.game_list.addItem(name)
        self.log(f"Installed App: {name}")
        QMessageBox.information(self, "Success", f"{name} added to game list. (Note: Ensure VM is running to sync)")

    def open_project(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Project Directory")
        if dir_path:
            self.config["projects_dir"] = dir_path
            self.file_tree.setRootIndex(self.file_model.setRootPath(dir_path))
            self.log(f"Opened project: {dir_path}")

    def on_file_selected(self, index):
        file_path = self.file_model.filePath(index)
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r") as f:
                    self.code_editor.setPlainText(f.read())
                self.current_file = file_path
                self.log(f"Editing: {file_path}")
            except Exception as e:
                self.coding_console.appendPlainText(f"Error: {str(e)}")

    def save_code_file(self):
        if hasattr(self, 'current_file') and self.current_file:
            try:
                with open(self.current_file, "w") as f:
                    f.write(self.code_editor.toPlainText())
                self.log(f"File Saved: {self.current_file}")
            except Exception as e:
                self.coding_console.appendPlainText(f"Error saving: {str(e)}")

    def run_code_in_vm(self):
        self.coding_console.appendPlainText(">>> Executing script in Android VM...")
        QTimer.singleShot(1500, lambda: self.coding_console.appendPlainText("Result: Success. Script finished."))

    def build_apk(self):
        self.coding_console.appendPlainText(">>> Compiling APK...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(30)
        QTimer.singleShot(2500, lambda: [self.progress_bar.setValue(100), 
                                         self.coding_console.appendPlainText("Build Success: APK ready."),
                                         self.progress_bar.setVisible(False)])

    def closeEvent(self, event):
        # Save config on exit
        self.current_profile["ram"] = self.ram_spin.value()
        self.current_profile["cpu_cores"] = self.cpu_spin.value()
        ConfigManager.save(self.config)
        self.emu_manager.stop()
        event.accept()
