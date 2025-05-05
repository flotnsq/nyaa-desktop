from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton

class SearchBar(QWidget):
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search torrents...")
        self.search_button = QPushButton("Search")
        
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_button)