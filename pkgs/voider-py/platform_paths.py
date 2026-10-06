# platform_paths.py — paths that used to be spelled the Linux way.
#
# /tmp/voider-fx, /tmp/voider-fx-panel and ~/void/tts/*.onnx do not exist on Windows.
# One place now says where those live, so a different platform (or a different void)
# changes it in one line.
import os
import tempfile


def tmp_file(name):
    """A file in the system's temp folder (/tmp on Linux, %TEMP% on Windows)."""
    return os.path.join(tempfile.gettempdir(), name)


# The voice models Voider speaks with, by language, inside <void>/tts/.
_TTS_MODEL_FILES = {
    'en': 'en_GB-alan-medium.onnx',
    'es': 'es_ES-sharvard-medium.onnx',
    'it': 'it_IT-riccardo-x_low.onnx',
}


def tts_models(void_dir):
    """Where each language's voice model is: under the configured void, not under ~.
    With no void configured, the old default (~/void) so nothing else changes."""
    base = os.path.join(void_dir or os.path.expanduser('~/void'), 'tts')
    return {lang: os.path.join(base, name) for lang, name in _TTS_MODEL_FILES.items()}
