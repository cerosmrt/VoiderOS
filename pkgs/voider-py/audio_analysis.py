"""audio_analysis.py — the maths behind the audio visualizer (numpy only, no Qt,
no audio device), so it can be tested with synthetic signals."""
import numpy as np

GAIN = 6.0                       # typical music RMS → 0..1 (as in the old AudioMonitor)
F_MIN, F_MAX = 40.0, 16000.0     # band range for the spectrum


def rms_level(samples, gain=GAIN):
    """Volume 0..1 from the RMS of a chunk."""
    if len(samples) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float64) ** 2)))
    return min(rms * gain, 1.0)


def waveform(samples, n):
    """`n` points of the signal (peak of each block), -1..1, for the oscilloscope."""
    if len(samples) == 0:
        return [0.0] * n
    x = np.asarray(samples, dtype=np.float64)
    blocks = np.array_split(x, n)
    peak = [float(b[np.argmax(np.abs(b))]) if len(b) else 0.0 for b in blocks]
    return [max(-1.0, min(1.0, v * 2.0)) for v in peak]


def band_spectrum(samples, rate, bands):
    """`bands` log-spaced magnitudes 0..1 (40 Hz – 16 kHz) for the analyzer."""
    if len(samples) == 0:
        return [0.0] * bands
    x = np.asarray(samples, dtype=np.float64)
    x = x * np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x)) / (len(x) / 4.0)
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    edges = np.geomspace(F_MIN, min(F_MAX, rate / 2.0), bands + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (freqs >= lo) & (freqs < hi)
        m = float(mag[sel].max()) if sel.any() else 0.0
        # dB scale: -60 dB → 0, 0 dB → 1; silence stays exactly 0.
        out.append(0.0 if m <= 1e-9 else max(0.0, min(1.0, 1.0 + 20.0 * np.log10(m) / 60.0)))
    return out


class Smoother:
    """Fast attack, slow decay per value: the shape jumps on a beat and fades
    gently (the same feel the old pulsing circle had)."""

    def __init__(self, attack=0.6, decay=0.04):
        self.attack, self.decay = attack, decay
        self._v = []

    def update(self, values):
        if len(self._v) != len(values):
            self._v = [0.0] * len(values)
        for i, raw in enumerate(values):
            k = self.attack if raw > self._v[i] else self.decay
            self._v[i] = k * raw + (1.0 - k) * self._v[i]
        return list(self._v)
