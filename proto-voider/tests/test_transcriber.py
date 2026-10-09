"""WhisperCli: audio → WAV → whisper-cli → clean text. The subprocess is injected,
so no model or binary is needed here."""
import wave

import numpy as np

from transcriber import WhisperCli, clean_text, write_wav


def test_write_wav_is_16bit_mono_at_the_given_rate(tmp_path):
    path = tmp_path / 'a.wav'
    write_wav(str(path), np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32), 16000)
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 4)


def test_write_wav_clips_instead_of_wrapping(tmp_path):
    path = tmp_path / 'a.wav'
    write_wav(str(path), np.array([2.0, -2.0], dtype=np.float32), 16000)
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(2), dtype=np.int16)
    assert data[0] == 32767 and data[1] <= -32767


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


def test_command_uses_model_language_and_quiet_flags(tmp_path):
    seen = {}

    def runner(cmd, **kw):
        seen['cmd'] = cmd
        return 0, "hola\n"

    t = WhisperCli(model='/m/ggml-small.bin', language='es', runner=runner)
    assert t.transcribe(np.zeros(1600, dtype=np.float32), 16000) == 'hola'
    cmd = seen['cmd']
    assert cmd[0] == 'whisper-cli'
    assert cmd[cmd.index('-m') + 1] == '/m/ggml-small.bin'
    assert cmd[cmd.index('-l') + 1] == 'es'
    assert '-nt' in cmd and '-np' in cmd
    assert cmd[cmd.index('-f') + 1].endswith('.wav')


def test_auto_language_is_passed_to_whisper_as_auto():
    seen = {}
    t = WhisperCli(model='m', language='auto',
                   runner=lambda cmd, **kw: (seen.update(cmd=cmd) or (0, 'x')))
    t.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert seen['cmd'][seen['cmd'].index('-l') + 1] == 'auto'


def test_failure_gives_empty_text_and_remembers_the_error():
    t = WhisperCli(model='m', language='es', runner=lambda cmd, **kw: (1, 'boom'))
    assert t.transcribe(np.zeros(1600, dtype=np.float32), 16000) == ''
    assert 'boom' in t.last_error


def test_missing_binary_is_reported_not_raised():
    def runner(cmd, **kw):
        raise FileNotFoundError('whisper-cli')

    t = WhisperCli(model='m', language='es', runner=runner)
    assert t.transcribe(np.zeros(1600, dtype=np.float32), 16000) == ''
    assert 'whisper-cli' in t.last_error


def test_temp_wav_is_removed_afterwards(tmp_path):
    import os
    seen = {}

    def runner(cmd, **kw):
        seen['wav'] = cmd[cmd.index('-f') + 1]
        assert os.path.exists(seen['wav'])
        return 0, 'hola'

    WhisperCli(model='m', language='es', runner=runner).transcribe(
        np.zeros(1600, dtype=np.float32), 16000)
    assert not os.path.exists(seen['wav'])


def test_availability_checks_binary_and_model(tmp_path):
    model = tmp_path / 'm.bin'
    t = WhisperCli(model=str(model), language='es', which=lambda b: None)
    ok, why = t.available()
    assert not ok and 'whisper-cli' in why
    t = WhisperCli(model=str(model), language='es', which=lambda b: '/bin/whisper-cli')
    ok, why = t.available()
    assert not ok and 'm.bin' in why
    model.write_bytes(b'x')
    assert t.available() == (True, '')
