"""
watch.py — Auto-restart voider.py on any .py file change.
Run with: python watch.py
"""
import subprocess
import sys
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(WATCH_DIR, "voider.py")
PYTHON = sys.executable

class RestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.restart_flag = False

    def on_modified(self, event):
        if event.src_path.endswith(".py") and not event.is_directory:
            print(f"\n⚡ Changed: {os.path.basename(event.src_path)} — restarting...")
            self.restart_flag = True

def run():
    handler = RestartHandler()
    observer = Observer()
    observer.schedule(handler, WATCH_DIR, recursive=False)
    observer.start()

    proc = None
    try:
        while True:
            if proc is None or handler.restart_flag:
                handler.restart_flag = False
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                print("▶ Starting voider.py...")
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                proc = subprocess.Popen([PYTHON, MAIN], env=env)
            elif proc.poll() is not None:
                # App closed by user — stop the watcher
                print("⏹ App closed. Stopping watcher.")
                break
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n🛑 Watcher stopped.")
        if proc and proc.poll() is None:
            proc.terminate()
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    run()
