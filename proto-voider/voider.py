# --- voider.py ---
import os
import sys
from PyQt6.QtWidgets import QApplication
from new_interface import FullscreenCircleApp

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        # The fonts travel with the app (fonts/), so the interface draws the same
        # letters on every machine. Before the window: it picks its font when built.
        from resources import load_bundled_fonts
        load_bundled_fonts()
        window = FullscreenCircleApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
