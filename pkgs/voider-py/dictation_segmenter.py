"""dictation_segmenter.py — cuts a mic stream into utterances for dictation.

Pure numpy, no audio device and no Qt. Feed it chunks as they arrive; when a
phrase ends (speech followed by a pause) it hands back the audio of that phrase.
The speech threshold follows the room's noise floor, so a fan or a hum is not
mistaken for a voice, and a short click never makes an utterance."""
from collections import deque

import numpy as np

MIN_THRESHOLD = 0.015        # RMS below this is never speech
NOISE_FACTOR = 3.0           # speech must be this many times louder than the room


class Segmenter:
    def __init__(self, rate=16000, silence_seconds=1.0, min_seconds=0.4,
                 max_seconds=25.0, preroll_seconds=0.3):
        self.rate = rate
        self._silence = int(silence_seconds * rate)
        self._min = int(min_seconds * rate)
        self._max = int(max_seconds * rate)
        self._preroll_n = int(preroll_seconds * rate)
        self._noise = 0.005
        self._reset()

    def _reset(self):
        self._speaking = False
        self._buf = []
        self._speech = 0
        self._quiet = 0
        self._preroll = deque()
        self._preroll_len = 0

    @staticmethod
    def _rms(chunk):
        return float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))) if len(chunk) else 0.0

    def _threshold(self):
        return max(MIN_THRESHOLD, self._noise * NOISE_FACTOR)

    def _finish(self):
        """Close the current utterance: its audio, or None if it was too short."""
        audio = np.concatenate(self._buf) if self._buf else np.zeros(0, np.float32)
        enough = self._speech >= self._min
        self._reset()
        return audio if enough else None

    def feed(self, chunk):
        """One chunk of float32 samples → a list of finished utterances (0 or 1)."""
        chunk = np.asarray(chunk, dtype=np.float32)
        level = self._rms(chunk)
        loud = level > self._threshold()
        if not self._speaking:
            if loud:
                self._speaking = True
                self._buf = list(self._preroll) + [chunk]
                self._speech, self._quiet = len(chunk), 0
                self._preroll.clear()
                self._preroll_len = 0
            else:
                self._noise = 0.95 * self._noise + 0.05 * level
                self._preroll.append(chunk)
                self._preroll_len += len(chunk)
                while self._preroll_len - len(self._preroll[0]) >= self._preroll_n:
                    self._preroll_len -= len(self._preroll.popleft())
            return []
        self._buf.append(chunk)
        if loud:
            self._speech += len(chunk)
            self._quiet = 0
        else:
            self._quiet += len(chunk)
        total = sum(len(c) for c in self._buf)
        if self._quiet >= self._silence or total >= self._max:
            audio = self._finish()
            return [audio] if audio is not None else []
        return []

    def flush(self):
        """Stop listening: hand back whatever phrase was in progress."""
        if not self._speaking:
            return []
        audio = self._finish()
        return [audio] if audio is not None else []
