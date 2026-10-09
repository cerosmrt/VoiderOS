"""transcriber.py — turns a phrase of audio into text with whisper.cpp.

Runs the `whisper-cli` binary (offline: your voice never leaves the machine) on a
temporary WAV and cleans up what it prints. The subprocess runner is injectable
so everything but the model itself is testable. Failures never raise: the text
comes back empty and `last_error` says why."""
import os
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np

BINARY = 'whisper-cli'

# What whisper prints on silence/noise, or invents out of it.
_PLACEHOLDER = re.compile(r'^\s*[\[\(\*].*[\]\)\*]\s*$')
_HALLUCINATIONS = (
    'subtítulos realizados por', 'subtitulos realizados por', 'amara.org',
    'gracias por ver', 'suscríbete', 'subtitles by', 'thanks for watching',
    'thank you for watching',
)


def write_wav(path, samples, rate):
    """float32 -1..1 → 16-bit mono WAV, clipped (never wrapped)."""
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


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


def _run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout if p.returncode == 0 else (p.stderr or p.stdout))


class WhisperCli:
    def __init__(self, model, language='es', threads=4, runner=_run, which=shutil.which):
        self.model, self.language, self.threads = model, language, threads
        self._run, self._which = runner, which
        self.last_error = ''

    def available(self):
        """(True, '') when the binary and the model exist, else (False, why)."""
        if not self._which(BINARY):
            return False, f"falta {BINARY} (whisper-cpp) en el PATH"
        if not os.path.isfile(self.model):
            return False, f"falta el modelo: {self.model}"
        return True, ''

    def transcribe(self, samples, rate):
        fd, wav = tempfile.mkstemp(suffix='.wav', prefix='voider-dictation-')
        os.close(fd)
        try:
            write_wav(wav, samples, rate)
            cmd = [BINARY, '-m', self.model, '-l', self.language, '-t', str(self.threads),
                   '-nt', '-np', '-f', wav]
            try:
                code, out = self._run(cmd)
            except OSError as e:
                self.last_error = f"{BINARY}: {e}"
                return ''
            if code != 0:
                self.last_error = (out or '').strip()[-300:]
                return ''
            self.last_error = ''
            return clean_text(out)
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass
