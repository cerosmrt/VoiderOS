"""FasterWhisper: audio → text in-process (model loaded once). The model is
injected, so no download and no library are needed here."""
from types import SimpleNamespace

import numpy as np

from transcriber import FasterWhisper, clean_text


class _Model:
    def __init__(self, texts):
        self.texts, self.calls = texts, []

    def transcribe(self, audio, **kw):
        self.calls.append((audio, kw))
        return [SimpleNamespace(text=t) for t in self.texts], SimpleNamespace(language='es')


def _t(model=None, language='es', **kw):
    model = model or _Model([' hola ', ' mundo'])
    loads = []

    def loader(size, root):
        loads.append((size, root))
        return model
    t = FasterWhisper(model_size='small', language=language, root='/r', loader=loader, **kw)
    t._loads = loads
    return t, model


def test_clean_text_joins_lines_and_trims():
    assert clean_text("  hola mundo \n  cómo estás\n") == "hola mundo cómo estás"


def test_clean_text_drops_whisper_placeholders():
    assert clean_text("[BLANK_AUDIO]") == ""
    assert clean_text(" (música) ") == ""
    assert clean_text("[Música]\nhola") == "hola"
    assert clean_text("*aplausos*") == ""


def test_clean_text_drops_known_silence_hallucinations():
    assert clean_text("Subtítulos realizados por la comunidad de Amara.org") == ""
    assert clean_text("Gracias por ver el video.") == ""


def test_segments_are_joined_into_one_text():
    t, _ = _t()
    assert t.transcribe(np.zeros(1600, dtype=np.float32), 16000) == 'hola mundo'


def test_language_is_passed_and_auto_means_detect():
    t, m = _t(language='es')
    t.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert m.calls[0][1]['language'] == 'es'
    t, m = _t(language='auto')
    t.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert m.calls[0][1]['language'] is None


def test_model_is_loaded_once_and_reused():
    t, _ = _t()
    for _ in range(3):
        t.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert t._loads == [('small', '/r')]


def test_warm_up_loads_the_model_ahead_of_the_first_phrase():
    t, _ = _t()
    t.warm_up()
    assert t._loads == [('small', '/r')]
    t.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert len(t._loads) == 1


def test_audio_is_resampled_to_16k_when_given_another_rate():
    t, m = _t()
    t.transcribe(np.zeros(4410, dtype=np.float32), 44100)
    assert len(m.calls[0][0]) == 1600


def test_a_loader_or_model_failure_gives_empty_text_and_an_error():
    def loader(size, root):
        raise RuntimeError('no model files')
    t = FasterWhisper(model_size='small', language='es', root='/r', loader=loader)
    assert t.transcribe(np.zeros(1600, dtype=np.float32), 16000) == ''
    assert 'no model files' in t.last_error


def test_availability_needs_the_library_and_the_local_model():
    t = FasterWhisper(model_size='small', root='/r', has_lib=lambda: False,
                      has_model=lambda root, size: True)
    ok, why = t.available()
    assert not ok and 'faster-whisper' in why
    t = FasterWhisper(model_size='small', root='/r', has_lib=lambda: True,
                      has_model=lambda root, size: False)
    ok, why = t.available()
    assert not ok and 'small' in why and '/r' in why
    t = FasterWhisper(model_size='small', root='/r', has_lib=lambda: True,
                      has_model=lambda root, size: True)
    assert t.available() == (True, '')
