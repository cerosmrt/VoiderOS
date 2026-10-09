"""Remapped keys live in their own keybindings.json (only what you changed), so a
new build with new/changed defaults never overwrites your remaps — and never
freezes old defaults into config.json."""
import json

from app_config import DEFAULT_CONFIG, _load_config_from, _save_config_to


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding='utf-8')


def test_defaults_when_there_are_no_overrides(tmp_path):
    cfg = _load_config_from(str(tmp_path / 'config.json'))
    assert cfg['keybindings'] == DEFAULT_CONFIG['keybindings']


def test_keybindings_json_overrides_a_default(tmp_path):
    _write(tmp_path / 'keybindings.json', {'help': 'F1'})
    cfg = _load_config_from(str(tmp_path / 'config.json'))
    assert cfg['keybindings']['help'] == 'F1'
    assert cfg['keybindings']['view_f2'] == DEFAULT_CONFIG['keybindings']['view_f2']


def test_keybindings_json_wins_over_legacy_config_json(tmp_path):
    _write(tmp_path / 'config.json', {'keybindings': {'help': 'F5'}})
    _write(tmp_path / 'keybindings.json', {'help': 'F6'})
    cfg = _load_config_from(str(tmp_path / 'config.json'))
    assert cfg['keybindings']['help'] == 'F6'


def test_broken_keybindings_json_is_ignored(tmp_path):
    (tmp_path / 'keybindings.json').write_text('{not json', encoding='utf-8')
    cfg = _load_config_from(str(tmp_path / 'config.json'))
    assert cfg['keybindings'] == DEFAULT_CONFIG['keybindings']


def test_save_does_not_freeze_default_keys_into_config_json(tmp_path):
    path = str(tmp_path / 'config.json')
    cfg = _load_config_from(path)
    cfg['font_size'] = 21
    _save_config_to(path, cfg)
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['font_size'] == 21
    assert saved.get('keybindings', {}) == {}


def test_save_keeps_overrides_out_of_config_json_and_in_their_file(tmp_path):
    path = str(tmp_path / 'config.json')
    _write(tmp_path / 'keybindings.json', {'help': 'F1'})
    cfg = _load_config_from(path)
    _save_config_to(path, cfg)
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved.get('keybindings', {}) == {}
    assert json.loads((tmp_path / 'keybindings.json').read_text()) == {'help': 'F1'}
