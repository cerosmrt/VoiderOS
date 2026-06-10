# --- voider.py ---
import os
import sys

# Must be set before QApplication so Qt picks up the layer-shell integration
os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from new_interface import FullscreenCircleApp


def _apply_layer_shell(window):
    try:
        import voider_layer
        import PyQt6.sip as sip
        handle = window.windowHandle()
        if handle:
            voider_layer.configure(sip.unwrapinstance(handle))
    except Exception as e:
        print(f"voider-layer: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = FullscreenCircleApp()
        # Defer layer-shell config to first event loop tick so the Wayland
        # shell surface is fully constructed before we call get()
        QTimer.singleShot(0, lambda: _apply_layer_shell(window))
        sys.exit(app.exec())
    except Exception as e:
        print(f"Error: {e}")
        input("Press Enter to exit...")
