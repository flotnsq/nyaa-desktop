from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

class ResultsTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Name", "Size", "Date", "Seeders", "Leechers"])
        self.setRowCount(0)
        self.horizontalHeader().setStretchLastSection(True)