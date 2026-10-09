"""Pure audio maths for the visualizer: volume, waveform and spectrum bands."""
import numpy as np

from audio_analysis import rms_level, waveform, band_spectrum, Smoother

RATE = 44100


def _sine(freq, n=2048, amp=0.5):
    t = np.arange(n) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_silence_has_zero_level():
    assert rms_level(np.zeros(1024, dtype=np.float32)) == 0.0


def test_level_grows_with_volume_and_is_capped_at_one():
    quiet, loud = rms_level(_sine(440, amp=0.02)), rms_level(_sine(440, amp=0.2))
    assert 0.0 < quiet < loud <= 1.0
    assert rms_level(_sine(440, amp=1.0), gain=50.0) == 1.0


def test_empty_input_is_silence():
    assert rms_level(np.array([], dtype=np.float32)) == 0.0
    assert band_spectrum(np.array([], dtype=np.float32), RATE, 16) == [0.0] * 16
    assert waveform(np.array([], dtype=np.float32), 8) == [0.0] * 8


def test_waveform_has_requested_length_and_stays_in_range():
    w = waveform(_sine(100, amp=0.9), 64)
    assert len(w) == 64 and all(-1.0 <= v <= 1.0 for v in w)


def test_waveform_follows_the_signal_shape():
    w = waveform(_sine(RATE / 2048 * 2, n=2048, amp=0.8), 64)    # two full cycles
    assert max(w) > 0.5 and min(w) < -0.5


def test_spectrum_peak_lands_in_the_right_band():
    low = band_spectrum(_sine(100), RATE, 32)
    high = band_spectrum(_sine(8000), RATE, 32)
    assert len(low) == len(high) == 32
    assert low.index(max(low)) < high.index(max(high))
    assert all(0.0 <= v <= 1.0 for v in low + high)


def test_spectrum_of_silence_is_flat_zero():
    assert band_spectrum(np.zeros(2048, dtype=np.float32), RATE, 8) == [0.0] * 8


def test_smoother_attacks_fast_and_decays_slow():
    s = Smoother(attack=0.6, decay=0.05)
    up = s.update([1.0])[0]
    assert up == 0.6                                   # jumps toward the peak
    down = s.update([0.0])[0]
    assert 0.5 < down < 0.6                            # falls only a little
