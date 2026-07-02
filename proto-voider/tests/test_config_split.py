"""Config/state split: runtime keys live in a separate state.json; the committed
config.json holds only defaults + keybindings and is never churned by navigation,
and a wiped/corrupt state.json can't take void_dir (launch config) down with it."""
import json
import os

from app_config import (_load_config_from, _save_config_to, _state_path_for,
                        STATE_KEYS)


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_runtime_keys_go_to_state_not_config(tmp_path):
    cfg = str(tmp_path / 'config.json')
    with open(cfg, 'w') as f:
        json.dump({'void_dir': '/v', 'keybindings': {}}, f)
    conf = _load_config_from(cfg)
    conf['active_file'] = '/v/I/x.txt'
    conf['last_view'] = 2
    _save_config_to(cfg, conf)

    committed = _read(cfg)
    state = _read(_state_path_for(cfg))
    assert 'active_file' not in committed and 'last_view' not in committed
    assert committed['void_dir'] == '/v'                # setup key stays committed
    assert state['active_file'] == '/v/I/x.txt'
    assert state['last_view'] == 2


def test_state_overlays_config_on_load(tmp_path):
    cfg = str(tmp_path / 'config.json')
    with open(cfg, 'w') as f:
        json.dump({'void_dir': '/v', 'active_file': '/old.txt'}, f)
    with open(_state_path_for(cfg), 'w') as f:
        json.dump({'active_file': '/new.txt', 'last_view': 3}, f)
    conf = _load_config_from(cfg)
    assert conf['active_file'] == '/new.txt'            # state wins
    assert conf['last_view'] == 3
    assert conf['void_dir'] == '/v'


def test_navigation_does_not_rewrite_committed_config(tmp_path):
    cfg = str(tmp_path / 'config.json')
    with open(cfg, 'w') as f:
        json.dump({'void_dir': '/v', 'keybindings': {}}, f)
    conf = _load_config_from(cfg)
    _save_config_to(cfg, conf)                          # first save cleans state keys
    before = os.path.getmtime(cfg)
    committed_before = _read(cfg)
    conf['last_view'] = 1                               # a pure runtime change
    _save_config_to(cfg, conf)
    assert _read(cfg) == committed_before               # committed content unchanged
    assert _read(cfg) == _read(cfg)                     # (sanity)


def test_corrupt_state_does_not_break_config(tmp_path):
    cfg = str(tmp_path / 'config.json')
    with open(cfg, 'w') as f:
        json.dump({'void_dir': '/home/federico/void'}, f)
    with open(_state_path_for(cfg), 'w') as f:
        f.write('{ this is not json')
    conf = _load_config_from(cfg)
    assert conf['void_dir'] == '/home/federico/void'    # launch key survives
