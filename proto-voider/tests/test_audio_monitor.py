"""AudioMonitor: picks the right device for the chosen source, turns raw chunks
into frames, and never touches a real audio device in tests."""
import numpy as np

from audio_monitor import AudioMonitor, pick_device, OFF, MIC, OUTPUT


class _FakePA:
    def __init__(self, devices):
        self._d = devices

    def get_device_count(self):
        return len(self._d)

    def get_device_info_by_index(self, i):
        return self._d[i]


DEVICES = [
    {'name': 'HDA Analog Out', 'maxInputChannels': 0},
    {'name': 'HDA Mic', 'maxInputChannels': 2},
    {'name': 'Monitor of Built-in Audio', 'maxInputChannels': 2},
]


def test_output_source_picks_the_monitor_device():
    assert pick_device(_FakePA(DEVICES), OUTPUT) == (2, True)


def test_mic_source_uses_the_default_input():
    assert pick_device(_FakePA(DEVICES), MIC) == (None, True)


def test_output_without_a_monitor_reports_unavailable():
    no_monitor = [d for d in DEVICES if 'Monitor' not in d['name']]
    assert pick_device(_FakePA(no_monitor), OUTPUT) == (None, False)


def test_off_source_picks_nothing():
    assert pick_device(_FakePA(DEVICES), OFF) == (None, False)


def test_process_chunk_updates_the_frame():
    m = AudioMonitor(start=False)
    t = np.arange(2048) / 44100
    m.process((0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32).tobytes())
    f = m.frame()
    assert f['level'] > 0.0
    assert len(f['wave']) == AudioMonitor.WAVE_POINTS
    assert len(f['bands']) == AudioMonitor.BANDS


def test_frame_is_silent_before_any_audio():
    f = AudioMonitor(start=False).frame()
    assert f['level'] == 0.0 and set(f['bands']) == {0.0}


def test_set_source_off_stops_and_zeroes_the_frame():
    m = AudioMonitor(start=False)
    t = np.arange(2048) / 44100
    m.process((0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32).tobytes())
    m.set_source(OFF)
    assert m.frame()['level'] == 0.0 and m.source == OFF
