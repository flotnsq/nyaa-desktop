import sys
import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
                               QLabel, QRadioButton, QButtonGroup, QSpinBox, QComboBox,
                               QLineEdit, QPushButton, QScrollArea, QFrame, QMessageBox)
from PySide6.QtCore import Qt, Signal, QObject, QEvent, QByteArray
from PySide6.QtGui import QKeySequence # Keep if needed for specific settings actions
import qtawesome as qta

# Assuming format_size might be needed if we display size-related settings?
# from core.scraper import format_size # Import if needed

class SettingsWidget(QWidget):
    # Signals to notify MainWindow about changes that affect it directly
    settings_changed = Signal(dict) # General signal for persisting changes
    proxy_config_changed = Signal(dict) # Specific signal for proxy change

    # Signals to request actions from MainWindow
    request_clear_history = Signal()
    request_select_download_dir = Signal()
    request_reset_settings = Signal()

    # Constants (can be adjusted or passed in)
    DEFAULT_SCRAPER_DELAY = 10
    DEFAULT_NETWORK_TIMEOUT = 30
    DEFAULT_MAX_HISTORY = 25
    DEFAULT_PROXY_TYPE = "none"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsWidgetContainer")

        # Store initial settings (will be updated by apply_settings)
        self._current_settings = {} 
        
        # Store references to specific controls if needed outside init
        self.proxy_type_combo = None
        self.proxy_host_edit = None
        self.proxy_port_edit = None
        self.proxy_user_edit = None
        self.proxy_pass_edit = None
        self.delay_spinbox = None
        self.timeout_spinbox = None
        self.max_history_spinbox = None
        self.download_dir_label = None
        
        # Keep track of categories/sort options if needed for defaults
        self._categories_list = []
        self._sort_options = {}

        self._init_ui()

    def _init_ui(self):
        # Main layout for this widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15) # Padding for the content
        main_layout.setSpacing(15) # Spacing between group boxes

        # Group boxes will be added here
        # --- Scraper Section ---
        scraper_group = QGroupBox("Scraper Settings")
        main_layout.addWidget(scraper_group)
        scraper_layout = QVBoxLayout(scraper_group)
        scraper_layout.setContentsMargins(10, 15, 10, 10)
        scraper_layout.setSpacing(8)

        scraper_controls_layout = QGridLayout() 
        scraper_controls_layout.addWidget(QLabel("Cloudflare Delay (sec):"), 0, 0, Qt.AlignRight)
        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setRange(5, 60)
        self.delay_spinbox.setSingleStep(1)
        self.delay_spinbox.setToolTip("Delay (in seconds) between requests if Cloudflare challenge is detected (5-60).\nLower values might get blocked more easily.")
        # self.delay_spinbox.installEventFilter(self) # TODO: Re-add event filter if needed
        scraper_controls_layout.addWidget(self.delay_spinbox, 0, 1) 

        scraper_controls_layout.addWidget(QLabel("Network Timeout (sec):"), 1, 0, Qt.AlignRight)
        self.timeout_spinbox = QSpinBox()
        self.timeout_spinbox.setRange(10, 120) 
        self.timeout_spinbox.setSingleStep(5)
        self.timeout_spinbox.setToolTip("Maximum time (in seconds) to wait for a network response (10-120).")
        # self.timeout_spinbox.installEventFilter(self) # TODO: Re-add event filter if needed
        scraper_controls_layout.addWidget(self.timeout_spinbox, 1, 1) 

        scraper_controls_layout.setColumnStretch(1, 1) 
        scraper_layout.addLayout(scraper_controls_layout) 
        # Connect signals internally
        # self.delay_spinbox.valueChanged.connect(self._handle_delay_changed)
        # self.timeout_spinbox.valueChanged.connect(self._handle_network_timeout_changed)

        # --- Paths Section ---
        paths_group = QGroupBox("Reference Paths")
        main_layout.addWidget(paths_group)
        paths_layout = QVBoxLayout(paths_group)
        paths_layout.setContentsMargins(10, 15, 10, 10)
        paths_layout.setSpacing(8)

        dl_controls_layout = QHBoxLayout()
        select_dir_button = QPushButton(qta.icon('mdi.folder-outline'), " Set Reference Folder")
        select_dir_button.setToolTip("Select the folder your external torrent client typically saves to.\nThis is just a reference and doesn't affect downloads directly.")
        select_dir_button.clicked.connect(self.request_select_download_dir.emit) # Emit signal

        self.download_dir_label = QLabel("Client Folder: ...") 
        self.download_dir_label.setWordWrap(True)

        dl_controls_layout.addWidget(select_dir_button)
        dl_controls_layout.addWidget(self.download_dir_label, 1)
        paths_layout.addLayout(dl_controls_layout) 

        explanation_label = QLabel(
            "Set the default download location used by your external torrent client. "
            "This is primarily for reference."
        )
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("font-size: 9pt; color: grey;")
        paths_layout.addWidget(explanation_label) 

        # --- History Section ---
        history_group = QGroupBox("History")
        main_layout.addWidget(history_group)
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(10, 15, 10, 10)
        history_layout.setSpacing(8)

        history_controls_layout = QHBoxLayout()
        history_controls_layout.addWidget(QLabel("Max History Size:"))
        self.max_history_spinbox = QSpinBox()
        self.max_history_spinbox.setRange(5, 100) 
        self.max_history_spinbox.setSingleStep(5)
        self.max_history_spinbox.setToolTip("Maximum number of recent searches to keep in history (5-100).")
        # self.max_history_spinbox.installEventFilter(self) # TODO: Re-add event filter
        # Connect signals internally
        # self.max_history_spinbox.valueChanged.connect(self._handle_max_history_changed)
        history_controls_layout.addWidget(self.max_history_spinbox)
        history_controls_layout.addSpacing(20) 

        clear_history_button = QPushButton(qta.icon('mdi.trash-can-outline', color='tomato'), " Clear Search History")
        clear_history_button.setToolTip("Removes all saved search terms from the history dropdown.")
        clear_history_button.clicked.connect(self.request_clear_history.emit) # Emit signal

        history_controls_layout.addWidget(clear_history_button)
        history_controls_layout.addStretch() 
        history_layout.addLayout(history_controls_layout) 

        # --- Proxy Settings Section ---
        proxy_group = QGroupBox("Proxy Settings")
        main_layout.addWidget(proxy_group)
        proxy_layout_group = QVBoxLayout(proxy_group)
        proxy_layout_group.setContentsMargins(10, 15, 10, 10)
        proxy_layout_group.setSpacing(8)

        proxy_grid = QGridLayout() 

        proxy_grid.addWidget(QLabel("Proxy Type:"), 0, 0, Qt.AlignRight)
        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(["None", "HTTP", "SOCKS5"])
        self.proxy_type_combo.setToolTip("Select the type of proxy to use for network requests.")
        proxy_grid.addWidget(self.proxy_type_combo, 0, 1, 1, 3) 

        proxy_grid.addWidget(QLabel("Host:"), 1, 0, Qt.AlignRight)
        self.proxy_host_edit = QLineEdit()
        self.proxy_host_edit.setPlaceholderText("e.g., 127.0.0.1 or proxy.example.com")
        proxy_grid.addWidget(self.proxy_host_edit, 1, 1) 

        proxy_grid.addWidget(QLabel("Port:"), 1, 2, Qt.AlignRight) 
        self.proxy_port_edit = QLineEdit()
        self.proxy_port_edit.setPlaceholderText("e.g., 8080")
        proxy_grid.addWidget(self.proxy_port_edit, 1, 3) 

        proxy_grid.addWidget(QLabel("Username (Optional):"), 2, 0, Qt.AlignRight) 
        self.proxy_user_edit = QLineEdit()
        proxy_grid.addWidget(self.proxy_user_edit, 2, 1, 1, 3) 

        proxy_grid.addWidget(QLabel("Password (Optional):"), 3, 0, Qt.AlignRight) 
        self.proxy_pass_edit = QLineEdit()
        self.proxy_pass_edit.setEchoMode(QLineEdit.Password)
        proxy_grid.addWidget(self.proxy_pass_edit, 3, 1, 1, 3) 

        proxy_grid.setColumnStretch(1, 1) 
        proxy_grid.setColumnMinimumWidth(3, 80) 

        proxy_layout_group.addLayout(proxy_grid) 

        proxy_note_label = QLabel("Note: Changes may require restarting the application or initiating a new search to take full effect.")
        proxy_note_label.setStyleSheet("font-size: 8pt; color: grey;")
        proxy_note_label.setWordWrap(True)
        proxy_layout_group.addWidget(proxy_note_label)
        
        # Connect proxy signals internally
        # self.proxy_type_combo.currentIndexChanged.connect(self._handle_proxy_setting_changed)
        # self.proxy_host_edit.textChanged.connect(self._handle_proxy_setting_changed)
        # self.proxy_port_edit.textChanged.connect(self._handle_proxy_setting_changed)
        # self.proxy_user_edit.textChanged.connect(self._handle_proxy_setting_changed)
        # self.proxy_pass_edit.textChanged.connect(self._handle_proxy_setting_changed)

        # --- Reset Settings Button ---
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        self.reset_button = QPushButton(qta.icon('mdi.restore', color='orange'), " Reset All Settings to Defaults")
        self.reset_button.setToolTip("Resets all application settings to their original values.")
        self.reset_button.clicked.connect(self._confirm_reset_settings)
        reset_layout.addWidget(self.reset_button)
        main_layout.addLayout(reset_layout)

        # Add a stretch at the very end to push everything up
        main_layout.addStretch(1)

        # --- Connect internal signals ONCE after creating UI elements ---
        self._connect_internal_signals()

    # --- Placeholder methods to be filled ---

    def set_combo_options(self, categories_list, sort_options):
        """Sets the available options for category and sort dropdowns."""
        self._categories_list = categories_list
        self._sort_options = sort_options
        print("DEBUG: SettingsWidget combos options set (Defaults removed).")

    def apply_settings(self, settings_data: dict):
        """Applies loaded settings to the UI elements."""
        print(f"DEBUG: SettingsWidget applying settings: {list(settings_data.keys())}")
        self._current_settings = settings_data.copy() # Store the loaded settings
        self._update_ui_from_settings()

    def get_current_settings(self) -> dict:
        """Retrieves the current values from the UI elements and returns as dict."""
        # Read values from UI elements
        settings = {
            "scraper_delay": self.delay_spinbox.value(),
            "network_timeout": self.timeout_spinbox.value(),
            "max_history_items": self.max_history_spinbox.value(),
            "proxy_type": self.proxy_type_combo.currentText().lower(),
            "proxy_host": self.proxy_host_edit.text().strip(),
            "proxy_port": self.proxy_port_edit.text().strip(),
            "proxy_username": self.proxy_user_edit.text().strip(),
            "proxy_password": self.proxy_pass_edit.text(),
            # MainWindow handles saving these, but widget needs to know the current value for display
            "default_download_path": self._current_settings.get("default_download_path", ""), 
        }
        # Update internal cache before returning, useful if called externally before a signal
        self._current_settings.update(settings) 
        return settings

    def update_download_dir_label(self, path: str):
         """Updates the download directory label."""
         if self.download_dir_label:
              self.download_dir_label.setText(f"Client Folder: {path}")
         # Update internal cache as well
         self._current_settings["default_download_path"] = path

    def _update_ui_from_settings(self):
        """Updates all UI elements based on the internal _current_settings dict."""
        print("DEBUG: SettingsWidget updating UI from internal state.")
        # Block signals to prevent loops during update
        # Scraper
        self.delay_spinbox.blockSignals(True)
        self.delay_spinbox.setValue(self._current_settings.get("scraper_delay", self.DEFAULT_SCRAPER_DELAY))
        self.delay_spinbox.blockSignals(False)
        self.timeout_spinbox.blockSignals(True)
        self.timeout_spinbox.setValue(self._current_settings.get("network_timeout", self.DEFAULT_NETWORK_TIMEOUT))
        self.timeout_spinbox.blockSignals(False)

        # History
        self.max_history_spinbox.blockSignals(True)
        self.max_history_spinbox.setValue(self._current_settings.get("max_history_items", self.DEFAULT_MAX_HISTORY))
        self.max_history_spinbox.blockSignals(False)

        # Paths
        self.update_download_dir_label(self._current_settings.get("default_download_path", os.path.expanduser("~")))

        # Proxy
        proxy_type = self._current_settings.get("proxy_type", self.DEFAULT_PROXY_TYPE)
        self.proxy_type_combo.blockSignals(True)
        proxy_type_index = self.proxy_type_combo.findText(proxy_type.capitalize() if proxy_type != "none" else "None")
        self.proxy_type_combo.setCurrentIndex(proxy_type_index if proxy_type_index != -1 else 0)
        self.proxy_type_combo.blockSignals(False)

        self.proxy_host_edit.setText(self._current_settings.get("proxy_host", ""))
        self.proxy_port_edit.setText(self._current_settings.get("proxy_port", ""))
        self.proxy_user_edit.setText(self._current_settings.get("proxy_username", ""))
        self.proxy_pass_edit.setText(self._current_settings.get("proxy_password", ""))
        self._update_proxy_fields_enabled_state()

        # Connect signals now that UI is populated
        # self._connect_internal_signals()

    def _connect_internal_signals(self):
        """Connects signals from UI elements to internal handlers ONCE."""
        self.delay_spinbox.valueChanged.connect(self._handle_delay_changed)
        self.timeout_spinbox.valueChanged.connect(self._handle_network_timeout_changed)
        self.max_history_spinbox.valueChanged.connect(self._handle_max_history_changed)
        self.proxy_type_combo.currentIndexChanged.connect(self._handle_proxy_setting_changed)
        self.proxy_host_edit.textChanged.connect(self._handle_proxy_setting_changed)
        self.proxy_port_edit.textChanged.connect(self._handle_proxy_setting_changed)
        self.proxy_user_edit.textChanged.connect(self._handle_proxy_setting_changed)
        self.proxy_pass_edit.textChanged.connect(self._handle_proxy_setting_changed)
        print("DEBUG: SettingsWidget internal signals connected.")

    def _emit_changed_settings(self):
        """Emits the settings_changed signal with the current settings."""
        current_settings = self.get_current_settings()
        self.settings_changed.emit(current_settings)
        print("DEBUG: SettingsWidget emitted settings_changed")

    # --- Handlers for UI changes (moved from MainWindow) ---

    def _handle_delay_changed(self, value):
        if value != self._current_settings.get("scraper_delay"):
            print(f"SettingsWidget: Delay changed to: {value}")
            self._emit_changed_settings()

    def _handle_network_timeout_changed(self, value):
        if value != self._current_settings.get("network_timeout"):
            print(f"SettingsWidget: Timeout changed to: {value}")
            self._emit_changed_settings()

    def _handle_max_history_changed(self, value):
        if value != self._current_settings.get("max_history_items"):
            print(f"SettingsWidget: Max history changed to: {value}")
            self._emit_changed_settings()
            # MainWindow will handle trimming the actual history list via signal

    def _handle_proxy_setting_changed(self):
        """Called when any proxy UI element changes.
           Updates internal state, enables/disables fields, and emits signals.
        """
        # Read current values from UI
        current_type = self.proxy_type_combo.currentText().lower()
        current_host = self.proxy_host_edit.text().strip()
        current_port = self.proxy_port_edit.text().strip()
        current_user = self.proxy_user_edit.text().strip()
        current_pass = self.proxy_pass_edit.text()

        # Check if anything actually changed compared to *internal* state
        changed = False
        if current_type != self._current_settings.get("proxy_type"):
            changed = True
        if current_host != self._current_settings.get("proxy_host"):
            changed = True
        if current_port != self._current_settings.get("proxy_port"):
            changed = True
        if current_user != self._current_settings.get("proxy_username"):
            changed = True
        if current_pass != self._current_settings.get("proxy_password"):
            changed = True

        # Update enabled state regardless of whether value changed
        self._update_proxy_fields_enabled_state()

        if changed:
            print(f"SettingsWidget: Proxy settings changed")
            proxy_config = self.get_current_settings() # Get fresh dict including proxy changes
            self.proxy_config_changed.emit(proxy_config)
            self._emit_changed_settings() # Emit general save signal

    def _update_proxy_fields_enabled_state(self):
        """Enables/disables proxy detail fields based on selected type."""
        proxy_type = self.proxy_type_combo.currentText().lower()
        is_enabled = (proxy_type != "none")
        self.proxy_host_edit.setEnabled(is_enabled)
        self.proxy_port_edit.setEnabled(is_enabled)
        self.proxy_user_edit.setEnabled(is_enabled)
        self.proxy_pass_edit.setEnabled(is_enabled)

    def _confirm_reset_settings(self):
         reply = QMessageBox.question(self, "Reset Settings?",
                                      "Are you sure you want to reset all application settings to their defaults?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
         if reply == QMessageBox.Yes:
              print("SettingsWidget: Requesting settings reset from MainWindow.")
              self.request_reset_settings.emit() # Ask MainWindow to handle the reset logic

    # --- Event Filter (Moved from MainWindow) --- #
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        spin_boxes = [
            self.delay_spinbox,
            self.timeout_spinbox,
            self.max_history_spinbox
        ]
        # Filter out None values if some spinboxes weren't created yet
        spin_boxes = [box for box in spin_boxes if box is not None]

        if event.type() == QEvent.Type.Wheel and watched in spin_boxes:
            if not watched.hasFocus():
                # Ignore wheel event if the spinbox doesn't have focus
                event.ignore()
                return True # Event handled (ignored)
        # Pass the event on for other cases
        return super().eventFilter(watched, event)
