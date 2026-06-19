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
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
        # Only block on input when attached to an interactive terminal (dev run).
        # When packaged under the layer-shell host there's no usable stdin, so
        # a bare input() would hang the desktop on a startup crash.
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")
