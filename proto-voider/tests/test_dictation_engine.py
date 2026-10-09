"""DictationEngine: listens continuously, transcribes each phrase on a second
thread (so listening never pauses), and hands finished text to the UI by polling."""
import threading
import time

import numpy as np

from dictation_engine import DictationEngine

RATE = 16000
CHUNK = 512


def _tone(seconds, amp=0.3):
    n = int(RATE * seconds)
    return (amp * np.sin(2 * np.pi * 220 * np.arange(n) / RATE)).astype(np.float32)


def _chunks(signal):
    return [signal[i:i + CHUNK] for i in range(0, len(signal) - CHUNK + 1, CHUNK)]


class _Source:
    """Plays a fixed list of chunks, then reports end-of-stream (None)."""
    def __init__(self, chunks, fail_at=None):
        self._c, self._i, self._fail = list(chunks), 0, fail_at
        self.closed = False

    def read(self):
        if self._fail is not None and self._i == self._fail:
            raise OSError('mic unplugged')
        if self._i >= len(self._c):
            return None
        c = self._c[self._i]
        self._i += 1
        return c

    def close(self):
        self.closed = True


class _Transcriber:
    def __init__(self, texts):
        self.texts, self.calls, self.gate = list(texts), 0, None

    def transcribe(self, samples, rate):
        if self.gate is not None:
            self.gate.wait(2)
        self.calls += 1
        return self.texts.pop(0) if self.texts else ''


def _wait_for(pred, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


def _silence(seconds):
    return np.zeros(int(RATE * seconds), dtype=np.float32)


def test_a_phrase_becomes_text():
    sig = np.concatenate([_silence(0.3), _tone(1.2), _silence(1.5)])
    eng = DictationEngine(_Transcriber(['hola mundo']), lambda: _Source(_chunks(sig)))
    eng.start()
    got = []
    assert _wait_for(lambda: got.extend(eng.poll()) or got)
    eng.stop()
    assert got == ['hola mundo']


def test_two_phrases_come_out_in_order():
    sig = np.concatenate([_tone(1.0), _silence(1.6), _tone(1.0), _silence(1.6)])
    eng = DictationEngine(_Transcriber(['uno', 'dos']), lambda: _Source(_chunks(sig)))
    eng.start()
    got = []
    assert _wait_for(lambda: got.extend(eng.poll()) or len(got) == 2)
    eng.stop()
    assert got == ['uno', 'dos']


def test_empty_transcriptions_are_dropped():
    sig = np.concatenate([_tone(1.0), _silence(1.6)])
    eng = DictationEngine(_Transcriber(['']), lambda: _Source(_chunks(sig)))
    eng.start()
    assert _wait_for(lambda: eng.transcriber.calls == 1 if hasattr(eng, 'transcriber') else True)
    time.sleep(0.2)
    assert eng.poll() == []
    eng.stop()


def test_listening_continues_while_a_phrase_is_being_transcribed():
    tr = _Transcriber(['uno', 'dos'])
    tr.gate = threading.Event()                    # first transcription blocks
    sig = np.concatenate([_tone(1.0), _silence(1.6), _tone(1.0), _silence(1.6)])
    src = _Source(_chunks(sig))
    eng = DictationEngine(tr, lambda: src)
    eng.start()
    assert _wait_for(lambda: src._i >= len(src._c))       # whole stream read meanwhile
    assert eng.state in ('transcribing', 'listening')
    tr.gate.set()
    got = []
    assert _wait_for(lambda: got.extend(eng.poll()) or len(got) == 2)
    eng.stop()


def test_stop_flushes_the_phrase_in_progress():
    sig = np.concatenate([_tone(1.5)])                    # no pause: only stop ends it
    src = _Source(_chunks(sig))
    eng = DictationEngine(_Transcriber(['a medias']), lambda: src)
    eng.start()
    assert _wait_for(lambda: src._i >= len(src._c))
    eng.stop()
    got = []
    assert _wait_for(lambda: got.extend(eng.poll()) or got)
    assert got == ['a medias'] and src.closed and eng.state == 'off'


def test_a_mic_failure_sets_the_error_state():
    eng = DictationEngine(_Transcriber([]), lambda: _Source(_chunks(_tone(1)), fail_at=3))
    eng.start()
    assert _wait_for(lambda: eng.state == 'error')
    assert 'mic unplugged' in eng.error
    eng.stop()


def test_state_is_off_before_start_and_after_stop():
    eng = DictationEngine(_Transcriber([]), lambda: _Source([]))
    assert eng.state == 'off'
    eng.start()
    eng.stop()
    assert eng.state == 'off'
