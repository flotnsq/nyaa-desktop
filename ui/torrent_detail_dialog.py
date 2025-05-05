from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
                               QTreeWidget, QTreeWidgetItem, QSizePolicy,
                               QPushButton, QDialogButtonBox, QHeaderView, QGridLayout,
                               QApplication, QMessageBox, QWidget, QSpacerItem, QLineEdit,
                               QScrollArea) # Add QScrollArea
from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup # Added QSize, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup
from PySide6.QtGui import QDesktopServices, QPixmap # Added QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply # Add Network imports

from core.scraper import TorrentDetails, FileInfo, format_size
import os
import qtawesome as qta
import pyperclip

class TorrentDetailDialog(QDialog):
    FILE_TYPE_ICONS = {
        # Archives
        "zip": ("mdi.folder-zip-outline", "orange"), "rar": ("mdi.folder-zip-outline", "orange"),
        "7z": ("mdi.folder-zip-outline", "orange"), "tar": ("mdi.folder-zip-outline", "orange"),
        "gz": ("mdi.folder-zip-outline", "orange"), # Using generic zip icon for archives
        # Video
        "mkv": ("mdi.movie-open-outline", "lightblue"), "mp4": ("mdi.movie-open-outline", "lightblue"),
        "avi": ("mdi.movie-open-outline", "lightblue"), "mov": ("mdi.movie-open-outline", "lightblue"),
        "wmv": ("mdi.movie-open-outline", "lightblue"), # Using movie icon
        # Audio
        "mp3": ("mdi.music-note-outline", "lightgreen"), "flac": ("mdi.music-note-outline", "lightgreen"),
        "wav": ("mdi.music-note-outline", "lightgreen"), "ogg": ("mdi.music-note-outline", "lightgreen"),
        "aac": ("mdi.music-note-outline", "lightgreen"),
        # Images
        "jpg": ("mdi.image-outline", "lightcoral"), "jpeg": ("mdi.image-outline", "lightcoral"),
        "png": ("mdi.image-outline", "lightcoral"), "gif": ("mdi.image-outline", "lightcoral"),
        "bmp": ("mdi.image-outline", "lightcoral"), "webp": ("mdi.image-outline", "lightcoral"),
        # Text/Docs
        "txt": ("mdi.file-document-outline", "whitesmoke"), "nfo": ("mdi.information-outline", "whitesmoke"),
        "srt": ("mdi.subtitles-outline", "whitesmoke"),
        "ass": ("mdi.subtitles-outline", "whitesmoke"),
        "pdf": ("mdi.file-pdf-box", "tomato"), "doc": ("mdi.file-word-box-outline", "dodgerblue"),
        "docx": ("mdi.file-word-box-outline", "dodgerblue"), "xls": ("mdi.file-excel-box-outline", "mediumseagreen"),
        "xlsx": ("mdi.file-excel-box-outline", "mediumseagreen"), "ppt": ("mdi.file-powerpoint-box-outline", "orangered"),
        "pptx": ("mdi.file-powerpoint-box-outline", "orangered"),
        # Code/Scripts
        "py": ("mdi.language-python", "yellow"), "js": ("mdi.language-javascript", "yellow"),
        "html": ("mdi.language-html5", "yellow"), "css": ("mdi.language-css3", "yellow"),
        "json": ("mdi.code-json", "yellow"), "xml": ("mdi.xml", "yellow"),
        # Executables/System
        "exe": ("mdi.cog-outline", "grey"), "iso": ("mdi.disc", "grey"),
        # Default
        "default": ("mdi.file-outline", "lightgrey")
    }

    def __init__(self, details: TorrentDetails, parent=None):
        super().__init__(parent)
        self.details = details
        # Use text wrapping for potentially long titles
        self.setWindowTitle(f"Details") # Set basic title first
        self.setMinimumSize(750, 600) # Increase min height slightly for better spacing

        # Create a main widget to hold all content
        main_widget = QWidget()
        # Apply the main layout to this main_widget
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(12) # Increased spacing slightly

        # --- Title Label ---
        # Use a QLabel for the title inside the dialog for better control
        title_label = QLabel(f"<b>{details.title}</b>")
        title_label.setWordWrap(True) # Allow wrapping
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse) # Allow selecting title
        layout.addWidget(title_label)

        # --- Top Info Section (QGridLayout) ---
        info_group = QWidget()
        info_layout = QGridLayout(info_group)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setHorizontalSpacing(15)
        info_layout.setVerticalSpacing(10) # Increased spacing slightly

        # Row 0: Category, Size
        info_layout.addWidget(QLabel("<b>Category:</b>"), 0, 0, Qt.AlignRight | Qt.AlignTop)
        cat_label = QLabel(details.category)
        cat_label.setWordWrap(True)
        info_layout.addWidget(cat_label, 0, 1)

        info_layout.addWidget(QLabel("<b>Size:</b>"), 0, 2, Qt.AlignRight | Qt.AlignTop)
        info_layout.addWidget(QLabel(details.size_str), 0, 3)

        # Row 1: Submitter, Date
        info_layout.addWidget(QLabel("<b>Submitter:</b>"), 1, 0, Qt.AlignRight | Qt.AlignTop)
        # Handle anonymous submitter links if scraper provides them
        submitter_label = QLabel(details.submitter) # Scraper should handle formatting 'Anonymous'
        submitter_label.setWordWrap(True) # Needed if user names are long
        info_layout.addWidget(submitter_label, 1, 1)

        info_layout.addWidget(QLabel("<b>Date:</b>"), 1, 2, Qt.AlignRight | Qt.AlignTop)
        date_label = QLabel(details.date_submitted)
        date_label.setToolTip(details.date_submitted) # Show full date on hover if needed
        info_layout.addWidget(date_label, 1, 3)


        # Row 2: S/L/C, Information (if available)
        info_layout.addWidget(QLabel("<b>S/L/C:</b>"), 2, 0, Qt.AlignRight | Qt.AlignTop)
        slc_text = f"<font color='lightgreen'>{details.seeders if details.seeders is not None else 'N/A'}</font> / " \
                   f"<font color='orange'>{details.leechers if details.leechers is not None else 'N/A'}</font> / " \
                   f"<font color='lightblue'>{details.completed if details.completed is not None else 'N/A'}</font>"
        info_layout.addWidget(QLabel(slc_text), 2, 1)

        if details.information and details.information != "N/A":
             info_layout.addWidget(QLabel("<b>Info Link:</b>"), 2, 2, Qt.AlignRight | Qt.AlignTop)
             # Make the information field a clickable link
             info_link_label = QLabel(f'<a href="{details.information}">{details.information}</a>')
             info_link_label.setOpenExternalLinks(True)
             info_link_label.setToolTip("Opens external link")
             info_layout.addWidget(info_link_label, 2, 3)


        # Row 3: Info Hash (with copy button)
        info_layout.addWidget(QLabel("<b>Info Hash:</b>"), 3, 0, Qt.AlignRight | Qt.AlignTop)
        # Use QLineEdit for easy selection and copying, make it read-only
        self.info_hash_edit = QLineEdit(details.info_hash)
        self.info_hash_edit.setReadOnly(True)
        self.info_hash_edit.setToolTip("Torrent Info Hash (double-click to select all)")
        # Optional: Adjust style for read-only line edit if needed via QSS
        # self.info_hash_edit.setStyleSheet("QLineEdit[readOnly=\"true\"] { background-color: #333; border: 1px solid #555; }")
        info_layout.addWidget(self.info_hash_edit, 3, 1, 1, 3) # Span 3 columns


        # Set column stretch
        info_layout.setColumnStretch(1, 1) # Stretch value columns
        info_layout.setColumnStretch(3, 1)
        info_layout.setRowStretch(4, 1) # Add stretch at the bottom if needed

        layout.addWidget(info_group)
        # --- End Top Info Section ---


        # --- Action Buttons (Copy Magnet/Hash) ---
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.copy_magnet_button = QPushButton(qta.icon('fa5s.magnet', color='red'), " Copy Magnet")
        icon_size = int(self.copy_magnet_button.fontMetrics().height() * 0.9)
        self.copy_magnet_button.setIconSize(QSize(icon_size, icon_size)) # Adjust icon size
        self.copy_magnet_button.setToolTip("Copy Magnet Link to Clipboard")
        self.copy_magnet_button.setEnabled(bool(details.magnet_link))
        self.copy_magnet_button.clicked.connect(self._copy_magnet)

        self.copy_infohash_button = QPushButton(qta.icon('mdi.content-copy', color='orange'), " Copy Hash") # Use mdi copy icon
        icon_size2 = int(self.copy_infohash_button.fontMetrics().height() * 0.9)
        self.copy_infohash_button.setIconSize(QSize(icon_size2, icon_size2))
        self.copy_infohash_button.setToolTip("Copy Info Hash to Clipboard")
        self.copy_infohash_button.setEnabled(details.info_hash != "N/A" and bool(details.info_hash))
        self.copy_infohash_button.clicked.connect(self._copy_info_hash)

        action_layout.addStretch() # Push buttons to the right
        action_layout.addWidget(self.copy_magnet_button)
        action_layout.addWidget(self.copy_infohash_button)
        layout.addLayout(action_layout)
        # --- End Action Buttons ---

        # --- Description Section ---
        desc_label = QLabel("<b>Description:</b>")
        desc_label.setObjectName("SectionHeaderLabel") # Add object name
        layout.addWidget(desc_label)
        self.description_browser = QTextBrowser()
        # Clean up description HTML if needed (basic cleaning example)
        clean_html = details.description.replace('<br>', '<br/>') # Ensure self-closing br tags
        self.description_browser.setHtml(clean_html)
        self.description_browser.setOpenExternalLinks(False) # Handle links manually for safety/control
        self.description_browser.anchorClicked.connect(self.safe_open_url) # Connect signal
        self.description_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) # Prefer height based on content
        self.description_browser.setFixedHeight(150) # Start with a fixed height, user can scroll
        layout.addWidget(self.description_browser) # No stretch factor initially

        # --- Image Preview Section ---
        if details.image_urls:
            img_prev_label = QLabel("<b>Image Previews:</b>")
            img_prev_label.setObjectName("SectionHeaderLabel") # Add object name
            layout.addWidget(img_prev_label)
            # Use a horizontal layout that can potentially wrap (or just horizontal scroll)
            self.image_preview_layout = QHBoxLayout()
            image_preview_container = QWidget()
            image_preview_container.setLayout(self.image_preview_layout)

            # Add the image container directly to the layout now
            layout.addWidget(image_preview_container)

            self.image_labels = {} # url -> QLabel map
            self.network_manager = QNetworkAccessManager()

            # Limit displayed previews
            preview_limit = 10
            for img_url in details.image_urls[:preview_limit]:
                placeholder_label = QLabel(f"Loading {os.path.basename(QUrl(img_url).path())[:20]}...")
                placeholder_label.setFixedSize(150, 150) # Fixed size for placeholder
                placeholder_label.setAlignment(Qt.AlignCenter)
                placeholder_label.setStyleSheet("border: 1px solid grey; background-color: #eee;") # Basic styling
                self.image_preview_layout.addWidget(placeholder_label)
                self.image_labels[img_url] = placeholder_label
                self._download_image(img_url, placeholder_label)
            self.image_preview_layout.addStretch() # Push images left

        # --- File List Section ---
        files_label = QLabel("<b>Files:</b>")
        files_label.setObjectName("SectionHeaderLabel") # Add object name
        layout.addWidget(files_label)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Name", "Size"])
        self.file_tree.header().setStretchLastSection(False)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_tree.setAlternatingRowColors(True) # Nice visual aid for file list
        self.file_tree.setSortingEnabled(True) # Enable sorting
        self.file_tree.header().setSectionsClickable(True) # Make headers clickable

        self.populate_nested_file_tree(details.file_list)

        # Allow file tree to take significant vertical space
        self.file_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.file_tree, 1) # Give file tree stretch factor 1

        # --- Connect Signals ---
        self.file_tree.header().sectionClicked.connect(self._handle_file_tree_sort)

        # --- Comments Section --- #
        if details.comments:
            comments_label = QLabel("<b>Comments:</b>")
            comments_label.setObjectName("SectionHeaderLabel")
            layout.addWidget(comments_label)

            self.comments_browser = QTextBrowser()
            self.comments_browser.setOpenExternalLinks(False) # Handle links manually
            self.comments_browser.anchorClicked.connect(self.safe_open_url)
            self.comments_browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.comments_browser.setFixedHeight(200) # Start with a fixed height

            # Build HTML for comments
            all_comments_html = """
            <style>
                .comment-block { border: 1px solid #444; margin-bottom: 10px; padding: 8px; border-radius: 4px; }
                .comment-header { font-size: 9pt; color: grey; margin-bottom: 5px; }
                .comment-author { font-weight: bold; }
                .comment-body p { margin: 0; padding: 0; }
            </style>
            """
            for comment in details.comments:
                all_comments_html += f"""
                <div class='comment-block'>
                    <div class='comment-header'>
                        <span class='comment-author'>{comment.get('author', 'N/A')}</span> - 
                        <span class='comment-date'>{comment.get('date', 'N/A')}</span>
                    </div>
                    <div class='comment-body'>
                        {comment.get('content_html', '[No Content]')}
                    </div>
                </div>
                """
            self.comments_browser.setHtml(all_comments_html)
            layout.addWidget(self.comments_browser)

        # --- Dialog Buttons (OK Button) ---
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # --- Setup Scroll Area for the entire content ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setWidget(main_widget) # Put the widget with all content inside scroll area

        # Create a new main layout for the dialog itself
        dialog_layout = QVBoxLayout(self) # Apply to self (the QDialog)
        dialog_layout.addWidget(scroll_area) # Add the scroll area to the dialog's layout

        # Expand only the top level initially, user can expand more
        self.file_tree.expandToDepth(0)
        # Set initial sort indicator (e.g., Name Ascending)
        self.file_tree.sortByColumn(0, Qt.AscendingOrder)
        self.file_tree.header().setSortIndicator(0, Qt.AscendingOrder)
        self.file_tree.header().setSortIndicatorShown(True)

    def showEvent(self, event): # Override showEvent to trigger animation
        # Start transparent for fade-in
        self.setWindowOpacity(0.0)

        # Get final geometry *after* the dialog is initially shown but still transparent
        final_geometry = self.geometry()
        start_pos = final_geometry.topLeft() + QPoint(0, 30) # Start 30px below final
        end_pos = final_geometry.topLeft()

        # Set initial position (slightly below) before animation starts
        self.move(start_pos)

        # Call the original showEvent AFTER setting initial state
        super().showEvent(event)

        # --- Setup Animations --- #
        # Opacity Animation (Fade In)
        self.opacity_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.opacity_animation.setDuration(350) # Slightly longer duration
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)
        self.opacity_animation.setEasingCurve(QEasingCurve.InOutQuad)

        # Position Animation (Slide Up)
        self.pos_animation = QPropertyAnimation(self, b"pos", self)
        self.pos_animation.setDuration(350)
        self.pos_animation.setStartValue(start_pos)
        self.pos_animation.setEndValue(end_pos)
        self.pos_animation.setEasingCurve(QEasingCurve.InOutQuad)

        # --- Group and Start Animations --- #
        self.animation_group = QParallelAnimationGroup(self)
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.addAnimation(self.pos_animation)
        self.animation_group.start()

    def safe_open_url(self, url: QUrl):
        """Opens URL from description safely in default browser after confirmation."""
        url_string = url.toString()
        # Basic check for potentially risky schemes (can be expanded)
        safe_schemes = ["http", "https", "mailto"]
        if url.scheme().lower() not in safe_schemes:
            QMessageBox.warning(self, "Blocked Link", f"Opening links with scheme '{url.scheme()}' is not permitted.")
            return

        reply = QMessageBox.question(self, "Open Link?",
                                     f"Do you want to open this external link in your browser?\n\n{url_string}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if not QDesktopServices.openUrl(url):
                QMessageBox.warning(self, "Error Opening Link", f"Could not open the link:\n{url_string}")

    def _copy_to_clipboard(self, text, button, success_message="Copied!"):
        """Helper function to copy text and provide visual feedback."""
        if not text:
            print("No text available to copy.")
            return
        try:
            QApplication.clipboard().setText(text)
            print(f"'{text[:30]}...' copied to clipboard.")
            original_text = button.text()
            button.setText(success_message)
            button.setEnabled(False) # Briefly disable
            # Timer to restore button text and enable state
            QTimer.singleShot(1500, lambda: self._restore_button_state(button, original_text))
        except Exception as e:
            print(f"Error copying to clipboard: {e}")
            QMessageBox.warning(self, "Clipboard Error", f"Could not copy to clipboard:\n{e}")

    def _restore_button_state(self, button, original_text):
        """Restores button text and enabled state."""
        button.setText(original_text)
        button.setEnabled(True)


    def _copy_magnet(self):
        self._copy_to_clipboard(self.details.magnet_link, self.copy_magnet_button, "Magnet Copied!")

    def _copy_info_hash(self):
        self._copy_to_clipboard(self.details.info_hash, self.copy_infohash_button, "Hash Copied!")


    def get_file_type_icon(self, filename):
        extension = filename.split('.')[-1].lower() if '.' in filename else ""
        icon_name, color = self.FILE_TYPE_ICONS.get(extension, self.FILE_TYPE_ICONS["default"])
        # Return the icon itself
        try:
             return qta.icon(icon_name, color=color)
        except Exception as e:
             print(f"Warning: Failed to get qtawesome icon '{icon_name}': {e}")
             # Fallback to a default Qt icon or a known safe qta icon
             return qta.icon(self.FILE_TYPE_ICONS["default"][0], color=self.FILE_TYPE_ICONS["default"][1])


    def populate_nested_file_tree(self, file_list: list[FileInfo]):
        self.file_tree.clear()
        if not file_list:
            QTreeWidgetItem(self.file_tree, ["No file information available."])
            return

        folder_items = {} # path_str: QTreeWidgetItem
        self.file_tree.setUpdatesEnabled(False) # Performance optimization

        for file_info in file_list:
            path_components = file_info.name.replace("\\", "/").split('/')
            filename = path_components[-1]
            folder_path_components = path_components[:-1]

            current_parent_item = self.file_tree.invisibleRootItem()
            current_path_str = ""

            for i, component in enumerate(folder_path_components):
                if not component: continue
                parent_path_str = current_path_str
                current_path_str = os.path.join(current_path_str, component) if current_path_str else component # Use os.path.join for consistency? No, stick to forward slash for dict keys.
                current_path_str = "/".join(folder_path_components[:i+1]) # Build path key reliably


                if current_path_str not in folder_items:
                    folder_item = QTreeWidgetItem(current_parent_item)
                    folder_item.setText(0, component)
                    folder_item.setIcon(0, qta.icon('mdi.folder-outline', color='#87CEFA')) # Use mdi folder
                    folder_item.setData(0, Qt.UserRole, component.lower()) # Store lowercase name for sorting
                    folder_item.setData(1, Qt.UserRole, 0) # Store size in bytes for sorting
                    # Set tooltip to show full path for folder
                    folder_item.setToolTip(0, current_path_str)
                    folder_items[current_path_str] = folder_item
                    current_parent_item = folder_item
                else:
                    current_parent_item = folder_items[current_path_str]

                # Add file size to this folder and implicitly handled later or during creation
                existing_size = current_parent_item.data(1, Qt.UserRole) or 0
                current_parent_item.setData(1, Qt.UserRole, existing_size + file_info.size_bytes)

            # Create the file item
            file_item = QTreeWidgetItem(current_parent_item)
            file_item.setText(0, filename)
            file_item.setText(1, file_info.size_str)
            file_item.setData(0, Qt.UserRole, filename.lower()) # Store lowercase name for sorting
            file_item.setData(1, Qt.UserRole, file_info.size_bytes) # Store size bytes for sorting
            file_item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            file_item.setIcon(0, self.get_file_type_icon(filename))
            # Set tooltip to show full path for file
            full_file_path = "/".join(path_components)
            file_item.setToolTip(0, full_file_path)
            file_item.setToolTip(1, f"{file_info.size_bytes:,} bytes") # Show bytes in tooltip

        # Second pass to set folder sizes and alignment
        for item in folder_items.values():
            total_folder_size = item.data(1, Qt.UserRole)
            if total_folder_size is not None:
                item.setText(1, format_size(total_folder_size))
                item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                item.setToolTip(1, f"{total_folder_size:,} bytes") # Show bytes in tooltip

        self.file_tree.setUpdatesEnabled(True)
        # Sort items within each level by name (column 0)
        # self.file_tree.sortItems(0, Qt.AscendingOrder) # This sorts globally, need per-level sort if desired. Recursive sort might be complex. Default order is usually fine.

    def _handle_file_tree_sort(self, logicalIndex):
        """Handles clicking on the file tree header to sort columns."""
        current_order = self.file_tree.header().sortIndicatorOrder()
        current_column = self.file_tree.header().sortIndicatorSection()

        # Toggle order if the same column is clicked, otherwise default to ascending
        if logicalIndex == current_column:
            new_order = Qt.DescendingOrder if current_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            new_order = Qt.AscendingOrder

        # Set the sort column role. We stored data in Qt.UserRole.
        # Note: Qt's default sorting uses Qt.DisplayRole (text). By setting
        # the column's sort role to Qt.UserRole, we tell it to use the data
        # we stored (lowercase name for col 0, size_bytes for col 1).
        self.file_tree.setSortRole(Qt.UserRole)
        self.file_tree.sortByColumn(logicalIndex, new_order)

        # Update the visual sort indicator
        self.file_tree.header().setSortIndicator(logicalIndex, new_order)
        self.file_tree.header().setSortIndicatorShown(True)

    def _download_image(self, url_string, target_label):
        """Starts asynchronous download of an image URL."""
        try:
            qurl = QUrl(url_string)
            if not qurl.isValid():
                target_label.setText("Invalid URL")
                target_label.setStyleSheet("border: 1px solid red; color: red;")
                return

            request = QNetworkRequest(qurl)
            reply = self.network_manager.get(request)
            # Store target label with the reply object
            reply.setProperty("target_label", target_label)
            reply.setProperty("image_url", url_string) # Store URL too for tooltips/errors
            # Connect the finished signal to the slot
            reply.finished.connect(self._on_image_download_finished)
            print(f"Starting download for: {url_string}")
        except Exception as e:
            print(f"Error initiating download for {url_string}: {e}")
            target_label.setText("Download Init Error")
            target_label.setStyleSheet("border: 1px solid red; color: red;")

    def _on_image_download_finished(self):
        """Handles the completed image download request."""
        reply = self.sender() # Get the reply object that emitted the signal
        if not reply:
            return

        target_label = reply.property("target_label")
        image_url = reply.property("image_url")

        if not target_label:
             print(f"Error: Target label not found for reply of {image_url}")
             reply.deleteLater()
             return

        if reply.error() == QNetworkReply.NetworkError.NoError:
            image_data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(image_data):
                # Scale pixmap to fit the label size while keeping aspect ratio
                scaled_pixmap = pixmap.scaled(target_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                target_label.setPixmap(scaled_pixmap)
                target_label.setToolTip(f"<img src='{image_url}' width='300'/><br/>{image_url}") # Show larger preview on hover
                target_label.setStyleSheet("") # Clear placeholder style
                print(f"Successfully loaded image: {image_url}")
            else:
                target_label.setText("Load Failed")
                target_label.setStyleSheet("border: 1px solid orange; color: orange;")
                print(f"Failed to load image data into QPixmap for: {image_url}")
        else:
            error_string = reply.errorString()
            target_label.setText(f"Net Error: {reply.error()}")
            target_label.setToolTip(f"Network Error: {error_string}\nURL: {image_url}")
            target_label.setStyleSheet("border: 1px solid red; color: red;")
            print(f"Network error downloading {image_url}: {error_string}")

        reply.deleteLater() # Clean up the reply object