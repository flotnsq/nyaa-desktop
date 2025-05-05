import re
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel,
                               QLineEdit, QPushButton, QDialogButtonBox, QWidget,
                               QSpacerItem, QSizePolicy)
from PySide6.QtCore import Qt, Signal

class FilterDialog(QDialog):
    """Dialog for setting search filters."""
    # Signal emitted when Apply is clicked, passing a dict of filters
    filters_applied = Signal(dict)
    # Signal emitted when Clear is clicked
    filters_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Filters")
        # Make it non-modal so user can interact with main window
        # self.setModal(False) # Might require more complex showing/hiding logic

        layout = QVBoxLayout(self)
        grid_layout = QGridLayout()
        layout.addLayout(grid_layout)

        # --- Filter Inputs ---
        # Min Seeders
        grid_layout.addWidget(QLabel("Min Seeders:"), 0, 0, Qt.AlignRight)
        self.min_seeders_input = QLineEdit()
        self.min_seeders_input.setPlaceholderText("e.g., 5")
        grid_layout.addWidget(self.min_seeders_input, 0, 1)

        # Min Size
        grid_layout.addWidget(QLabel("Min Size:"), 1, 0, Qt.AlignRight)
        self.min_size_input = QLineEdit()
        self.min_size_input.setPlaceholderText("e.g., 500 MiB")
        grid_layout.addWidget(self.min_size_input, 1, 1)

        # Max Size
        grid_layout.addWidget(QLabel("Max Size:"), 2, 0, Qt.AlignRight)
        self.max_size_input = QLineEdit()
        self.max_size_input.setPlaceholderText("e.g., 2 GiB (0=None)")
        grid_layout.addWidget(self.max_size_input, 2, 1)

        grid_layout.setColumnStretch(1, 1) # Allow inputs to stretch

        # --- Buttons ---
        button_box = QDialogButtonBox()
        self.apply_button = button_box.addButton("Apply", QDialogButtonBox.ApplyRole)
        self.clear_button = button_box.addButton("Clear", QDialogButtonBox.ResetRole)
        self.close_button = button_box.addButton("Close", QDialogButtonBox.RejectRole)

        layout.addWidget(button_box)

        # --- Connections ---
        self.apply_button.clicked.connect(self._emit_apply_filters)
        self.clear_button.clicked.connect(self._emit_clear_filters)
        self.close_button.clicked.connect(self.reject) # Close dialog on Close click

    def _parse_user_size_input(self, size_str: str) -> int:
        """Parses user input like '1.5 GiB', '500MB', '1024k' into bytes."""
        if not isinstance(size_str, str) or not size_str.strip():
            return 0

        size_str = size_str.strip().upper()
        # Corrected regex escape (only need one backslash for literal backslash in r-string)
        match = re.match(r'^([\d.,]+)\s*([KMGT])?I?B?$', size_str)

        if not match:
            try:
                return int(size_str.replace(',', ''))
            except ValueError:
                return 0

        num_str, unit = match.groups()
        num_str = num_str.replace(',', '')
        try:
            num = float(num_str)
        except ValueError:
            return 0

        units = {'K': 1, 'M': 2, 'G': 3, 'T': 4}
        exponent = units.get(unit, 0)
        return int(num * (1024 ** exponent))

    def _emit_apply_filters(self):
        """Parse inputs and emit the filters_applied signal."""
        filters = self.get_filters()
        self.filters_applied.emit(filters)
        # self.accept() # Optionally close dialog on Apply

    def _emit_clear_filters(self):
        """Clear UI fields and emit the filters_cleared signal."""
        self.clear_ui()
        self.filters_cleared.emit()
        # self.accept() # Optionally close dialog on Clear

    def get_filters(self) -> dict:
        """Returns the currently entered filter values as a dictionary."""
        min_seeders_str = self.min_seeders_input.text().strip()
        min_size_str = self.min_size_input.text().strip()
        max_size_str = self.max_size_input.text().strip()

        try:
            min_seeders = int(min_seeders_str) if min_seeders_str else 0
        except ValueError:
            min_seeders = 0 # Default or show error? Default for now.
        min_seeders = max(0, min_seeders) # Ensure non-negative

        min_size_bytes = self._parse_user_size_input(min_size_str)
        max_size_bytes = self._parse_user_size_input(max_size_str)

        # Basic validation for size range (optional, main window handles this too)
        if max_size_bytes > 0 and min_size_bytes > max_size_bytes:
            max_size_bytes = 0 # Reset max size if invalid range

        return {
            "min_seeders": min_seeders,
            "min_size_bytes": min_size_bytes,
            "max_size_bytes": max_size_bytes
        }

    def set_filters(self, filters: dict):
        """Sets the UI fields based on a dictionary of filter values."""
        self.min_seeders_input.setText(str(filters.get("min_seeders", 0) or ""))

        # Convert bytes back to a somewhat readable format (or just use bytes?)
        # For simplicity, let's just store/retrieve the raw string they entered?
        # No, let's set based on the processed byte values for consistency.
        # We won't try to format bytes back to GiB/MiB perfectly here.
        self.min_size_input.setText(str(filters.get("min_size_bytes", 0) or ""))
        self.max_size_input.setText(str(filters.get("max_size_bytes", 0) or "")) # 0 means no limit

    def clear_ui(self):
        """Clears the input fields in the dialog."""
        self.min_seeders_input.clear()
        self.min_size_input.clear()
        self.max_size_input.clear() 