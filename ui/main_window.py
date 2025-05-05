import sys
import os
import webbrowser  
import pyperclip   
import json        
import re
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QLabel, QTabWidget, QComboBox, QStatusBar, QGroupBox, QGridLayout,
                               QSizePolicy, # Keep QSizePolicy
                               QSpinBox, # Keep QSpinBox
                               QFileDialog, QMessageBox, QDialog, QRadioButton, QButtonGroup,
                               QDateEdit, QFrame, QScrollArea, QCheckBox, QMenu) # REMOVE QDateEdit, ADD QCheckBox, QMenu
from PySide6.QtCore import Qt, QThread, Signal, QCoreApplication, QSettings, QDate, QTimer, QUrl, QSize, QObject, QEvent, QByteArray # REMOVE QDate, ADD QObject, QEvent, QByteArray
from PySide6.QtGui import QIcon, QAction, QDesktopServices, QPixmap, QColor, QPalette, QClipboard, QKeySequence, QShortcut # Added QAction, QClipboard, QKeySequence, QShortcut
import qtawesome as qta

# Core component imports (Scraper remains, TorrentManager removed)
from core.scraper import NyaaScraper, ScrapeResult, TorrentDetails, format_size
from ui.torrent_detail_dialog import TorrentDetailDialog
from ui.filter_dialog import FilterDialog # Import the new dialog
from .settings_widget import SettingsWidget # Import the new widget

# --- Worker Thread for Scraping Search Results (Keep) ---
class ScraperWorker(QThread):
    results_ready = Signal(list) # list[ScrapeResult]
    error_occurred = Signal(str)

    def __init__(self, query, category, sort_by, page, delay, timeout, proxy_config, trusted_only, uploader):
        super().__init__()
        self.query = query
        self.category = category
        self.sort_by = sort_by
        self.page = page
        self.delay = delay
        self.timeout = timeout
        self.proxy_config = proxy_config
        self.trusted_only = trusted_only # Store trusted filter state
        self.uploader = uploader # Store uploader filter state
        # Initializing scraper here means a new session for each search.
        # Consider initializing it once in MainWindow and passing it if session reuse is desired.
        # However, re-initializing might be safer if sessions expire or have issues.
        self.scraper = NyaaScraper(cloudflare_delay=self.delay, proxy_config=self.proxy_config)

    def run(self):
        try:
            print(f"Worker starting scrape: Q='{self.query}', Cat='{self.category}', Sort='{self.sort_by}', Page={self.page}, Delay={self.delay}s, Timeout={self.timeout}s, Trusted={self.trusted_only}, Uploader='{self.uploader}'")
            results = self.scraper.search(
                self.query,
                category=self.category,
                sort_by=self.sort_by,
                page=self.page,
                timeout=self.timeout,
                trusted_only=self.trusted_only,
                uploader=self.uploader # Pass uploader state to scraper
            )
            self.results_ready.emit(results)
        except ConnectionError as e:
             print(f"Scraper Connection error: {e}")
             self.error_occurred.emit(f"Connection error: {e}")
        except FileNotFoundError as e: # Might occur if API changes, but less likely for search
             print(f"Scraper FileNotFoundError: {e}")
             self.error_occurred.emit(f"Resource not found: {e}")
        except RuntimeError as e: # Catch specific runtime errors from scraper
             print(f"Scraper Runtime error: {e}")
             self.error_occurred.emit(f"Scraping failed: {e}")
        except Exception as e:
            # Log the full traceback for debugging
            import traceback
            print(f"Scraper error: {type(e).__name__} - {e}")
            traceback.print_exc()
            self.error_occurred.emit(f"An unexpected error occurred during search: {e}")

# --- Worker Thread for Scraping Torrent Details (Keep) ---
class DetailScraperWorker(QThread):
    details_ready = Signal(TorrentDetails)
    error_occurred = Signal(str)

    def __init__(self, url, delay, timeout, proxy_config):
        super().__init__()
        self.url = url
        self.delay = delay
        self.timeout = timeout
        self.proxy_config = proxy_config
        self.scraper = NyaaScraper(cloudflare_delay=self.delay, proxy_config=self.proxy_config)

    def run(self):
        try:
            print(f"Detail Worker starting scrape for: {self.url}, Delay={self.delay}s, Timeout={self.timeout}s")
            details = self.scraper.get_torrent_details(self.url, timeout=self.timeout)
            self.details_ready.emit(details)
        except FileNotFoundError as e:
            print(f"Detail scraper error: {e}")
            self.error_occurred.emit(f"{e}") # Pass cleaner message
        except ConnectionError as e:
             print(f"Detail scraper error: {e}")
             self.error_occurred.emit(f"Connection error: {e}")
        except RuntimeError as e:
            print(f"Detail scraper error: {e}")
            self.error_occurred.emit(f"Failed to parse details: {e}")
        except ValueError as e: # Catch invalid URL error from get_torrent_details
            print(f"Detail scraper error: {e}")
            self.error_occurred.emit(f"Invalid URL: {e}")
        except Exception as e:
            import traceback
            print(f"Detail scraper error: {type(e).__name__} - {e}")
            traceback.print_exc()
            self.error_occurred.emit(f"An unexpected error occurred fetching details: {e}")

# --- Main Application Window ---
class MainWindow(QMainWindow):
    # --- Constants ---
    DEFAULT_SCRAPER_DELAY = 10 # Default delay value
    APP_NAME = "NyaaDesktopClient" # Define once
    ORG_NAME = "YourOrgName" # Optional: For QSettings

    SETTINGS_FILE_NAME = "settings.json" # Use .json extension

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{self.APP_NAME}")
        self.setGeometry(100, 100, 1200, 700)
        # Set window icon (optional)
        # try:
        #     self.setWindowIcon(qta.icon('fa5s.cat', color='lightblue')) # Example icon
        # except Exception as e:
        #     print(f"Warning: Could not set window icon - {e}")

        
        # --- Core Components ---
        self.current_page = 1
        self.current_search_query = ""
        self.current_category = "0_0"
        self.current_sort_by = "date"
        self.saved_download_path = os.path.expanduser("~") # Default to user's home dir initially
        self.detail_worker = None
        self.scraper_worker = None # Track search worker too

        # --- Corrected Mappings for UI Columns ---
        # UI Columns: [Mark(0), Cat(1), Name(2), Size(3), Date(4), S(5), L(6), Uploader(7), Actions(8)]
        # Nyaa Sort Keys: name, size, id (for date), seeders, leechers

        # Map API sort key -> UI Column Index
        self.sort_key_to_column_map = {
            "name": 2,
            "size": 3,
            "date": 4,  # Represents sorting by date
            "seeders": 5,
            "leechers": 6,
            "id": 4     # Nyaa API uses 'id' for date sorting, map it to the same UI column
        }

        # Map UI Column Index -> API Sort Key (used for header clicks)
        self.column_to_sort_key_map = {
            2: "name",
            3: "size",
            4: "date",    # Clicking UI Date column (4) should sort by 'date'
            5: "seeders",
            6: "leechers"
        }
        # Note: We don't need a reverse mapping for UI Col 1 (Cat), 7 (Uploader), 8 (Actions) as they aren't sorted via header click

        # Initialize current sort based on default ('date')
        self.current_sort_by = "date" # Default sort key (used by dropdown and worker)
        self.current_sort_column = self.sort_key_to_column_map.get(self.current_sort_by, 3) # Should map to 4 (Date column)
        self.current_sort_order = Qt.DescendingOrder

        # --- State Variables ---
        self.scraper_delay = self.DEFAULT_SCRAPER_DELAY
        self.search_history = []
        self.max_history_items = 25 # Default, will be loaded from settings
        # Filter States
        self.min_size_bytes = 0
        self.max_size_bytes = 0 # 0 means no upper limit
        self.min_seeders = 0
        self.filter_trusted_only = False # Add state for trusted filter
        self.filter_uploader = "" # Add state for uploader filter
        self.current_results = [] # Store the currently displayed results for context menu
        self.network_timeout = 30 # Default seconds, loaded from settings
        self.default_download_path = os.path.expanduser("~") # Default to user's home dir
        # self.start_date = None # Remove date filters
        # _initial_load_done = False # Flag no longer needed with this approach

        # --- Proxy State --- #
        self.proxy_type = "none" # none, http, socks5
        self.proxy_host = ""
        self.proxy_port = ""
        self.proxy_username = ""
        self.proxy_password = ""

        # --- Mark As State --- #
        self.marked_torrents = set() # Store links of marked torrents

        # Map Nyaa category strings to Material Design Icons and colors
        # Using keywords allows flexibility
        self.category_icon_map = {
            "Anime - AMV": ("mdi.filmstrip", "lightblue"),
            "Anime - English-translated": ("mdi.translate", "lightgreen"),
            "Anime - Non-English-translated": ("mdi.translate", "salmon"),
            "Anime - Raw": ("mdi.video-outline", "lightgrey"),
            "Audio - Lossless": ("mdi.music-note-outline", "cyan"),
            "Audio - Lossy": ("mdi.music-note-outline", "skyblue"),
            "Literature - English-translated": ("mdi.book-open-page-variant-outline", "lightgreen"),
            "Literature - Non-English-translated": ("mdi.book-open-page-variant-outline", "salmon"),
            "Literature - Raw": ("mdi.book-outline", "lightgrey"),
            "Live Action - English-translated": ("mdi.television-classic", "lightgreen"),
            "Live Action - Idol/Promotional Video": ("mdi.star-outline", "pink"),
            "Live Action - Non-English-translated": ("mdi.television-classic", "salmon"),
            "Live Action - Raw": ("mdi.television-classic-off", "lightgrey"),
            "Pictures - Graphics": ("mdi.image-outline", "mediumpurple"),
            "Pictures - Photos": ("mdi.camera-outline", "lightcoral"),
            "Software - Applications": ("mdi.application-cog-outline", "orange"),
            "Software - Games": ("mdi.gamepad-variant-outline", "tomato"),
            "default": ("mdi.help-circle-outline", "grey")
        }

        # --- Directly Apply Dark Theme Here ---
        self._apply_dark_theme_stylesheet()

        # --- Initialize UI ---
        self.init_ui()

        # --- Initialize Filter Dialog --- #
        self.filter_dialog = FilterDialog(self)
        self.filter_dialog.filters_applied.connect(self._apply_filters_from_dialog)
        self.filter_dialog.filters_cleared.connect(self._clear_filters_from_dialog)

        # --- Final Setup after UI and Settings --- #
        # Connect signals that might trigger unwanted searches during init/load
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)

        # Connect item changed signal for checkbox handling
        self.results_table.itemChanged.connect(self._handle_item_marked_state_changed)

        # Trigger initial search after everything is set up
        print("DEBUG: Triggering initial search after __init__.")
        QTimer.singleShot(0, self._trigger_initial_search) # Use timer

        # --- Setup Global Shortcuts ---
        self._setup_shortcuts()

    def _apply_dark_theme_stylesheet(self):
        """Loads and applies the dark theme stylesheet."""
        theme_path = "ui/styles/dark_theme.qss"
        stylesheet = ""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            abs_theme_path = os.path.join(script_dir, 'styles', os.path.basename(theme_path))

            if not os.path.exists(abs_theme_path):
                print(f"ERROR: Dark stylesheet not found: {abs_theme_path}")
            else:
                with open(abs_theme_path, "r", encoding="utf-8") as f:
                    stylesheet = f.read()
                print(f"Applying default dark theme from {abs_theme_path}")

        except Exception as e:
            print(f"ERROR loading stylesheet {theme_path}: {e}")

        app = QCoreApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            print("Error: Could not get QApplication instance to apply stylesheet.")

    def _attempt_initial_transmission_connect(self):
        """Tries to connect to Transmission on startup and start the timer if successful."""
        print("Attempting initial connection to Transmission...")
        try:
            # Try getting status as a connection test
            self.transmission_manager.get_torrents_status()
            self._transmission_connected = True
            print("Initial Transmission connection successful. Starting refresh timer.")
            self.show_status_message("Connected to Transmission.", 5000)
            self.download_refresh_timer.start(self.download_refresh_interval_ms)
            # Trigger an immediate refresh
            self._refresh_download_list()
        except ConnectionError as e:
            self._transmission_connected = False
            print(f"Initial Transmission connection failed: {e}")
            self.show_error_message(f"Transmission Connect Failed: {e} - Check Settings tab.")
            self._show_disconnected_state()
        except Exception as e:
            self._transmission_connected = False
            print(f"Unexpected error during initial Transmission connection: {e}")
            self.show_error_message(f"Transmission Init Error: {e}")
            self._show_disconnected_state()

    def _show_disconnected_state(self):
        """Updates UI elements to reflect a disconnected state from Transmission."""
        self.downloads_table.clearContents()
        self.downloads_table.setRowCount(0)
        # Maybe add a placeholder row?
        # self.downloads_table.setRowCount(1)
        # placeholder_item = QTableWidgetItem("Not connected to Transmission. Check Settings.")
        # placeholder_item.setTextAlignment(Qt.AlignCenter)
        # self.downloads_table.setItem(0, 0, placeholder_item)
        # self.downloads_table.setSpan(0, 0, 1, self.downloads_table.columnCount())
        # Disable buttons
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.remove_data_button.setEnabled(False)
        # Ensure timer is stopped
        if self.download_refresh_timer.isActive():
             print("Stopping download refresh timer due to disconnect.")
             self.download_refresh_timer.stop()
        self._transmission_connected = False # Explicitly set flag
        # Update status bar persistently?
        self.show_status_message("Error: Disconnected from Transmission. Check Settings.", 0) # timeout 0 for persistent

    def get_category_icon(self, category_name):
        """Gets a qtawesome icon based on the category name."""
        # Normalize category name for comparison
        norm_category_name = category_name.lower().strip()
        # Prioritize exact matches first
        if norm_category_name in (key.lower() for key in self.category_icon_map):
             for key, (icon_name, color) in self.category_icon_map.items():
                 if key.lower() == norm_category_name:
                      return qta.icon(icon_name, color=color)

        # Fallback to keyword matching
        for key, (icon_name, color) in self.category_icon_map.items():
            if key == "default": continue # Skip default in keyword search
            # Match if key (as a keyword) is in the category name
            if key.lower() in norm_category_name:                
                return qta.icon(icon_name, color=color)
        # Final fallback
        return qta.icon(self.category_icon_map["default"][0], color=self.category_icon_map["default"][1])

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Tabs ---
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- Search Tab ---
        search_tab = QWidget(objectName="SearchTabWidget")
        search_layout = QVBoxLayout(search_tab)
        search_layout.setContentsMargins(10, 10, 10, 10)
        search_layout.setSpacing(12)
        self.tabs.addTab(search_tab, qta.icon('mdi.magnify', color='lightblue'), "Search")

        # -- Top Search Area --
        top_search_layout = QHBoxLayout()
        search_layout.addLayout(top_search_layout)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Nyaa.si...")
        self.search_input.setToolTip("Enter search terms. You can use Nyaa operators like uploader:SomeUser, -exclude, trusted:yes")
        self.search_input.returnPressed.connect(lambda: self.start_search(reset_page=True))
        self.search_input.textChanged.connect(self._apply_row_visibility_filters) # Connect textChanged to filter method
        top_search_layout.addWidget(self.search_input, 1) # Give search input stretch factor

        # -- Category Filter --
        self.category_combo = QComboBox()
        # Store categories in a way that preserves order easily
        self.categories_list = [
           ("All categories", "0_0"), ("Anime", "1_0"), # Added main Anime category
            ("Anime - AMV", "1_1"), ("Anime - English-translated", "1_2"),
            ("Anime - Non-English-translated", "1_3"), ("Anime - Raw", "1_4"),
            ("Audio", "2_0"), # Added main Audio category
            ("Audio - Lossless", "2_1"), ("Audio - Lossy", "2_2"),
            ("Literature", "3_0"), # Added main Literature category
            ("Literature - English-translated", "3_1"), ("Literature - Non-English-translated", "3_2"),
            ("Literature - Raw", "3_3"),
            ("Live Action", "4_0"), # Added main Live Action category
            ("Live Action - English-translated", "4_1"), ("Live Action - Idol/Promotional Video", "4_2"),
            ("Live Action - Non-English-translated", "4_3"), ("Live Action - Raw", "4_4"),
            ("Pictures", "5_0"), # Added main Pictures category
            ("Pictures - Graphics", "5_1"), ("Pictures - Photos", "5_2"),
            ("Software", "6_0"), # Added main Software category
            ("Software - Applications", "6_1"), ("Software - Games", "6_2")
         ]
        for name, code in self.categories_list:
            self.category_combo.addItem(name, code)
        self.category_combo.currentIndexChanged.connect(self.on_category_changed) # Connect AFTER init/load
        top_search_layout.addWidget(QLabel("Category:"))
        top_search_layout.addWidget(self.category_combo)

        # -- Sort Filter --
        self.sort_combo = QComboBox()
        self.sort_options = {
            "Date": "date", "Seeders": "seeders", "Leechers": "leechers",
            "Size": "size", "Name": "name"
        }
        for name, code in self.sort_options.items():
            self.sort_combo.addItem(name, code)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed) # Connect AFTER init/load
        # Connect AFTER load_settings potentially sets initial sort? No, connect here.
        # self.sort_combo.currentIndexChanged.connect(self.on_sort_changed) # Connect AFTER init/load
        top_search_layout.addWidget(QLabel("Sort by:"))
        top_search_layout.addWidget(self.sort_combo)

        # -- Uploader Filter --
        top_search_layout.addWidget(QLabel("Uploader:"))
        self.uploader_filter_input = QLineEdit()
        self.uploader_filter_input.setPlaceholderText("Optional name")
        self.uploader_filter_input.setToolTip("Filter results by a specific uploader name.")
        self.uploader_filter_input.setFixedWidth(120) # Give it a reasonable fixed width
        self.uploader_filter_input.returnPressed.connect(lambda: self.start_search(reset_page=True))
        self.uploader_filter_input.textChanged.connect(self._on_uploader_filter_changed)
        top_search_layout.addWidget(self.uploader_filter_input)
        top_search_layout.addSpacing(5)

        # -- Quick Filters --
        self.trusted_checkbox = QCheckBox("Trusted Only")
        self.trusted_checkbox.setToolTip("Show only torrents from trusted users.")
        self.trusted_checkbox.stateChanged.connect(self._on_trusted_filter_changed)
        top_search_layout.addWidget(self.trusted_checkbox)
        top_search_layout.addSpacing(10) # Add space before Filters button

        # --- Filters Button --- #
        self.filters_button = QPushButton(qta.icon('mdi.filter-variant'), "Filters")
        self.filters_button.setToolTip("Set additional search filters (size, seeders, etc.)")
        self.filters_button.setCheckable(False) # We'll manage style manually
        self.filters_button.setObjectName("FiltersButton") # For QSS styling
        self.filters_button.clicked.connect(self._show_filter_dialog)
        top_search_layout.addWidget(self.filters_button)
        top_search_layout.addSpacing(10) # Space before search button

        # Keep Search button at the end
        search_button = QPushButton(qta.icon('mdi.magnify', color='white'), "Search")
        search_button.clicked.connect(lambda: self.start_search(reset_page=True))
        top_search_layout.addWidget(search_button)

        # -- Search History Area --
        history_layout = QHBoxLayout()
        history_layout.addWidget(QLabel("History:"))
        self.history_combo = QComboBox()
        self.history_combo.setPlaceholderText("Recent searches...")
        self.history_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.history_combo.setEditable(False)
        self.history_combo.activated.connect(self._use_search_history)
        history_layout.addWidget(self.history_combo, 1) # Give stretch        
        search_layout.addLayout(history_layout)

        # -- Loading Indicator --
        self.loading_indicator_label = QLabel()
        loading_icon = qta.icon('mdi.loading', animation=qta.Spin(self), color='grey') # Use mdi.loading
        self.loading_indicator_label.setPixmap(loading_icon.pixmap(QSize(32, 32))) # Use pixmap
        self.loading_indicator_label.setAlignment(Qt.AlignCenter)
        self.loading_indicator_label.hide() # Initially hidden
        search_layout.addWidget(self.loading_indicator_label)

        # -- Results Table --
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(9)
        self.results_table.setHorizontalHeaderLabels(["Mark", "Cat", "Name", "Size", "Date", "S", "L", "Uploader", "Actions"])
        self.mark_column_index = 0 # Store index for later use
        self.results_table.horizontalHeader().setSectionResizeMode(self.mark_column_index, QHeaderView.ResizeToContents) # Mark column
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch) # Stretch Name column (index shifted)
        self.results_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents) # Actions column size fixed (index shifted)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.ExtendedSelection) # Enable multi-selection
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(False) # Disable Qt's sorting
        # Enable custom context menu
        self.results_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._show_table_context_menu)
        # Connect header click signal AFTER UI setup
        self.results_table.horizontalHeader().sectionClicked.connect(self.handle_header_click)
        self.results_table.horizontalHeader().setSectionsMovable(True)
        self.results_table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.horizontalHeader().customContextMenuRequested.connect(self._show_header_context_menu)
        search_layout.addWidget(self.results_table)

        # -- Pagination Controls --
        pagination_layout = QHBoxLayout()
        search_layout.addLayout(pagination_layout)
        self.prev_button = QPushButton(qta.icon('mdi.arrow-left'), "Previous")
        self.prev_button.clicked.connect(self.prev_page)
        self.prev_button.setEnabled(False)
        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_button = QPushButton("Next", icon=qta.icon('mdi.arrow-right'))
        self.next_button.setIcon(qta.icon('mdi.arrow-right')) # Set icon properly
        self.next_button.setLayoutDirection(Qt.RightToLeft) # Move icon to right
        self.next_button.clicked.connect(self.next_page)
        self.next_button.setEnabled(False)
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.next_button)

        # --- Download Folder Tab (Simplified) ---
        downloads_tab = QWidget(objectName="DownloadsTabWidget")
        downloads_layout = QVBoxLayout(downloads_tab)
        downloads_layout.setContentsMargins(10, 10, 10, 10)
        downloads_layout.setSpacing(10)
        self.tabs.addTab(downloads_tab, qta.icon('mdi.folder-open-outline', color='lightgoldenrodyellow'), "External Client Path")

        dl_controls_layout = QHBoxLayout()
        select_dir_button = QPushButton(qta.icon('mdi.folder-outline'), "Set Reference Folder")
        select_dir_button.setToolTip("Select the folder your external torrent client typically saves to.\nThis is just a reference and doesn't affect downloads directly.")
        select_dir_button.clicked.connect(self.select_download_directory)

        self.download_dir_label = QLabel(f"Client Folder: {self.saved_download_path}")
        self.download_dir_label.setWordWrap(True)

        dl_controls_layout.addWidget(select_dir_button)
        dl_controls_layout.addWidget(self.download_dir_label, 1)
        downloads_layout.addLayout(dl_controls_layout)

        explanation_label = QLabel(
            "Set the default download location used by your external torrent client. \n"
            "This is primarily for reference (e.g., future features like checking for existing files). \n"
            "This application does not download files itself."
        )
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("font-size: 9pt; color: grey;") # Optional styling
        downloads_layout.addWidget(explanation_label)

        downloads_layout.addStretch()

        # --- Settings Tab --- #
        settings_tab = QWidget(objectName="SettingsTabWidget")
        settings_tab_layout = QVBoxLayout(settings_tab) # Layout FOR the tab itself
        settings_tab_layout.setContentsMargins(0, 0, 0, 0) # No margins for the tab's direct layout

        # Create Scroll Area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("SettingsScrollArea") # For potential QSS styling
        scroll_area.setStyleSheet("QScrollArea#SettingsScrollArea { border: none; }") # Remove scroll area border
        settings_tab_layout.addWidget(scroll_area) # Add scroll area TO the tab layout

        # Create Container Widget for Settings Content (goes INSIDE scroll area)
        settings_content_widget = QWidget()
        scroll_area.setWidget(settings_content_widget)

        # Layout for the Settings Content (group boxes go here)
        settings_content_layout = QVBoxLayout(settings_content_widget)
        settings_content_layout.setContentsMargins(15, 15, 15, 15) # Padding for the content inside scroll area
        settings_content_layout.setSpacing(10) # Spacing between group boxes

        # Add the actual tab widget
        self.tabs.addTab(settings_tab, qta.icon('mdi.cog-outline', color='gray'), "Settings")

        # --- Add SettingsWidget to Scroll Area ---
        # Moved import to top
        self.settings_widget = SettingsWidget(self)
        scroll_area.setWidget(self.settings_widget)
        # --- Connect SettingsWidget signals to MainWindow slots ---
        self.settings_widget.settings_changed.connect(self._handle_settings_widget_change)
        self.settings_widget.proxy_config_changed.connect(self._handle_proxy_config_change)
        self.settings_widget.request_clear_history.connect(self._clear_search_history)
        self.settings_widget.request_select_download_dir.connect(self.select_download_directory)
        # Pass necessary data/connect signals after settings are loaded

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar) # Set the status bar

        # --- Setup Global Shortcuts (Called AFTER all UI elements are created) ---
        self._setup_shortcuts()

    # --- Event Filter for SpinBox Scroll --- # REMOVE THIS METHOD
    # def eventFilter(self, watched: QObject, event: QEvent) -> bool:
    # ... (code removed) ...

    # --- Clear Search History --- # Keep this, triggered by signal
    def _clear_search_history(self):
        """Clears the search history after confirmation."""
        reply = QMessageBox.question(self, "Clear History?",
                                     "Are you sure you want to clear your search history?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.search_history = []
            self._update_history_combo() # Update dropdown UI
            self.save_settings() # Persist the empty list
            self.show_status_message("Search history cleared.", 3000)
        else:
            self.show_status_message("Clear history cancelled.", 3000)

    # --- Helper Function for Parsing Size Input ---
    def _parse_user_size_input(self, size_str: str) -> int:
        """Parses user input like '1.5 GiB', '500MB', '1024k' into bytes."""
        if not isinstance(size_str, str) or not size_str.strip():
            return 0

        size_str = size_str.strip().upper()
        # Allow variations: G, GB, GIB or M, MB, MIB etc.
        match = re.match(r'^([\d.,]+)\s*([KMGT])?I?B?$', size_str)

        if not match:
            # Handle plain numbers as bytes
            try:
                return int(size_str.replace(',', ''))
            except ValueError:
                return 0 # Invalid format

        num_str, unit = match.groups()
        num_str = num_str.replace(',', '')
        try:
            num = float(num_str)
        except ValueError:
            return 0 # Invalid number part

        units = {'K': 1, 'M': 2, 'G': 3, 'T': 4}
        exponent = units.get(unit, 0) # Default to 0 (Bytes) if no unit
        return int(num * (1024 ** exponent))

    # --- Search History Handling ---
    def _update_history_combo(self):
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        self.history_combo.addItems(self.search_history)
        self.history_combo.setCurrentIndex(-1)
        self.history_combo.blockSignals(False)

    def _add_to_search_history(self, term: str):
        if not term: return
        term = term.strip()
        if not term: return # Check again after stripping

        if term in self.search_history:
            self.search_history.remove(term)
        self.search_history.insert(0, term)
        self.search_history = self.search_history[:self.max_history_items]
        self._update_history_combo()
        # Defer saving settings until explicitly called or on exit for performance
        # self.save_settings() # Optional: save immediately

    def _use_search_history(self, index: int):
        if 0 <= index < len(self.search_history):
            selected_term = self.search_history[index]
            print(f"Using history term: '{selected_term}'")
            self.search_input.setText(selected_term)
            # Move selected term to front (effectively adds it again)
            self._add_to_search_history(selected_term)
            # Trigger search, indicating it's from history to prevent re-adding
            self.start_search(reset_page=True, from_history=True)

    # --- Max History Handling --- # REMOVE THIS METHOD
    # def _on_max_history_changed(self, value):
    # ... (code removed) ...

    # --- Scraper Delay Handling --- # REMOVE THIS METHOD
    # def _on_delay_changed(self, value):
    # ... (code removed) ...

    # --- Network Timeout Handling --- # REMOVE THIS METHOD
    # def _on_network_timeout_changed(self, value):
    # ... (code removed) ...

    # --- Default Sort Handling --- # REMOVE THIS METHOD
    # def _on_default_sort_changed(self):
    # ... (code removed) ...

    # --- Default Category Handling --- # REMOVE THIS METHOD
    # def _on_default_category_changed(self):
    # ... (code removed) ...

    # --- UI Actions ---
    def on_category_changed(self):
        new_category = self.category_combo.currentData()
        if new_category != self.current_category:
             self.current_category = new_category
             print(f"Category changed to: {self.current_category}")
             # Trigger search only if the category actually changed
             self.start_search(reset_page=True)
             
    def on_sort_changed(self):
        new_sort_key = self.sort_combo.currentData()
        if new_sort_key != self.current_sort_by:
             self.current_sort_by = new_sort_key
             self.current_sort_column = self.sort_key_to_column_map.get(self.current_sort_by, 3) # Default date
             self.current_sort_order = Qt.DescendingOrder # Nyaa default
             print(f"Sort changed via dropdown to: {self.current_sort_by} (Col: {self.current_sort_column}, Order: Desc)")
             # Update header indicator
             self.results_table.horizontalHeader().setSortIndicator(
                 self.current_sort_column, self.current_sort_order
             )
             # Trigger search only if sort actually changed
             self.start_search(reset_page=True)
             
    def start_search(self, reset_page=False, from_history=False):
        print("DEBUG: start_search entered.") # DEBUG
        query = self.search_input.text().strip()

        # Filter state is now managed by the dialog handlers
        print(f"Filters Applied - Min Seeders: {self.min_seeders}, Min Size: {self.min_size_bytes} B, Max Size: {self.max_size_bytes if self.max_size_bytes > 0 else 'None'} B")

        if reset_page:
            self.current_page = 1

        # Add to history only if it's a manual search (not from history dropdown) and query is not empty
        if not from_history and query:
            self._add_to_search_history(query)

        self.current_search_query = query
        self.show_status_message(f"Searching for '{query}' (Page {self.current_page})...")
        self.results_table.setRowCount(0)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.loading_indicator_label.show() # Show loading indicator

        # Ensure indicator reflects current sort state before search
        self.results_table.horizontalHeader().setSortIndicator(
            self.current_sort_column, self.current_sort_order
        )
        self.results_table.horizontalHeader().setSortIndicatorShown(True)

        # Abort previous search worker if running
        if self.scraper_worker and self.scraper_worker.isRunning():
            print("Terminating previous search worker...")
            self.scraper_worker.terminate() # Forcefully stop
            self.scraper_worker.wait() # Wait for termination
            print("Previous search worker terminated.")

        # Prepare proxy config dictionary
        proxy_config = {
            'type': self.proxy_type,
            'host': self.proxy_host,
            'port': self.proxy_port,
            'username': self.proxy_username,
            'password': self.proxy_password
        }

        self.scraper_worker = ScraperWorker(
            self.current_search_query,
            self.current_category,
            self.current_sort_by,
            self.current_page,
            self.scraper_delay,
            self.network_timeout,
            proxy_config, # Pass proxy config
            self.filter_trusted_only, # Pass trusted filter state
            self.filter_uploader # Pass uploader filter state
        )
        self.scraper_worker.results_ready.connect(self.update_results_table)
        self.scraper_worker.error_occurred.connect(self.show_error_message)
        self.scraper_worker.finished.connect(self._on_search_worker_finished) # Cleanup connection
        print("DEBUG: Starting scraper worker...") # DEBUG
        self.scraper_worker.start()
        
    def _on_search_worker_finished(self):
        print("DEBUG: _on_search_worker_finished called.") # DEBUG
        print("Search worker finished.")
        # Hide loading indicator when worker finishes (success or error)
        self.loading_indicator_label.hide()
        # Clear status bar only if it was showing the "Searching..." message for the *current* query/page
        # This check might be complex, simpler to just clear if it starts with "Searching..."
        current_msg = self.status_bar.currentMessage()
        if current_msg.startswith("Searching"):
            self.status_bar.clearMessage()
        # Allow the results_ready or error_occurred signal to set the final status
        self.scraper_worker = None # Release reference

    def update_results_table(self, results: list[ScrapeResult]):
        print(f"DEBUG: update_results_table called with {len(results)} results.") # DEBUG
        # Check if this worker's results are still relevant (e.g., user hasn't started a new search)
        # Basic check - could be enhanced if needed
        # if self.sender() != self.scraper_worker:
        #     print("Ignoring results from outdated search worker.")
        #     return

        self.results_table.setRowCount(0)
        original_results_count = len(results)

        # --- Apply Client-Side Filters ---
        filtered_results = []
        # Check if any filter is active
        filtering_active = self.min_seeders > 0 or self.min_size_bytes > 0 or self.max_size_bytes > 0

        if filtering_active:
            for result in results:
                # Seeder Check
                if self.min_seeders > 0 and result.seeders < self.min_seeders:
                    continue
                # Min Size Check
                if self.min_size_bytes > 0 and result.size_bytes < self.min_size_bytes:
                    continue
                # Max Size Check (only if max_size_bytes is set > 0)
                if self.max_size_bytes > 0 and result.size_bytes > self.max_size_bytes:
                    continue

                # If all checks pass, add to filtered list
                filtered_results.append(result)
        else:
            filtered_results = results # No filters applied

        # --- Store results for context menu access --- #
        self.current_results = filtered_results

        # --- Use filtered_results from now on ---
        results_count = len(filtered_results)
        print(f"Displaying {results_count} results after filtering from {original_results_count} fetched.")

        if results_count == 0:
            if self.current_page == 1:
                self.show_status_message(f"No results found for '{self.current_search_query}'.", 5000)
            else:
                self.show_status_message(f"No more results found.", 5000)
            # Update pagination based on current page even if no results
            self.prev_button.setEnabled(self.current_page > 1)
            self.next_button.setEnabled(False)
            self.page_label.setText(f"Page {self.current_page}")
            return

        self.results_table.setRowCount(results_count)

        # Performance: Disable sorting and updates during population
        self.results_table.setSortingEnabled(False)
        self.setUpdatesEnabled(False)

        for row, result in enumerate(filtered_results):
            # Category Item
            category_item = QTableWidgetItem()
            category_item.setIcon(self.get_category_icon(result.category))
            category_item.setToolTip(result.category)
            self.results_table.setItem(row, 1, category_item)

            # Name Item
            name_item = QTableWidgetItem(result.name)
            name_item.setToolTip(result.name)
            self.results_table.setItem(row, 2, name_item)

            # Other text items            
            self.results_table.setItem(row, 3, QTableWidgetItem(result.size))
            self.results_table.setItem(row, 4, QTableWidgetItem(result.date))

            # Numeric items (aligned)
            s_item = QTableWidgetItem(str(result.seeders))
            s_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(row, 5, s_item)
            l_item = QTableWidgetItem(str(result.leechers))
            l_item.setTextAlignment(Qt.AlignCenter)
            self.results_table.setItem(row, 6, l_item)

            # Uploader Item            
            uploader_item = QTableWidgetItem(result.uploader)
            uploader_item.setToolTip(result.uploader)
            self.results_table.setItem(row, 7, uploader_item)

            # Actions Column
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(5)
            actions_layout.setAlignment(Qt.AlignCenter) # Center buttons in the cell

            # Magnet Button (Opens Link)            
            magnet_button = QPushButton(qta.icon('mdi.magnet', color='red'), "")
            magnet_button.setToolTip(f"Open Magnet Link")
            if result.magnet_link:
                 # Correct lambda capture:                 
                 magnet_button.clicked.connect(lambda checked=False, magnet=result.magnet_link, name=result.name: self.add_download(magnet, name))
            else:
                magnet_button.setEnabled(False)
                magnet_button.setToolTip("Magnet link not found")
            actions_layout.addWidget(magnet_button)

            # Details Button
            details_button = QPushButton(qta.icon('mdi.information-outline', color='lightblue'), "")
            details_button.setToolTip("View Torrent Details")
            if result.link and result.link != '#':
                # Correct lambda capture:                
                details_button.clicked.connect(lambda checked=False, link=result.link: self.show_details(link))
            else:
                details_button.setEnabled(False)
                details_button.setToolTip("Details link not found or invalid")
            actions_layout.addWidget(details_button)

            actions_widget.setLayout(actions_layout)
            self.results_table.setCellWidget(row, 8, actions_widget)

            # Store the link (identifier) for the handler
            torrent_link = result.link

            # Marked Checkbox Item
            mark_item = QTableWidgetItem()
            mark_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            # Store link in item data for retrieval in handler
            mark_item.setData(Qt.UserRole, torrent_link)
            is_marked = torrent_link in self.marked_torrents
            mark_item.setCheckState(Qt.Checked if is_marked else Qt.Unchecked)
            self.results_table.setItem(row, self.mark_column_index, mark_item)

        # Re-enable updates and apply settings
        self.setUpdatesEnabled(True)
        self.results_table.resizeRowsToContents()
        # Apply initial row styles after populating
        for row in range(results_count):
            # Retrieve the check state from the created item
            mark_item = self.results_table.item(row, self.mark_column_index)
            if mark_item:
                is_marked = mark_item.checkState() == Qt.Checked
                self._apply_row_style(row, is_marked)

        # Only resize columns if needed (e.g., on first load or if content drastically changes)
        # self.results_table.resizeColumnsToContents() # Maybe only do this once initially

        # --- Update Sort Indicator ---
        self.results_table.horizontalHeader().setSortIndicator(
            self.current_sort_column, self.current_sort_order
        )
        self.results_table.horizontalHeader().setSortIndicatorShown(True)
        
        # Update pagination
        self.prev_button.setEnabled(self.current_page > 1)
        # Nyaa usually shows 75 results/page. Enable 'Next' if 75 results are shown.
        # Base 'Next' button enabling on the *original* count before filtering
        # This prevents disabling 'Next' just because filters removed items from this page.
        self.next_button.setEnabled(original_results_count >= 75)
        self.page_label.setText(f"Page {self.current_page}")
        # Update status message to reflect filtered count
        self.show_status_message(f"Displaying {results_count} results (filtered from {original_results_count}) for page {self.current_page}.", 5000)
        print("DEBUG: update_results_table finished.") # DEBUG


    def add_download(self, magnet_link, name):
        """Attempts to open the magnet link in the default torrent client."""
        if not magnet_link:
            self.show_error_message("No magnet link available for this item.")
            return

        print(f"Attempting to open magnet link for: {name}")
        # --- Restore original behaviour --- #
        self.show_status_message(f"Opening '{name[:50]}...' in default client...", 5000)

        try:
            opened = webbrowser.open(magnet_link)
            if not opened:
                self.show_status_message("Could not automatically open torrent client.", 8000)
                try:
                    pyperclip.copy(magnet_link)
                    QMessageBox.information(self, "Magnet Link Copied",
                                            "Could not automatically open your torrent client.\n"
                                            "The magnet link has been copied to your clipboard. Please paste it into your client manually.")
                except Exception as clip_err:
                    print(f"Clipboard error: {clip_err}")
                    QMessageBox.warning(self, "Manual Copy Needed",
                                          "Could not automatically open your torrent client or copy to clipboard.\n"
                                          f"Please copy the link manually:\n\n{magnet_link}",
                                          QMessageBox.Ok)
        except Exception as e:
            self.show_error_message(f"Error opening magnet link: {e}")
            QMessageBox.warning(self, "Error Opening Link",
                                  f"Could not open the magnet link in the default application.\nError: {e}\n\nLink: {magnet_link}")

    def show_details(self, link: str):
        """Initiates fetching and showing torrent details in a dialog."""
        if self.detail_worker and self.detail_worker.isRunning():
            self.show_status_message("Already fetching details...", 3000)
            return

        self.show_status_message(f"Fetching details...", 0) # Persistent message, less verbose

        # Abort previous detail worker if running (less likely but good practice)
        if self.detail_worker and self.detail_worker.isRunning():
             print("Terminating previous detail worker...")
             self.detail_worker.terminate()
             self.detail_worker.wait()
             print("Previous detail worker terminated.")
             
        # Prepare proxy config dictionary
        proxy_config = {
            'type': self.proxy_type,
            'host': self.proxy_host,
            'port': self.proxy_port,
            'username': self.proxy_username,
            'password': self.proxy_password
        }

        self.detail_worker = DetailScraperWorker(link, self.scraper_delay, self.network_timeout, proxy_config)
        self.detail_worker.details_ready.connect(self.display_detail_dialog)
        self.detail_worker.error_occurred.connect(self.show_detail_error)
        self.detail_worker.finished.connect(self._on_detail_worker_finished) # Cleanup connection        
        self.detail_worker.start()
        
    def _on_detail_worker_finished(self):
        print("Detail worker finished.")
        current_msg = self.status_bar.currentMessage()
        if current_msg.startswith("Fetching details"):
            self.status_bar.clearMessage()
        self.detail_worker = None # Release reference

    def display_detail_dialog(self, details: TorrentDetails):
        self.show_status_message(f"Details loaded for: {details.title[:50]}...", 5000)
        try:
            # Pass self (main window) as parent            
            dialog = TorrentDetailDialog(details, self)
            dialog.exec()
        except Exception as e:
            import traceback
            print(f"Error creating/showing details dialog: {e}")
            traceback.print_exc()
            self.show_error_message(f"Failed to display details dialog: {e}")

    def show_detail_error(self, message: str):
         self.show_error_message(f"Detail Error: {message}")

    # --- Pagination ---
    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.start_search() # Don't reset page here

    def next_page(self):
        self.current_page += 1
        self.start_search() # Don't reset page here

    # --- Sort Handling ---
    def handle_header_click(self, logicalIndex):
        new_sort_key = self.column_to_sort_key_map.get(logicalIndex)
        if not new_sort_key:
             # Allow clicking to remove sort indicator if clicked column is not sortable
             # self.results_table.horizontalHeader().setSortIndicatorShown(False)
             # Or just ignore the click on non-sortable columns
             print(f"Column {logicalIndex} is not sortable by Nyaa.")
             # Keep existing indicator shown
             self.results_table.horizontalHeader().setSortIndicatorShown(True)
             return

        # Determine new sort order
        if self.current_sort_column == logicalIndex:
            # Toggle order? Nyaa API might not support ascending easily.
            # Simplest: Keep descending when clicking same column again, or cycle back to default (date).
            # For now, let's just re-apply descending sort for the same column.
            new_order = Qt.DescendingOrder
        else:
            # Default to descending when clicking a new column
            new_order = Qt.DescendingOrder

        # Update internal state
        self.current_sort_column = logicalIndex
        self.current_sort_order = new_order
        self.current_sort_by = new_sort_key # Update the sort key string

        print(f"Sort changed via header click to: {self.current_sort_by} (Col: {self.current_sort_column}, Order: Desc)")

        # Update the dropdown to reflect the header click
        dropdown_index = self.sort_combo.findData(self.current_sort_by)
        if dropdown_index != -1:
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(dropdown_index)
            self.sort_combo.blockSignals(False)

        # Trigger search with new sort parameters
        self.start_search(reset_page=True)

    # --- Settings and Utils ---
    def select_download_directory(self):
        """Selects a directory for reference."""
        # Start browser from the currently saved path
        directory = QFileDialog.getExistingDirectory(self, "Select Client Download Reference Folder", self.saved_download_path)
        if directory:
            self.saved_download_path = os.path.abspath(directory)
            # Update the label in the SettingsWidget
            if hasattr(self, 'settings_widget'):
                self.settings_widget.update_download_dir_label(self.saved_download_path)
            # Save settings (could also rely on settings_widget signal)
            self._save_settings_from_widget() # Use helper to get latest
            self.show_status_message(f"Client download folder reference updated.", 5000)

    def show_status_message(self, message, timeout=5000):
        """Safely displays message in the status bar."""
        if self.status_bar:
            self.status_bar.showMessage(message, timeout)
        else:
            print(f"Status: {message}")

    def show_error_message(self, message):
        """Displays errors in the status bar and optionally a dialog."""
        print(f"DEBUG: show_error_message called with: {message}") # DEBUG
        print(f"ERROR: {message}")
        self.show_status_message(f"Error: {message}", 10000)

        # Optional: Show critical errors in a popup
        # Only show popup for significant errors that might prevent functionality
        keywords = ["cloudflare", "parse", "connect", "timeout", "failed", "unexpected", "http error", "not found"]
        is_critical = any(keyword in message.lower() for keyword in keywords)
        # Avoid popups for simple "No results found" or less critical detail errors unless explicitly severe
        is_detail_error = message.startswith("Detail Error:")
        if is_critical and not (is_detail_error and "not found" not in message.lower()):
             # Prevent multiple popups in quick succession if needed
             QMessageBox.warning(self, "Application Error", message)


    def get_settings_path(self):
        """Gets the path for the settings file using platform-specific locations."""
        if sys.platform == "win32":
            base_path = os.getenv('LOCALAPPDATA')
        elif sys.platform == "darwin": # macOS
            base_path = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        else: # Linux/Other
            base_path = os.getenv('XDG_CONFIG_HOME', os.path.join(os.path.expanduser("~"), ".config"))

        app_data_path = os.path.join(base_path, self.APP_NAME)
        os.makedirs(app_data_path, exist_ok=True)
        return os.path.join(app_data_path, self.SETTINGS_FILE_NAME)

    def save_settings(self):
        """Saves current settings to a JSON file."""
        settings_data = {
            "version": 1, # Add a version number for future migrations
            "default_download_path": self.saved_download_path,
            "search_history": self.search_history,
            "scraper_delay": self.scraper_delay,
            "max_history_items": self.max_history_items,
            "network_timeout": self.network_timeout,
            # Add Proxy Settings
            "proxy_type": self.proxy_type,
            "proxy_host": self.proxy_host,
            "proxy_port": self.proxy_port,
            "proxy_username": self.proxy_username,
            "proxy_password": self.proxy_password, # WARNING: Stored in plain text
            "marked_torrents": list(self.marked_torrents), # Add marked torrents (convert set to list)
            "filter_trusted_only": self.filter_trusted_only, # Save trusted filter state
            "filter_uploader": self.filter_uploader, # Save uploader filter state
            # "current_results": self.current_results, # Don't save results to settings
        }

        # --- Fetch settings from SettingsWidget before saving --- #
        if hasattr(self, 'settings_widget'):
            widget_settings = self.settings_widget.get_current_settings()
            # Only update keys managed by the widget
            keys_to_update = [
                "scraper_delay", "network_timeout", "max_history_items",
                "proxy_type",
                "proxy_host", "proxy_port", "proxy_username", "proxy_password",
                "default_download_path" # Widget keeps track of this now
            ]
            for key in keys_to_update:
                if key in widget_settings:
                    settings_data[key] = widget_settings[key]
        else:
            print("Warning: SettingsWidget not found during save_settings.")

        # --- Save Header State ---
        if hasattr(self, 'results_table'):
            try:
                header_state = self.results_table.horizontalHeader().saveState().toBase64().data().decode('ascii')
                settings_data["table_header_state"] = header_state
            except Exception as e:
                 print(f"Warning: Could not save table header state: {e}")
        else:
             print("Warning: results_table not found during save_settings.")

        path = self.get_settings_path()
        try:
            # Save the rest of the settings to JSON
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=4)
            print(f"Settings saved to {path}")
        except IOError as e:
            self.show_error_message(f"Could not save settings to {path}: {e}")
        except Exception as e:
            self.show_error_message(f"Unexpected error saving settings: {e}")


    def load_settings(self):
        """Loads settings from the JSON file and applies them."""
        print("Loading settings...")
        path = self.get_settings_path()

        # Establish defaults
        default_path = os.path.expanduser("~")
        default_history = []
        default_delay = self.DEFAULT_SCRAPER_DELAY
        default_max_history = 25
        default_timeout = 30
        # Proxy Defaults
        default_proxy_type = "none"
        default_proxy_host = ""
        default_proxy_port = ""
        default_proxy_user = ""
        default_proxy_pass = ""
        # Marked Torrents Default
        default_marked_torrents = set()
        default_trusted_only = False
        default_uploader = ""

        # Initialize loaded vars to defaults
        loaded_path = default_path
        loaded_history = default_history
        loaded_delay = default_delay
        loaded_max_history = default_max_history
        loaded_network_timeout = default_timeout
        loaded_proxy_type = default_proxy_type
        loaded_proxy_host = default_proxy_host
        loaded_proxy_port = default_proxy_port
        loaded_proxy_user = default_proxy_user
        loaded_proxy_pass = default_proxy_pass
        loaded_marked_torrents = default_marked_torrents
        loaded_trusted_only = default_trusted_only
        loaded_uploader = default_uploader
        loaded_header_state = None # Default for header state

        if not os.path.exists(path):
            print(f"Settings file not found at {path}. Using defaults.")
            # Apply defaults directly
            self.saved_download_path = default_path
            self.search_history = default_history
            self.scraper_delay = default_delay
            self.max_history_items = default_max_history
            self.network_timeout = default_timeout
            self.proxy_type = default_proxy_type
            self.proxy_host = default_proxy_host
            self.proxy_port = default_proxy_port
            self.proxy_username = default_proxy_user
            self.proxy_password = default_proxy_pass
            self.marked_torrents = default_marked_torrents
            self.filter_trusted_only = default_trusted_only
            self.filter_uploader = default_uploader
            # No header state to restore

            # Apply to UI (call the update UI part)
            self._update_settings_ui()

            # Save the defaults for next time
            self.save_settings()
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)

            # --- Load individual settings safely --- #
            # Basic settings first
            loaded_path = settings_data.get("default_download_path", default_path)
            if not isinstance(loaded_path, str): loaded_path = default_path

            temp_delay = settings_data.get("scraper_delay", default_delay)
            if isinstance(temp_delay, int) and 5 <= temp_delay <= 60:
                loaded_delay = temp_delay
            else:
                loaded_delay = default_delay

            temp_timeout = settings_data.get("network_timeout", default_timeout)
            if isinstance(temp_timeout, int) and 10 <= temp_timeout <= 120:
                loaded_network_timeout = temp_timeout
            else:
                loaded_network_timeout = default_timeout

            # Load max history first
            temp_max_hist = settings_data.get("max_history_items", default_max_history)
            if isinstance(temp_max_hist, int) and 5 <= temp_max_hist <= 100:
                loaded_max_history = temp_max_hist
            else:
                print(f"Warning: Invalid max_history_items value '{temp_max_hist}' in settings. Using default.")
                loaded_max_history = default_max_history

            # Load history safely and apply limit
            temp_history = settings_data.get("search_history", default_history)
            if isinstance(temp_history, list):
                loaded_history = [str(item) for item in temp_history if isinstance(item, str)]
                loaded_history = loaded_history[:loaded_max_history] # Apply limit
            else:
                print("Warning: Invalid search_history format in settings file. Using default.")
                loaded_history = default_history

            # Load Proxy settings
            loaded_proxy_type = settings_data.get("proxy_type", default_proxy_type)
            if loaded_proxy_type not in ["none", "http", "socks5"]: loaded_proxy_type = default_proxy_type

            loaded_proxy_host = settings_data.get("proxy_host", default_proxy_host)
            if not isinstance(loaded_proxy_host, str): loaded_proxy_host = default_proxy_host

            loaded_proxy_port = settings_data.get("proxy_port", default_proxy_port)
            if not isinstance(loaded_proxy_port, str): loaded_proxy_port = default_proxy_port

            loaded_proxy_user = settings_data.get("proxy_username", default_proxy_user)
            if not isinstance(loaded_proxy_user, str): loaded_proxy_user = default_proxy_user

            loaded_proxy_pass = settings_data.get("proxy_password", default_proxy_pass)
            if not isinstance(loaded_proxy_pass, str): loaded_proxy_pass = default_proxy_pass

            # Load marked torrents safely
            temp_marked = settings_data.get("marked_torrents", [])
            if isinstance(temp_marked, list):
                loaded_marked_torrents = {str(item) for item in temp_marked if isinstance(item, str)}
            else:
                print("Warning: Invalid marked_torrents format in settings. Using default.")
                loaded_marked_torrents = default_marked_torrents

            # Load trusted filter state
            loaded_trusted_only = settings_data.get("filter_trusted_only", default_trusted_only)
            if not isinstance(loaded_trusted_only, bool):
                print(f"Warning: Invalid filter_trusted_only value '{loaded_trusted_only}' in settings. Using default.")
                loaded_trusted_only = default_trusted_only

            # Load uploader filter
            loaded_uploader = settings_data.get("filter_uploader", default_uploader)
            if not isinstance(loaded_uploader, str):
                print(f"Warning: Invalid filter_uploader value '{loaded_uploader}' in settings. Using default.")
                loaded_uploader = default_uploader

            # --- Load Header State --- #
            header_state_base64 = settings_data.get("table_header_state")
            if isinstance(header_state_base64, str):
                try:
                    # Decode from base64 before restoring
                    loaded_header_state = QByteArray.fromBase64(header_state_base64.encode('ascii'))
                except Exception as e:
                    print(f"Warning: Could not decode table_header_state from settings: {e}")
                    loaded_header_state = None # Fallback if decoding fails
            else:
                 if header_state_base64 is not None:
                      print("Warning: table_header_state is not a string in settings. Ignoring.")
                 loaded_header_state = None # Use default if missing or wrong type

        except json.JSONDecodeError as e:
            print(f"ERROR parsing settings file ({path}): {e}. Using defaults.")
            # Set all loaded vars to defaults here...
            loaded_path = default_path
            loaded_history = default_history
            loaded_delay = default_delay
            loaded_max_history = default_max_history
            loaded_network_timeout = default_timeout
            loaded_proxy_type = default_proxy_type
            loaded_proxy_host = default_proxy_host
            loaded_proxy_port = default_proxy_port
            loaded_proxy_user = default_proxy_user
            loaded_proxy_pass = default_proxy_pass
            loaded_marked_torrents = default_marked_torrents
            loaded_trusted_only = default_trusted_only
            loaded_uploader = default_uploader
            loaded_header_state = None

        except Exception as e:
            print(f"ERROR loading settings ({path}): {type(e).__name__} - {e}. Using defaults.")
            # Set all loaded vars to defaults here...
            loaded_path = default_path
            loaded_history = default_history
            loaded_delay = default_delay
            loaded_max_history = default_max_history
            loaded_network_timeout = default_timeout
            loaded_proxy_type = default_proxy_type
            loaded_proxy_host = default_proxy_host
            loaded_proxy_port = default_proxy_port
            loaded_proxy_user = default_proxy_user
            loaded_proxy_pass = default_proxy_pass
            loaded_marked_torrents = default_marked_torrents
            loaded_trusted_only = default_trusted_only
            loaded_uploader = default_uploader
            loaded_header_state = None

        # Apply loaded (or default) settings to state variables
        self.saved_download_path = loaded_path
        self.max_history_items = loaded_max_history # Apply before trimming history
        self.search_history = loaded_history # Already trimmed during load
        self.scraper_delay = loaded_delay
        self.network_timeout = loaded_network_timeout
        self.proxy_type = loaded_proxy_type
        self.proxy_host = loaded_proxy_host
        self.proxy_port = loaded_proxy_port
        self.proxy_username = loaded_proxy_user
        self.proxy_password = loaded_proxy_pass
        self.marked_torrents = loaded_marked_torrents
        self.filter_trusted_only = loaded_trusted_only
        self.filter_uploader = loaded_uploader

        # Update UI elements *after* internal state is set
        self._update_settings_ui()

        # --- Restore Header State (after UI is potentially updated) ---
        if loaded_header_state and hasattr(self, 'results_table'):
             try:
                 if not self.results_table.horizontalHeader().restoreState(loaded_header_state):
                     print("Warning: Failed to restore table header state (may be invalid or incompatible).")
                 else:
                     print("Successfully restored table header state.")
             except Exception as e:
                 print(f"Error restoring table header state: {e}")
        else:
             print("No valid table header state found in settings to restore.")

        print("Settings loaded and applied.")

    def _update_settings_ui(self):
        """Updates UI elements in MainWindow based on current state variables.
           (Most UI updates are now handled within SettingsWidget)
        """
        self._update_history_combo()
        self._update_quick_filter_ui()

    def _update_quick_filter_ui(self):
         """Updates the uploader input and trusted checkbox state."""
         self.uploader_filter_input.blockSignals(True)
         self.uploader_filter_input.setText(self.filter_uploader)
         self.uploader_filter_input.blockSignals(False)
         self.trusted_checkbox.blockSignals(True)
         self.trusted_checkbox.setChecked(self.filter_trusted_only)
         self.trusted_checkbox.blockSignals(False)

    def closeEvent(self, event):
        """Saves settings and cleans up on exit."""
        print(f"{self.APP_NAME} shutting down...")
        # Abort any running workers
        if self.scraper_worker and self.scraper_worker.isRunning():
            print("Terminating active search worker...")
            self.scraper_worker.terminate()
            self.scraper_worker.wait(1000) # Wait max 1 sec
        if self.detail_worker and self.detail_worker.isRunning():
            print("Terminating active detail worker...")
            self.detail_worker.terminate()
            self.detail_worker.wait(1000)

        self.save_settings()
        print("Settings saved. Goodbye!")
        event.accept()

    # Method to be called by the timer
    def _trigger_initial_search(self):
        print("DEBUG: _trigger_initial_search called by timer.")
        self.start_search(reset_page=True)

    # --- Helper to create separators --- #
    def _create_separator(self) -> QFrame:
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        # Optional: Adjust margin/styling via QSS if needed later
        # separator.setStyleSheet("margin-top: 5px; margin-bottom: 5px;")
        return separator

    def _reset_settings_to_defaults(self):
        """Resets all application settings to their original values."""
        reply = QMessageBox.question(self, "Reset Settings?",
                                     "Are you sure you want to reset all application settings to their defaults?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            self.show_status_message("Reset settings cancelled.", 3000)
            return

        print("Resetting all settings to defaults...")
        # Reset state variables to defaults
        self.saved_download_path = os.path.expanduser("~")
        self.search_history = []
        self.scraper_delay = self.DEFAULT_SCRAPER_DELAY
        self.max_history_items = 25
        self.network_timeout = 30
        self.proxy_type = "none"
        self.proxy_host = ""
        self.proxy_port = ""
        self.proxy_username = ""
        self.proxy_password = ""
        self.marked_torrents = set()
        self.filter_trusted_only = False
        self.filter_uploader = ""

        # Apply defaults to UI
        self._update_settings_ui()

        # Save the reset settings
        self.save_settings()

        self.show_status_message("All settings reset to defaults.", 5000)

    # --- Helper to save settings using widget data ---
    def _save_settings_from_widget(self):
        """Gets current settings from widget and saves everything."""
        # Ensure internal state matches widget before saving
        if hasattr(self, 'settings_widget'):
            widget_settings = self.settings_widget.get_current_settings()
            self._update_state_from_settings_dict(widget_settings)
        self.save_settings() # Now call the original save method

    # --- Slots for SettingsWidget signals ---
    def _handle_settings_widget_change(self, new_settings: dict):
        """Handles the generic settings_changed signal from SettingsWidget."""
        print("MainWindow received settings_changed signal.")
        self._update_state_from_settings_dict(new_settings)
        # Save all settings whenever any setting managed by the widget changes
        self.save_settings()

    def _handle_proxy_config_change(self, proxy_settings: dict):
        """Updates proxy state variables based on signal from SettingsWidget."""
        print("MainWindow received proxy_config_changed signal.")
        self.proxy_type = proxy_settings.get("proxy_type", SettingsWidget.DEFAULT_PROXY_TYPE)
        self.proxy_host = proxy_settings.get("proxy_host", "")
        self.proxy_port = proxy_settings.get("proxy_port", "")
        self.proxy_username = proxy_settings.get("proxy_username", "")
        self.proxy_password = proxy_settings.get("proxy_password", "")
        # No need to save here, _handle_settings_widget_change handles saving

    def _update_state_from_settings_dict(self, settings_dict: dict):
        """Updates MainWindow's internal state variables from a settings dictionary."""
        # Update only the relevant MainWindow state variables
        self.scraper_delay = settings_dict.get("scraper_delay", self.scraper_delay)
        self.network_timeout = settings_dict.get("network_timeout", self.network_timeout)
        self.max_history_items = settings_dict.get("max_history_items", self.max_history_items)
        self.saved_download_path = settings_dict.get("default_download_path", self.saved_download_path)
        # Proxy settings are updated via _handle_proxy_config_change if needed separately,
        # but they are also in the main dict, so update here too for simplicity.
        self.proxy_type = settings_dict.get("proxy_type", self.proxy_type)
        self.proxy_host = settings_dict.get("proxy_host", self.proxy_host)
        self.proxy_port = settings_dict.get("proxy_port", self.proxy_port)
        self.proxy_username = settings_dict.get("proxy_username", self.proxy_username)
        self.proxy_password = settings_dict.get("proxy_password", self.proxy_password)

        # Trim history if max items changed
        if len(self.search_history) > self.max_history_items:
             self.search_history = self.search_history[:self.max_history_items]
             self._update_history_combo()
        
        # Re-apply defaults to main search UI in case they changed
        self._apply_main_search_defaults()


    # --- Item Changed Handling ---
    def _handle_item_marked_state_changed(self, item: QTableWidgetItem):
        """Handles the check state change for the 'Mark' column."""
        if item.column() != self.mark_column_index:
            return # Only handle changes in the mark column

        row_index = item.row()
        is_checked = item.checkState() == Qt.Checked
        torrent_link = item.data(Qt.UserRole) # Retrieve the stored link

        if not torrent_link:
            print(f"Warning: No torrent link found for item at row {row_index}")
            return

        # Prevent signal loops if style changes trigger this handler
        self.results_table.blockSignals(True)

        print(f"Mark state changed for {torrent_link}: {is_checked}")
        if is_checked:
            self.marked_torrents.add(torrent_link)
        else:
            self.marked_torrents.discard(torrent_link) # Use discard to avoid error if not present

        self._apply_row_style(row_index, is_checked)

        # Unblock signals and save
        self.results_table.blockSignals(False)
        self.save_settings()

    # --- Mark As Handling ---
    def _apply_row_style(self, row_index, is_marked):
        """Applies or removes visual styling for a marked row."""
        font = self.results_table.font() # Get default font
        font.setStrikeOut(is_marked)
        # Dim color slightly if marked
        text_color = QColor(Qt.gray) if is_marked else self.results_table.palette().color(QPalette.Text)

        # Iterate through all columns *except* the checkbox column itself
        for col_index in range(self.results_table.columnCount()):
            if col_index == self.mark_column_index:
                continue
            item = self.results_table.item(row_index, col_index)
            if item:
                item.setFont(font)
                item.setForeground(text_color)
            # Apply to cell widget in Actions column too
            elif col_index == 8: # Actions column index
                widget = self.results_table.cellWidget(row_index, col_index)
                if widget:
                    # Might need to iterate through buttons if more complex styling needed
                    widget.setEnabled(not is_marked)

    # --- Filter Dialog Handling --- #
    def _show_filter_dialog(self):
        # Set current filters in the dialog before showing
        current_filters = {
            "min_seeders": self.min_seeders,
            "min_size_bytes": self.min_size_bytes,
            "max_size_bytes": self.max_size_bytes
        }
        self.filter_dialog.set_filters(current_filters)
        self.filter_dialog.show() # Show non-modally
        self.filter_dialog.raise_() # Bring to front
        self.filter_dialog.activateWindow()

    def _apply_filters_from_dialog(self, filters: dict):
        changed = False
        if filters.get("min_seeders", 0) != self.min_seeders:
            self.min_seeders = filters.get("min_seeders", 0)
            changed = True
        if filters.get("min_size_bytes", 0) != self.min_size_bytes:
            self.min_size_bytes = filters.get("min_size_bytes", 0)
            changed = True
        if filters.get("max_size_bytes", 0) != self.max_size_bytes:
            self.max_size_bytes = filters.get("max_size_bytes", 0)
            changed = True

        self._update_filter_button_style() # Update button appearance

        if changed:
            print(f"Filters applied from dialog: Min Seeders={self.min_seeders}, Min Size={self.min_size_bytes}, Max Size={self.max_size_bytes}")
            # Trigger a new search if filters changed
            self.start_search(reset_page=True)
        else:
            print("Filters applied, but no change detected.")

    def _clear_filters_from_dialog(self):
        changed = self.min_seeders != 0 or self.min_size_bytes != 0 or self.max_size_bytes != 0
        self.min_seeders = 0
        self.min_size_bytes = 0
        self.max_size_bytes = 0
        self._update_filter_button_style() # Update button appearance

        if changed:
            print("Filters cleared from dialog.")
            # Trigger a new search if filters were cleared
            self.start_search(reset_page=True)
        else:
            print("Filters cleared, but none were active.")

    def _update_filter_button_style(self):
        """Updates the Filters button style and text to indicate if filters are active."""
        active_filters = []
        tooltip_parts = ["Set additional search filters."] # Base tooltip

        if self.min_seeders > 0:
            active_filters.append("Seeders")
            tooltip_parts.append(f"Min Seeders: {self.min_seeders}")
        if self.min_size_bytes > 0:
            active_filters.append("Min Size")
            tooltip_parts.append(f"Min Size: {format_size(self.min_size_bytes)}") # Use format_size helper
        if self.max_size_bytes > 0:
            active_filters.append("Max Size")
            tooltip_parts.append(f"Max Size: {format_size(self.max_size_bytes)}")

        if active_filters:
            # Update button text and tooltip
            active_text = ", ".join(active_filters)
            self.filters_button.setText(f"Filters ({active_text})")
            if len(tooltip_parts) > 1:
                tooltip_parts.pop(0) # Remove base tooltip text
            self.filters_button.setToolTip("\n".join(tooltip_parts))
            # Apply active style (e.g., change background, border, or icon color)
            # Using setProperty for QSS targeting
            self.filters_button.setProperty("active", True)
        else:
            # Apply inactive/default style
            self.filters_button.setText("Filters")
            self.filters_button.setToolTip("Set additional search filters (size, seeders, etc.)")
            self.filters_button.setProperty("active", False)

        # Re-polish the widget to apply QSS changes based on the property
        self.filters_button.style().unpolish(self.filters_button)
        self.filters_button.style().polish(self.filters_button)

    # --- Filter State Handlers --- #
    def _on_trusted_filter_changed(self, state): # state is Qt.CheckState enum
        """Handles changes to the 'Trusted Only' checkbox state."""
        is_checked = (state == Qt.Checked)
        if is_checked != self.filter_trusted_only:
            print(f"Trusted filter changed to: {is_checked}")
            self.filter_trusted_only = is_checked
            self.save_settings() # Save setting immediately
            # Trigger search immediately when the filter is toggled
            self.start_search(reset_page=True)

    def _on_uploader_filter_changed(self, text): # state is Qt.CheckState enum
        """Handles changes to the uploader filter input."""
        uploader = text.strip()
        if uploader != self.filter_uploader:
            print(f"Uploader filter changed to: '{uploader}'")
            self.filter_uploader = uploader
            # Consider saving immediately or only when search is triggered?
            # Let's save immediately for now.
            self.save_settings()
            # Don't trigger search on every keystroke, only on Enter (connected above)

    # --- Clear Search History ---
    def _clear_search_history(self):
        """Clears the search history after confirmation."""
        reply = QMessageBox.question(self, "Clear History?",
                                     "Are you sure you want to clear your search history?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.search_history = []
            self._update_history_combo() # Update dropdown UI
            self.save_settings() # Persist the empty list
            self.show_status_message("Search history cleared.", 3000)
        else:
            self.show_status_message("Clear history cancelled.", 3000)

    # --- Table Context Menu --- #
    def _show_table_context_menu(self, position): # position is a QPoint
        """Creates and shows the context menu for the results table."""
        selected_data = self._get_all_selected_row_data()
        num_selected = len(selected_data)

        if num_selected == 0:
            return # Don't show menu if no rows are selected

        menu = QMenu(self)

        if num_selected == 1:
            # --- Single Item Actions ---
            row_index, result_data = selected_data[0]

            open_details_action = QAction(qta.icon('mdi.information-outline'), f"View Details...", self)
            open_details_action.triggered.connect(lambda checked=False, r=row_index: self._open_details_selected_from_context(r))
            open_details_action.setEnabled(bool(result_data.link and result_data.link != '#'))
            menu.addAction(open_details_action)
            menu.addSeparator()

            copy_name_action = QAction(qta.icon('mdi.content-copy'), f"Copy Name: {result_data.name[:30]}...", self)
            copy_name_action.triggered.connect(lambda checked=False, r=row_index: self._copy_name(r))
            menu.addAction(copy_name_action)

            copy_magnet_action = QAction(qta.icon('mdi.magnet'), "Copy Magnet Link", self)
            copy_magnet_action.triggered.connect(lambda checked=False, r=row_index: self._copy_magnet_link(r))
            copy_magnet_action.setEnabled(bool(result_data.magnet_link))
            menu.addAction(copy_magnet_action)

            copy_details_action = QAction(qta.icon('mdi.link-variant'), "Copy Details Link", self)
            copy_details_action.triggered.connect(lambda checked=False, r=row_index: self._copy_details_link(r))
            copy_details_action.setEnabled(bool(result_data.link and result_data.link != '#'))
            menu.addAction(copy_details_action)

            menu.addSeparator()

            mark_item = self.results_table.item(row_index, self.mark_column_index)
            is_marked = mark_item.checkState() == Qt.Checked if mark_item else False
            mark_action_text = "Unmark Torrent" if is_marked else "Mark Torrent"
            mark_action_icon = qta.icon('mdi.close-box-outline') if is_marked else qta.icon('mdi.checkbox-marked-outline')
            toggle_mark_action = QAction(mark_action_icon, mark_action_text, self)
            toggle_mark_action.triggered.connect(lambda checked=False, r=row_index: self._toggle_mark_row(r))
            toggle_mark_action.setEnabled(mark_item is not None) # Only enable if item exists
            menu.addAction(toggle_mark_action)

        else: # num_selected > 1
            # --- Bulk Actions --- #            
            menu.addAction(f"{num_selected} items selected")
            menu.addSeparator()

            # Bulk Mark/Unmark
            mark_selected_action = QAction(qta.icon('mdi.checkbox-marked-outline'), f"Mark Selected ({num_selected})", self)
            mark_selected_action.triggered.connect(self._mark_selected_rows)
            menu.addAction(mark_selected_action)
            unmark_selected_action = QAction(qta.icon('mdi.close-box-outline'), f"Unmark Selected ({num_selected})", self)
            unmark_selected_action.triggered.connect(self._unmark_selected_rows)
            menu.addAction(unmark_selected_action)

            menu.addSeparator()

            # Bulk Copy
            copy_magnets_action = QAction(qta.icon('mdi.magnet'), f"Copy Magnet Links ({num_selected})", self)
            copy_magnets_action.triggered.connect(self._copy_selected_magnet_links)
            # Enable if at least one selected has a magnet link?
            copy_magnets_action.setEnabled(any(res.magnet_link for _, res in selected_data))
            menu.addAction(copy_magnets_action)

            copy_details_links_action = QAction(qta.icon('mdi.link-variant'), f"Copy Details Links ({num_selected})", self)
            copy_details_links_action.triggered.connect(self._copy_selected_detail_links)
            copy_details_links_action.setEnabled(any(res.link and res.link != '#' for _, res in selected_data))
            menu.addAction(copy_details_links_action)

            copy_names_action = QAction(qta.icon('mdi.content-copy'), f"Copy Names ({num_selected})", self)
            copy_names_action.triggered.connect(self._copy_selected_names)
            menu.addAction(copy_names_action)

        # --- Show Menu --- #
        # Map the local position to global screen position
        global_pos = self.results_table.viewport().mapToGlobal(position)
        menu.exec(global_pos)

    # --- Single Row Context Menu Actions --- #
    def _open_details_selected_from_context(self, row_index):
        """Opens details based on the VISIBLE row index from context menu."""
        # We have the direct row index, get the data using the helper
        mark_item = self.results_table.item(row_index, self.mark_column_index)
        if mark_item:
            original_index = mark_item.data(Qt.UserRole + 1)
            if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                result_data = self.unfiltered_page_results[original_index]
                if result_data and result_data.link and result_data.link != '#':
                    self.show_details(result_data.link)
                    return
        self.show_error_message("Could not retrieve details link for the selected row.")

    def _copy_name(self, row_index):
        """Copies name based on the VISIBLE row index from context menu."""
        mark_item = self.results_table.item(row_index, self.mark_column_index)
        if mark_item:
            original_index = mark_item.data(Qt.UserRole + 1)
            if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                result_data = self.unfiltered_page_results[original_index]
                if result_data:
                    try:
                        pyperclip.copy(result_data.name)
                        self.show_status_message(f"Copied name: {result_data.name[:50]}...", 3000)
                    except Exception as e:
                        print(f"Clipboard Error (Name Context): {e}")
                        self.show_error_message("Failed to copy name to clipboard.")
                    return
        self.show_error_message("Could not retrieve name for the selected row.")

    def _copy_magnet_link(self, row_index):
        """Copies magnet link based on the VISIBLE row index from context menu."""
        mark_item = self.results_table.item(row_index, self.mark_column_index)
        if mark_item:
            original_index = mark_item.data(Qt.UserRole + 1)
            if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                result_data = self.unfiltered_page_results[original_index]
                if result_data and result_data.magnet_link:
                    try:
                        pyperclip.copy(result_data.magnet_link)
                        self.show_status_message("Copied magnet link.", 3000)
                    except Exception as e:
                        print(f"Clipboard Error (Magnet Context): {e}")
                        self.show_error_message("Failed to copy magnet link to clipboard.")
                    return
        self.show_error_message("Could not retrieve magnet link for the selected row.")

    def _copy_details_link(self, row_index):
        """Copies details link based on the VISIBLE row index from context menu."""
        mark_item = self.results_table.item(row_index, self.mark_column_index)
        if mark_item:
            original_index = mark_item.data(Qt.UserRole + 1)
            if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                result_data = self.unfiltered_page_results[original_index]
                if result_data and result_data.link and result_data.link != '#':
                    try:
                        pyperclip.copy(result_data.link)
                        self.show_status_message(f"Copied details link.", 3000)
                    except Exception as e:
                        print(f"Clipboard Error (Details Context): {e}")
                        self.show_error_message("Failed to copy details link to clipboard.")
                    return
        self.show_error_message("Could not retrieve details link for the selected row.")

    def _toggle_mark_row(self, row_index):
        """Toggles the check state of the mark checkbox for the given VISIBLE row index."""
        mark_item = self.results_table.item(row_index, self.mark_column_index)
        if mark_item:
            current_state = mark_item.checkState()
            new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
            mark_item.setCheckState(new_state)
            # The itemChanged signal connected earlier will handle saving state and applying style
        else:
            print(f"Warning: Could not find mark item for row {row_index} to toggle.")

    # --- Bulk Action Handlers --- #
    def _mark_selected_rows(self, mark_state=Qt.Checked):
        """Sets the mark state for all selected rows."""
        selected_data = self._get_all_selected_row_data()
        if not selected_data:
            return
        
        print(f"Setting mark state to {mark_state} for {len(selected_data)} rows.")
        self.results_table.blockSignals(True)
        changed_links = set()
        for row_index, result_data in selected_data:
            mark_item = self.results_table.item(row_index, self.mark_column_index)
            if mark_item and mark_item.checkState() != mark_state:
                mark_item.setCheckState(mark_state)
                torrent_link = result_data.link
                if torrent_link:
                    if mark_state == Qt.Checked:
                        self.marked_torrents.add(torrent_link)
                    else:
                        self.marked_torrents.discard(torrent_link)
                    changed_links.add(torrent_link)
                self._apply_row_style(row_index, mark_state == Qt.Checked)

        self.results_table.blockSignals(False)
        if changed_links:
            self.save_settings() # Save if any state actually changed
        action = "Marked" if mark_state == Qt.Checked else "Unmarked"
        self.show_status_message(f"{action} {len(changed_links)} selected torrents.", 3000)

    def _unmark_selected_rows(self):
        self._mark_selected_rows(mark_state=Qt.Unchecked)

    def _copy_selected_magnet_links(self):
        selected_data = self._get_all_selected_row_data()
        magnets = [res.magnet_link for _, res in selected_data if res.magnet_link]
        if magnets:
            try:
                pyperclip.copy("\n".join(magnets))
                self.show_status_message(f"Copied {len(magnets)} magnet links.", 3000)
            except Exception as e:
                print(f"Clipboard Error (Bulk Magnets): {e}")
                self.show_error_message("Failed to copy magnet links to clipboard.")
        else:
            self.show_status_message("No valid magnet links found in selection.", 3000)

    def _copy_selected_detail_links(self):
        selected_data = self._get_all_selected_row_data()
        links = [res.link for _, res in selected_data if res.link and res.link != '#']
        if links:
            try:
                pyperclip.copy("\n".join(links))
                self.show_status_message(f"Copied {len(links)} detail links.", 3000)
            except Exception as e:
                print(f"Clipboard Error (Bulk Details): {e}")
                self.show_error_message("Failed to copy detail links to clipboard.")
        else:
            self.show_status_message("No valid detail links found in selection.", 3000)

    def _copy_selected_names(self):
        selected_data = self._get_all_selected_row_data()
        names = [res.name for _, res in selected_data]
        if names:
            try:
                pyperclip.copy("\n".join(names))
                self.show_status_message(f"Copied {len(names)} names.", 3000)
            except Exception as e:
                print(f"Clipboard Error (Bulk Names): {e}")
                self.show_error_message("Failed to copy names to clipboard.")
        else:
            self.show_status_message("No items selected.", 3000)

    # --- Live Filtering Method --- #
    def _apply_row_visibility_filters(self):
        """Hides/shows rows based on current filter criteria (name, size, seeders)."""
        if not hasattr(self, 'results_table') or not hasattr(self, 'unfiltered_page_results'):
            print("DEBUG: Filter called before table/results ready.")
            return # Table not ready

        name_filter = self.search_input.text().lower().strip()
        min_seeders = self.min_seeders
        min_size = self.min_size_bytes
        max_size = self.max_size_bytes

        visible_count = 0
        self.results_table.setUpdatesEnabled(False) # Performance boost

        for row_index in range(self.results_table.rowCount()):
            # Check if the unfiltered results list has this index
            if row_index >= len(self.unfiltered_page_results):
                # This case shouldn't happen if population is correct, but good to guard
                self.results_table.setRowHidden(row_index, True)
                continue

            result = self.unfiltered_page_results[row_index]

            # Apply filters
            name_match = (not name_filter) or (name_filter in result.name.lower())
            seeder_match = result.seeders >= min_seeders
            min_size_match = result.size_bytes >= min_size
            max_size_match = max_size <= 0 or result.size_bytes <= max_size

            is_visible = name_match and seeder_match and min_size_match and max_size_match

            self.results_table.setRowHidden(row_index, not is_visible)
            if is_visible:
                visible_count += 1

        self.results_table.setUpdatesEnabled(True)
        print(f"DEBUG: Live filter applied. Visible rows: {visible_count}")

        # Optional: Update status bar?
        # Might be too noisy to update on every keystroke.
        # Consider updating only after a short delay (using QTimer) if desired.
        # self.show_status_message(f"{visible_count} results shown after filtering.", 2000)

    # --- Header Context Menu Logic --- #
    def _show_header_context_menu(self, position): # position is a QPoint relative to header
        """Creates and shows the context menu for the table header to show/hide columns."""
        header = self.results_table.horizontalHeader()
        menu = QMenu(self)

        # Keep track of non-hidden columns to prevent hiding the last one
        visible_columns = [i for i in range(header.count()) if not header.isSectionHidden(i)]
        can_hide = len(visible_columns) > 1 # Can hide if more than one column is visible

        for logical_index in range(header.count()):
            action_text = self.results_table.horizontalHeaderItem(logical_index).text()
            action = QAction(action_text, self, checkable=True)
            action.setChecked(not header.isSectionHidden(logical_index))

            # Prevent hiding the last visible column
            if not action.isChecked() and not can_hide:
                action.setEnabled(False)
            
            # Prevent hiding essential columns (optional - e.g., Name and Actions)
            # Let's allow hiding all for now, simplicity first
            # if logical_index in [2, 8]: # Example: Name and Actions
            #    action.setEnabled(False)
            #    action.setToolTip("This column cannot be hidden.")

            action.toggled.connect(lambda checked, idx=logical_index: self._toggle_column_visibility(checked, idx))
            menu.addAction(action)

        # Show the menu at the global position
        global_pos = header.mapToGlobal(position)
        menu.exec(global_pos)

    def _toggle_column_visibility(self, is_visible, logical_index):
        """Slot to handle toggling column visibility from the header context menu."""
        print(f"Toggling column {logical_index} visibility to {is_visible}")
        self.results_table.setColumnHidden(logical_index, not is_visible)
        # No need to save settings here, we'll save the header state on close

    # --- Setup Shortcuts --- #
    def _setup_shortcuts(self):
        """Creates global keyboard shortcuts."""
        # Focus Search
        focus_search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        focus_search_shortcut.activated.connect(self.search_input.setFocus)
        print("Shortcut Ctrl+F -> Focus Search registered.")

        # Pagination
        prev_page_shortcut1 = QShortcut(QKeySequence("Ctrl+Left"), self)
        prev_page_shortcut1.activated.connect(self.prev_page)
        prev_page_shortcut2 = QShortcut(QKeySequence(Qt.Key_PageUp), self) # Use standard PageUp key
        prev_page_shortcut2.activated.connect(self.prev_page)
        print("Shortcuts Ctrl+Left / PageUp -> Previous Page registered.")

        next_page_shortcut1 = QShortcut(QKeySequence("Ctrl+Right"), self)
        next_page_shortcut1.activated.connect(self.next_page)
        next_page_shortcut2 = QShortcut(QKeySequence(Qt.Key_PageDown), self) # Use standard PageDown key
        next_page_shortcut2.activated.connect(self.next_page)
        print("Shortcuts Ctrl+Right / PageDown -> Next Page registered.")

    # --- Keyboard Event Handling --- #
    def keyPressEvent(self, event: QEvent):
        """Handle key presses for table navigation and actions."""
        # Check if the results table or one of its children (viewport) has focus
        table_has_focus = self.results_table.hasFocus() or self.results_table.viewport().hasFocus()

        if table_has_focus:
            key = event.key()
            modifiers = event.modifiers()

            # Check for standard copy/paste keys first
            is_ctrl_or_meta = modifiers & (Qt.ControlModifier | Qt.MetaModifier) # Meta is Cmd on macOS

            if key == Qt.Key_Return or key == Qt.Key_Enter:
                print("Key Press: Enter on table")
                self._open_details_selected()
                event.accept()
                return
            elif key == Qt.Key_Space:
                print("Key Press: Space on table")
                self._toggle_mark_selected()
                event.accept()
                return
            elif is_ctrl_or_meta and key == Qt.Key_M:
                print("Key Press: Ctrl/Meta+M on table")
                self._copy_magnet_selected()
                event.accept()
                return
            elif is_ctrl_or_meta and key == Qt.Key_L:
                 print("Key Press: Ctrl/Meta+L on table")
                 self._copy_details_selected()
                 event.accept()
                 return
            elif is_ctrl_or_meta and key == Qt.Key_C:
                 print("Key Press: Ctrl/Meta+C on table")
                 self._copy_name_selected()
                 event.accept()
                 return

        # Call base class implementation for other keys / focus targets
        super().keyPressEvent(event)

    # --- Helper Methods for Selected Row Actions ---
    def _get_selected_row_data(self) -> ScrapeResult | None:
        """Gets the ScrapeResult data for the currently selected row."""
        selected_items = self.results_table.selectedItems()
        if not selected_items:            
            return None
        # Assume single row selection
        selected_row_index = selected_items[0].row()
        if 0 <= selected_row_index < len(self.current_results): # Use current_results which maps filtered rows
            # Need to map the visible row index back to the unfiltered index if filtering is active
            # Let's refine this - self.current_results is now potentially outdated with live filtering
            # We should get the data directly associated with the table row

            # Get the original index stored when populating
            mark_item = self.results_table.item(selected_row_index, self.mark_column_index)
            if mark_item:
                original_index = mark_item.data(Qt.UserRole + 1)
                if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                    return self.unfiltered_page_results[original_index]
                else:
                    print(f"Warning: Invalid original index ({original_index}) found for selected row {selected_row_index}")
                    return None
            else:
                print(f"Warning: Mark item not found for selected row {selected_row_index} to get original index.")
                return None
        else:
            print(f"Warning: Selected row index {selected_row_index} out of bounds for current_results.")
            return None

    def _get_all_selected_row_data(self) -> list[tuple[int, ScrapeResult]]:
        """Gets the original row index and ScrapeResult data for all selected rows."""
        selected_rows_data = []
        selected_indices = {index.row() for index in self.results_table.selectedIndexes()}
        if not selected_indices:
            return []

        for row_index in sorted(list(selected_indices)):
            # Get the original index stored when populating
            mark_item = self.results_table.item(row_index, self.mark_column_index)
            if mark_item:
                original_index = mark_item.data(Qt.UserRole + 1)
                if isinstance(original_index, int) and 0 <= original_index < len(self.unfiltered_page_results):
                    selected_rows_data.append((row_index, self.unfiltered_page_results[original_index]))
                else:
                    print(f"Warning: Invalid original index ({original_index}) found for selected row {row_index}")
            else:
                print(f"Warning: Mark item not found for selected row {row_index} to get original index.")
        return selected_rows_data

    def _open_details_selected(self):
        # This action only makes sense for a single selection
        result_data = self._get_selected_row_data()
        if result_data and result_data.link and result_data.link != '#':
            print(f"Opening details for: {result_data.name}")
            self.show_details(result_data.link)
        elif result_data:
            self.show_error_message(f"No valid details link for {result_data.name}")
        else:
            self.show_status_message("No row selected or data not found.", 3000)

    def _get_selected_row_index(self) -> int | None:
        """Helper to get the index of the single selected row, or None if multiple/zero."""
        selected_indices = {index.row() for index in self.results_table.selectedIndexes()}
        if len(selected_indices) == 1:
            return list(selected_indices)[0]
        return None

    def _copy_magnet_selected(self):
        result_data = self._get_selected_row_data()
        if result_data and result_data.magnet_link:
            try:
                pyperclip.copy(result_data.magnet_link)
                self.show_status_message("Copied magnet link.", 3000)
            except Exception as e:
                print(f"Clipboard Error (Magnet Shortcut): {e}")
                self.show_error_message("Failed to copy magnet link to clipboard.")
        elif result_data:
            self.show_status_message(f"No magnet link for {result_data.name[:30]}...", 3000)
        else:
            self.show_status_message("No row selected or data not found.", 3000)

    def _copy_details_selected(self):
        result_data = self._get_selected_row_data()
        if result_data and result_data.link and result_data.link != '#':
            try:
                pyperclip.copy(result_data.link)
                self.show_status_message(f"Copied details link.", 3000)
            except Exception as e:
                print(f"Clipboard Error (Details Shortcut): {e}")
                self.show_error_message("Failed to copy details link to clipboard.")
        elif result_data:
            self.show_status_message(f"No details link for {result_data.name[:30]}...", 3000)
        else:
            self.show_status_message("No row selected or data not found.", 3000)

    def _copy_name_selected(self):
        result_data = self._get_selected_row_data()
        if result_data:
            try:
                pyperclip.copy(result_data.name)
                self.show_status_message(f"Copied name: {result_data.name[:50]}...", 3000)
            except Exception as e:
                print(f"Clipboard Error (Name Shortcut): {e}")
                self.show_error_message("Failed to copy name to clipboard.")
        else:
            self.show_status_message("No row selected or data not found.", 3000)

    def _toggle_mark_selected(self):
        selected_items = self.results_table.selectedItems()
        if not selected_items:
            self.show_status_message("No row selected to mark/unmark.", 3000)
            return
        # Assume single row selection
        row_index = selected_items[0].row()
        self._toggle_mark_row(row_index) # Use the existing context menu action method