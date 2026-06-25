# tts_mixin.py — TTS methods
import os
import subprocess
import threading


class TtsMixin:

    _TTS_MODELS = {
        'en': os.path.expanduser('~/void/tts/en_GB-alan-medium.onnx'),
        'es': os.path.expanduser('~/void/tts/es_ES-sharvard-medium.onnx'),
        'it': os.path.expanduser('~/void/tts/it_IT-riccardo-x_low.onnx'),
    }

    def _detect_lang(self, text):
        try:
            from langdetect import detect
            lang = detect(text)
            return lang if lang in self._TTS_MODELS else 'en'
        except Exception:
            return 'en'

    def _tts_speak(self, text):
        if not text or text == '.':
            return
        self._tts_stop_proc()
        # Use prefetched audio if available
        if self._tts_prefetch_text == text and self._tts_prefetch_data:
            try:
                aplay = subprocess.Popen(
                    ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                data = self._tts_prefetch_data
                self._tts_prefetch_data = None
                self._tts_prefetch_text = None
                # Write in background — pipe buffer blocks main thread otherwise
                def _pipe(proc, buf):
                    try:
                        proc.stdin.write(buf)
                        proc.stdin.close()
                    except Exception:
                        pass
                threading.Thread(target=_pipe, args=(aplay, data), daemon=True).start()
                self._tts_process = aplay
                self._tts_piper = None
                return
            except Exception:
                pass
        lang = self._detect_lang(text)
        model = self._TTS_MODELS.get(lang, self._TTS_MODELS['en'])
        if not os.path.exists(model):
            print(f"⚠️ TTS model not found: {model}")
            return
        try:
            piper = subprocess.Popen(
                ['piper', '--model', model, '--length_scale', '1.15', '--output_raw'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            aplay = subprocess.Popen(
                ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
                stdin=piper.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            piper.stdin.write(text.encode('utf-8', errors='replace'))
            piper.stdin.close()
            piper.stdout.close()
            self._tts_process = aplay
            self._tts_piper  = piper
        except FileNotFoundError as e:
            print(f"⚠️ TTS error: {e}")

    def _tts_stop_proc(self):
        for proc in (getattr(self, '_tts_piper', None), self._tts_process):
            if proc and proc.poll() is None:
                proc.terminate()
        self._tts_process = None
        self._tts_piper   = None

    def _tts_prefetch(self, text):
        """Pre-render next line's audio in background so playback is gapless."""
        if not text or text in ('.', '') or text == self._tts_prefetch_text:
            return
        self._tts_prefetch_text = text
        self._tts_prefetch_data = None
        lang = self._detect_lang(text)
        model = self._TTS_MODELS.get(lang, self._TTS_MODELS['en'])
        def _fetch():
            try:
                piper = subprocess.Popen(
                    ['piper', '--model', model, '--length_scale', '1.15', '--output_raw'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                data, _ = piper.communicate(text.encode('utf-8', errors='replace'))
                self._tts_prefetch_data = data
            except Exception:
                self._tts_prefetch_data = b''
        threading.Thread(target=_fetch, daemon=True).start()

    def _tts_stop(self):
        self._tts_timer.stop()
        self._tts_stop_proc()

    def _tts_cut(self):
        """Stop TTS when the user navigates — keeps tts_active False so it won't auto-resume."""
        if getattr(self, 'tts_active', False):
            self.tts_active = False
            self._tts_stop()

    def _tts_toggle(self):
        self.tts_active = not self.tts_active
        if not self.tts_active:
            self._tts_stop()
            print("🔇 TTS off")
        else:
            print("🔊 TTS on")
            self._tts_on_view(self.current_view)

    def _tts_on_view(self, view_index):
        """Start TTS behaviour appropriate for the given view."""
        if not self.tts_active:
            return
        self._tts_stop()
        if view_index == 0:                          # F1 — single line
            self._tts_speak(self.line_ring.current())
        elif view_index == 1:                        # F2 — sequential through I/
            cur = self.line_ring.current()
            if cur != '.':
                self._tts_speak(cur)
            self._tts_timer.start()
        elif view_index == 4:                        # F5 — single O/ line
            self._tts_speak(self.entry.text())
        elif view_index == 5:                        # F6 — sequential through O/ book
            cur = self.o_reader_ring.current()
            if cur not in ('.', ''):
                self._tts_speak(cur)
            self._tts_timer.start()
        # F4 (reading view) has no TTS — it's a visual prose render
        elif view_index == 7:                        # F8 — oracle O/
            self._tts_speak(self.oracle_o_ring.current())

    def _tts_poll(self):
        """Poll every 50ms; when aplay finishes, advance and speak next line."""
        if not self.tts_active:
            self._tts_timer.stop()
            return
        if self._tts_process and self._tts_process.poll() is None:
            return  # still speaking
        if self.current_view == 1:                   # F2 sequential
            self.line_ring.move(1)
            while self.line_ring.current() == '.':
                self.line_ring.move(1)
            if self.circular_view:
                self.circular_view._offset = 0.0
                self.circular_view.editor.setText(self.line_ring.current())
                self.circular_view.update()
            self._tts_speak(self.line_ring.current())
            # Prefetch the line after this one
            lines = self.line_ring.lines
            idx = self.line_ring.index
            peek = (idx + 1) % len(lines)
            while lines[peek] == '.' and peek != idx:
                peek = (peek + 1) % len(lines)
            self._tts_prefetch(lines[peek])
        elif self.current_view == 5:                 # F6 sequential
            self.o_reader_ring.move(1)
            while self.o_reader_ring.current() in ('.', ''):
                self.o_reader_ring.move(1)
            if self.o_reader_view:
                self.o_reader_view._offset = 0.0
                self.o_reader_view.editor.setText(self.o_reader_ring.current())
                self.o_reader_view.update()
            self._tts_speak(self.o_reader_ring.current())
            # Prefetch the line after this one
            lines = self.o_reader_ring.lines
            idx = self.o_reader_ring.index
            peek = (idx + 1) % len(lines)
            while lines[peek] in ('.', '') and peek != idx:
                peek = (peek + 1) % len(lines)
            self._tts_prefetch(lines[peek])
        else:
            self._tts_timer.stop()
