import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH to a per-test temp file in every module that holds it,
    so no test can ever write the real proto-voider/config.json. Tests carry tiny
    stub configs; without this a save-path (e.g. switch_to_view, rename) truncates
    the user's live config (void_dir, keybindings, active_file)."""
    cfg = str(tmp_path / 'config.json')
    import app_config
    monkeypatch.setattr(app_config, 'CONFIG_PATH', cfg, raising=False)
    if 'new_interface' in sys.modules:
        monkeypatch.setattr(sys.modules['new_interface'], 'CONFIG_PATH', cfg,
                            raising=False)
    yield
