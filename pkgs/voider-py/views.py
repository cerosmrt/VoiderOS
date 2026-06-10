# views.py
import math
import os
import sys
import threading
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QTimer


class AudioMonitor:
    """Reads system audio level from the PipeWire monitor source in a daemon thread.
    Falls back silently to level=0 if audio is unavailable."""

    CHUNK = 512
    RATE  = 44100
    # Multiply raw RMS by this to map typical music levels to 0-1
    _GAIN = 6.0

    def __init__(self):
        self._level = 0.0
        if not self._wayland_available():
            return
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    @staticmethod
    def _wayland_available() -> bool:
        wd = os.environ.get('WAYLAND_DISPLAY', '')
        if not wd:
            return False
        if wd.startswith('/'):
            return os.path.exists(wd)
        runtime = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        return os.path.exists(os.path.join(runtime, wd))

    def _find_monitor_index(self, pa):
        """Return the device index of a PipeWire/PulseAudio monitor source, or None."""
        # First, try to find our virtual mic
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0 and 'voider_virtual_mic' in info['name'].lower():
                return i
        
        # Fall back to any monitor source
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0 and 'monitor' in info['name'].lower():
                return i
        return None  # fall back to default input

    def _run(self):
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            idx = self._find_monitor_index(pa)
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=self.RATE,
                input=True,
                input_device_index=idx,
                frames_per_buffer=self.CHUNK,
            )
            while True:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(data, dtype=np.float32)
                rms = float(np.sqrt(np.mean(samples ** 2)))
                self._level = min(rms * self._GAIN, 1.0)
        except Exception as e:
            print(f"AudioMonitor: {e}", file=sys.stderr)
            self._level = 0.0

    @property
    def level(self):
        return self._level


class NormalView(QWidget):
    """F1 view: minimal white circle with centered text entry"""

    _BREATH_PERIOD_MS = 4000  # one full breath cycle
    _BREATH_AMPLITUDE = 0.15  # ±15% → scale 0.85..1.15 (more visible breathing)
    _AUDIO_MAX_SCALE  = 0.35  # +35% radius at peak audio
    _TICK_MS = 33             # ~30 fps

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setStyleSheet("background: black;")

        self._breath_phase = 0.0
        self._audio_smooth = 0.0   # exponentially smoothed audio level
        self._audio = AudioMonitor()

        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._breath_tick)
        self._breath_timer.start(self._TICK_MS)

    def _breath_tick(self):
        self._breath_phase += 2 * math.pi * self._TICK_MS / self._BREATH_PERIOD_MS

        # Fast attack, slow decay so the circle jumps on beats and fades gently
        raw = self._audio.level
        if raw > self._audio_smooth:
            self._audio_smooth = 0.6 * raw + 0.4 * self._audio_smooth
        else:
            self._audio_smooth = 0.04 * raw + 0.96 * self._audio_smooth

        self.update()

    def paintEvent(self, event):
        if not self.parent_app:
            return
        if self.width() == 0 or self.height() == 0:
            return
        painter = QPainter(self)
        if not painter.isActive():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("white"), 10)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        w = self.width()
        h = self.height()
        center_x = w // 2
        center_y = h // 2
        base_radius = min(w, h) // 2 - 35

        breath_scale = 1.0 + self._BREATH_AMPLITUDE * math.sin(self._breath_phase)
        audio_scale  = 1.0 + self._AUDIO_MAX_SCALE * self._audio_smooth
        # Audio overrides breathing when active; breathing takes over in silence
        scale  = max(breath_scale, audio_scale)
        radius = int(base_radius * scale)

        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)