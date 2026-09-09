"""Ctrl+Shift+X abre la basura como archivo activo en F2.

trash.txt no es más que un archivo en I/, así que abrirlo es apuntar F2 ahí —
lo mismo que haría Ctrl+F2 eligiéndolo a mano, pero sin el diálogo. Desde
adentro, Ctrl+Delete sobre una línea la devuelve a 0.txt.
"""
import os
import types
import pytest
from unittest.mock import MagicMock


def _app(tmp_path, make_file=True):
    from new_interface import FullscreenCircleApp

    class _App:
        pass

    app = _App()
    app.void_dir = str(tmp_path)
    os.makedirs(tmp_path / 'I', exist_ok=True)
    trash = tmp_path / 'I' / 'trash.txt'
    if make_file:
        trash.write_text('una linea tirada.\n', encoding='utf-8')
    app._trash_file = str(trash)
    app._set_f2_file = MagicMock()
    app.switch_to_view = MagicMock()
    app.open_trash = types.MethodType(FullscreenCircleApp.open_trash, app)
    return app, trash


def test_it_points_f2_at_the_trash_file(tmp_path):
    app, trash = _app(tmp_path)
    app.open_trash()
    app._set_f2_file.assert_called_once_with(str(trash))
    app.switch_to_view.assert_called_once_with(1)


def test_an_empty_trash_is_created_rather_than_failing(tmp_path):
    """Nunca tiraste nada todavía: abrir la basura no puede explotar."""
    app, trash = _app(tmp_path, make_file=False)
    app.open_trash()
    assert trash.exists()
    app._set_f2_file.assert_called_once_with(str(trash))


def test_it_falls_back_to_the_void_when_no_trash_path_is_set(tmp_path):
    app, trash = _app(tmp_path)
    del app._trash_file
    app.open_trash()
    app._set_f2_file.assert_called_once_with(
        os.path.join(str(tmp_path), 'I', 'trash.txt'))


def test_the_key_is_bound_and_collides_with_nothing():
    from app_config import DEFAULT_CONFIG, _parse_keybinding
    kb = DEFAULT_CONFIG['keybindings']
    assert kb['open_trash'] == 'Ctrl+Shift+X'
    parsed = [_parse_keybinding(v) for v in kb.values()]
    assert parsed.count(_parse_keybinding(kb['open_trash'])) == 1
