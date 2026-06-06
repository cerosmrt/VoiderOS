# --- voider.py ---
import os
import sys
from PyQt6.QtWidgets import QApplication
from new_interface import FullscreenCircleApp

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = FullscreenCircleApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
