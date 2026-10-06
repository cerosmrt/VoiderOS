"""La voz en F5 lee el párrafo en el que estás parado.

Antes leía self.entry.text() — el renglón de F1, resto de cuando F5 era otra
vista. En F5 ese renglón ni se ve.
"""
import types
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")
from line_ring import LineRing


def test_f5_speaks_the_current_paragraph():
    from new_interface import FullscreenCircleApp as App

    class _A:
        pass
    a = _A()
    a.tts_active = True
    a.line_ring = LineRing(['.', 'uno a.', 'uno b.', '.', 'dos.'])
    a._f5_para_idx = 1
    a.entry = MagicMock()
    a.entry.text.return_value = 'lo que quedo en F1'
    a._tts_stop = MagicMock()
    a._tts_speak = MagicMock()
    for n in ('_tts_on_view', '_f5_units', '_f5_tokens', '_f5_tokens_cached'):
        setattr(a, n, types.MethodType(getattr(App, n), a))
    a._tts_on_view(4)
    a._tts_speak.assert_called_once_with('dos.')
