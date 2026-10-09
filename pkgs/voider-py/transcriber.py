"""transcriber.py — turns a phrase of audio into text with faster-whisper.

In-process and offline: your voice never leaves the machine. The model is loaded
once (warm_up() does it ahead of the first phrase, since it takes ~30 s) and
reused for every phrase. Failures never raise: the text comes back empty and
`last_error` says why. The model loader is injectable so everything but the
model itself is testable.

(whisper.cpp was tried first; the nixpkgs build of whisper-cpp 1.7.5 here
segfaults in ggml_backend_dev_backend_reg — it ships without the CPU backend.)"""
import glob
import os
import re

import numpy as np

# What whisper prints on silence/noise, or invents out of it.
_PLACEHOLDER = re.compile(r'^\s*[\[\(\*].*[\]\)\*]\s*$')
_HALLUCINATIONS = (
    'subtítulos realizados por', 'subtitulos realizados por', 'amara.org',
    'gracias por ver', 'suscríbete', 'subtitles by', 'thanks for watching',
    'thank you for watching',
)
RATE = 16000


def clean_text(raw):
    """Join whisper's lines, drop placeholders like [BLANK_AUDIO] and the stock
    phrases it hallucinates on silence."""
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or _PLACEHOLDER.match(line):
            continue
        parts.append(line)
    text = ' '.join(parts).strip()
    low = text.lower()
    if any(h in low for h in _HALLUCINATIONS):
        return ''
    return text


def _has_lib():
    import importlib.util
    return importlib.util.find_spec('faster_whisper') is not None


def _has_model(root, size):
    """True when faster-whisper-<size> is already under `root` (no download)."""
    return bool(glob.glob(os.path.join(root, f'models--Systran--faster-whisper-{size}',
                                       'snapshots', '*', 'model.bin')))


def _load(size, root):
    from faster_whisper import WhisperModel
    return WhisperModel(size, device='cpu', compute_type='int8',
                        download_root=root, local_files_only=True)


class FasterWhisper:
    def __init__(self, model_size='small', language='es', root='', loader=_load,
                 has_lib=_has_lib, has_model=_has_model):
        self.model_size, self.language, self.root = model_size, language, root
        self._loader, self._has_lib, self._has_model = loader, has_lib, has_model
        self._model = None
        self.last_error = ''

    def available(self):
        """(True, '') when the library and the local model exist, else (False, why)."""
        if not self._has_lib():
            return False, 'falta la librería faster-whisper (python)'
        if not self._has_model(self.root, self.model_size):
            return False, f"falta el modelo '{self.model_size}' en {self.root}"
        return True, ''

    def warm_up(self):
        """Load the model now (slow) so the first phrase does not wait for it."""
        try:
            if self._model is None:
                self._model = self._loader(self.model_size, self.root)
            self.last_error = ''
        except Exception as e:
            self.last_error = str(e)

    def transcribe(self, samples, rate):
        samples = np.asarray(samples, dtype=np.float32)
        if rate != RATE and len(samples):
            n = int(len(samples) * RATE / rate)
            samples = np.interp(np.linspace(0, len(samples) - 1, n),
                                np.arange(len(samples)), samples).astype(np.float32)
        self.warm_up()
        if self._model is None:
            return ''
        try:
            segments, _info = self._model.transcribe(
                samples, language=None if self.language == 'auto' else self.language,
                beam_size=1, vad_filter=False, condition_on_previous_text=False)
            self.last_error = ''
            return clean_text('\n'.join(s.text.strip() for s in segments))
        except Exception as e:
            self.last_error = str(e)
            return ''
