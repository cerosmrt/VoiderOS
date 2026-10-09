"""Voice-activity segmentation for dictation: cut the mic stream into utterances
(speech followed by a pause), ignore clicks and room noise."""
import numpy as np

from dictation_segmenter import Segmenter

RATE = 16000
CHUNK = 512


def _tone(seconds, amp=0.3, freq=220.0):
    n = int(RATE * seconds)
    t = np.arange(n) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _silence(seconds, amp=0.0):
    n = int(RATE * seconds)
    rng = np.random.default_rng(0)
    return (amp * rng.standard_normal(n)).astype(np.float32)


def _run(seg, signal):
    out = []
    for i in range(0, len(signal) - CHUNK + 1, CHUNK):
        out += seg.feed(signal[i:i + CHUNK])
    return out


def test_silence_gives_nothing():
    assert _run(Segmenter(RATE), _silence(5)) == []


def test_speech_then_a_pause_gives_one_utterance():
    out = _run(Segmenter(RATE), np.concatenate([_silence(0.5), _tone(1.5), _silence(1.5)]))
    assert len(out) == 1
    assert 1.5 <= len(out[0]) / RATE <= 3.5          # the speech, with a little padding


def test_a_short_click_is_ignored():
    out = _run(Segmenter(RATE), np.concatenate([_silence(0.5), _tone(0.1), _silence(2.0)]))
    assert out == []


def test_two_phrases_make_two_utterances():
    sig = np.concatenate([_tone(1.0), _silence(1.6), _tone(1.0), _silence(1.6)])
    assert len(_run(Segmenter(RATE), sig)) == 2


def test_a_short_pause_inside_a_phrase_does_not_split_it():
    sig = np.concatenate([_tone(1.0), _silence(0.4), _tone(1.0), _silence(1.6)])
    assert len(_run(Segmenter(RATE), sig)) == 1


def test_steady_room_noise_is_not_speech():
    sig = np.concatenate([_silence(3, amp=0.01)])
    assert _run(Segmenter(RATE), sig) == []


def test_speech_over_background_noise_is_still_detected():
    noise = _silence(4, amp=0.01)
    sig = np.concatenate([noise, _tone(1.5) + _silence(1.5, amp=0.01), noise])
    assert len(_run(Segmenter(RATE), sig)) == 1


def test_endless_speech_is_cut_at_the_maximum_length():
    seg = Segmenter(RATE, max_seconds=5.0)
    out = _run(seg, _tone(12))
    assert len(out) >= 2
    assert all(len(u) / RATE <= 6.0 for u in out)


def test_flush_returns_the_pending_utterance_on_stop():
    seg = Segmenter(RATE)
    assert _run(seg, _tone(1.5)) == []              # no pause yet
    out = seg.flush()
    assert len(out) == 1 and len(out[0]) / RATE >= 1.4
    assert seg.flush() == []
