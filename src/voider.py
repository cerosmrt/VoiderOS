# voider.py — VoiderOS entry point
import sys
from PyQt6.QtWidgets import QApplication
from new_interface import FullscreenCircleApp
from login_screen import VoiderLoginScreen


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("voider")
    app.setDesktopFileName("voider")

    login = VoiderLoginScreen()

    def on_lock():
        login.reset()
        login.showFullScreen()

    window = FullscreenCircleApp(on_lock=on_lock)
    login.auth_success.connect(login.hide)

    window.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
