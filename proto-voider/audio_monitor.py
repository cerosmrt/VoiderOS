"""audio_monitor.py — reads audio from the microphone or from what the computer
is playing, and turns it into frames for the visualizer.

Sources: OFF (nothing is opened — the mic is never touched unless asked),
MIC (default input), OUTPUT (the PipeWire/PulseAudio *monitor* of the speakers:
TTS, YouTube, anything that sounds). A daemon thread reads chunks; the UI only
ever calls frame(). Any audio failure leaves the frame silent."""
import sys
import threading

import numpy as np

from audio_analysis import rms_level, waveform, band_spectrum

OFF, MIC, OUTPUT = 'off', 'mic', 'output'


def pick_device(pa, source):
    """(device_index, available) for `source`. A None index means the default
    input; available=False means there is nothing to read for that source."""
    if source == MIC:
        return None, True
    if source == OUTPUT:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0 and 'monitor' in info['name'].lower():
                return i, True
    return None, False


class AudioMonitor:
    RATE = 44100
    CHUNK = 1024
    WINDOW = 2048
    WAVE_POINTS = 128
    BANDS = 32

    def __init__(self, source=OFF, start=True):
        self.source = OFF
        self.status = ''
        self._lock = threading.Lock()
        self._frame = self._silent()
        self._stop = None
        if start:
            self.set_source(source)

    @staticmethod
    def _silent():
        return {'level': 0.0, 'wave': [0.0] * AudioMonitor.WAVE_POINTS,
                'bands': [0.0] * AudioMonitor.BANDS}

    def frame(self):
        with self._lock:
            return dict(self._frame)

    def process(self, raw):
        """Float32 bytes → analysed frame."""
        samples = np.frombuffer(raw, dtype=np.float32)
        frame = {'level': rms_level(samples),
                 'wave': waveform(samples, self.WAVE_POINTS),
                 'bands': band_spectrum(samples, self.RATE, self.BANDS)}
        with self._lock:
            self._frame = frame

    def set_source(self, source):
        """Switch (or stop) the source; the previous reader is told to stop."""
        if self._stop is not None:
            self._stop.set()
            self._stop = None
        self.source = source
        self.status = ''
        with self._lock:
            self._frame = self._silent()
        if source == OFF:
            return
        stop = threading.Event()
        self._stop = stop
        threading.Thread(target=self._run, args=(source, stop), daemon=True).start()

    def close(self):
        self.set_source(OFF)

    def _run(self, source, stop):
        stream = pa = None
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            idx, ok = pick_device(pa, source)
            if not ok:
                self.status = 'no hay dispositivo para ' + source
                return
            stream = pa.open(format=pyaudio.paFloat32, channels=1, rate=self.RATE,
                             input=True, input_device_index=idx,
                             frames_per_buffer=self.CHUNK)
            buf = np.zeros(self.WINDOW, dtype=np.float32)
            while not stop.is_set():
                chunk = np.frombuffer(
                    stream.read(self.CHUNK, exception_on_overflow=False), dtype=np.float32)
                buf = np.concatenate((buf[len(chunk):], chunk))
                if not stop.is_set():
                    self.process(buf.tobytes())
        except Exception as e:                      # no device, no pyaudio, no PipeWire…
            self.status = str(e)
            print(f"AudioMonitor: {e}", file=sys.stderr)
        finally:
            try:
                if stream is not None:
                    stream.close()
                if pa is not None:
                    pa.terminate()
            except Exception:
                pass
