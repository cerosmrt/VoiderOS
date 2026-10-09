"""dictation_engine.py — always-on listening that turns speech into text.

Two threads: one reads the microphone and cuts it into phrases (so listening
never stops), the other transcribes each phrase (a few seconds each with
whisper). Finished text waits in a queue that the UI polls — no Qt in here.
Nothing opens the mic until start()."""
import queue
import sys
import threading

from dictation_segmenter import Segmenter

RATE = 16000
CHUNK = 512


class PyAudioSource:
    """The default microphone at 16 kHz mono float32 (what whisper wants)."""

    def __init__(self):
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paFloat32, channels=1, rate=RATE,
                                     input=True, frames_per_buffer=CHUNK)

    def read(self):
        import numpy as np
        return np.frombuffer(self._stream.read(CHUNK, exception_on_overflow=False),
                             dtype=np.float32)

    def close(self):
        try:
            self._stream.close()
            self._pa.terminate()
        except Exception:
            pass


class DictationEngine:
    def __init__(self, transcriber, source_factory=PyAudioSource):
        self.transcriber = transcriber
        self._factory = source_factory
        self._texts = queue.Queue()
        self._phrases = queue.Queue()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._busy = 0                 # phrases waiting or being transcribed
        self._loading = False          # the model is being loaded (first start: ~30 s)
        self.error = ''

    @property
    def state(self):
        if self.error:
            return 'error'
        if not self._running:
            return 'off'
        if self._loading:
            return 'loading'
        return 'transcribing' if self._busy else 'listening'

    def start(self):
        if self._running:
            return
        self.error = ''
        self._stop = threading.Event()
        self._phrases = queue.Queue()
        self._running = True
        self._loading = hasattr(self.transcriber, 'warm_up')
        threading.Thread(target=self._listen, args=(self._stop, self._phrases),
                         daemon=True).start()
        threading.Thread(target=self._transcribe, args=(self._phrases,),
                         daemon=True).start()

    def stop(self):
        """Stop listening now; a phrase already heard is still transcribed in the
        background and shows up in poll()."""
        self._stop.set()
        self._running = False

    def poll(self):
        """Texts finished since the last call, oldest first."""
        out = []
        while True:
            try:
                out.append(self._texts.get_nowait())
            except queue.Empty:
                return out

    def _add_busy(self, n):
        with self._lock:
            self._busy += n

    def _listen(self, stop, phrases):
        src = None
        try:
            src = self._factory()
            seg = Segmenter(RATE)
            while not stop.is_set():
                chunk = src.read()
                if chunk is None:                         # end of stream
                    break
                for audio in seg.feed(chunk):
                    self._add_busy(1)
                    phrases.put(audio)
            for audio in seg.flush():
                self._add_busy(1)
                phrases.put(audio)
        except Exception as e:                            # no mic, PipeWire gone…
            self.error = str(e)
            print(f"Dictation: {e}", file=sys.stderr)
        finally:
            if src is not None:
                try:
                    src.close()
                except Exception:
                    pass
            phrases.put(None)

    def _transcribe(self, phrases):
        warm = getattr(self.transcriber, 'warm_up', None)
        if warm is not None:
            try:
                warm()
            except Exception as e:
                print(f"Dictation: {e}", file=sys.stderr)
            self._loading = False
        while True:
            audio = phrases.get()
            if audio is None:
                return
            try:
                text = self.transcriber.transcribe(audio, RATE)
            except Exception as e:
                text = ''
                print(f"Dictation: {e}", file=sys.stderr)
            if text:
                self._texts.put(text)
            self._add_busy(-1)
