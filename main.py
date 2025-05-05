# main.py
import sys
import os
# Import QApplication from PySide6, not PyQt6
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.main_window import MainWindow

# Set environment variable for Qt (can help with some rendering issues)
# Consider if this is truly necessary for PySide6, often it's not.
# os.environ['QT_API'] = 'pyside6' # Keep if needed, otherwise remove

if __name__ == "__main__":
    # Set application attribute for HiDPI scaling before QApplication init
    if hasattr(QApplication, 'setAttribute'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Load stylesheet - Path looks correct relative to main.py if structure is:
    # main.py
    # ui/
    #   styles/
    #     dark_theme.qss
    #   main_window.py
    # core/
    #   scraper.py
    # requirements.txt
    # ...etc.
    style_path = "ui/styles/dark_theme.qss"
    try:
        # Ensure path is correct relative to execution directory or use absolute paths
        # For robustness, consider finding the script's directory:
        # script_dir = os.path.dirname(os.path.abspath(__file__))
        # style_path = os.path.join(script_dir, "ui", "styles", "dark_theme.qss")
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())
        print(f"Loaded stylesheet: {style_path}")
    except FileNotFoundError:
        print(f"WARNING: Stylesheet '{style_path}' not found, using default style.")
    except Exception as e:
        print(f"ERROR: Error loading stylesheet: {e}")

    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
