"""C: headless boot self-test. Construct the real FullscreenCircleApp offscreen
and cycle through F1–F5, asserting no exceptions. Catches import/wiring/mixin
regressions (the kind that broke launch this session) without a real display.

Isolation: config is redirected to a temp file by the autouse conftest fixture;
void_dir points at a temp /void; the IPC socket name is uniquified so the test
never attaches to a running Voider instance.
"""
import json
import uuid

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def void(tmp_path):
    v = tmp_path / "void"
    (v / "I").mkdir(parents=True)
    (v / "I" / "0.txt").write_text(".\nhello\n.\nworld\n", encoding="utf-8")
    (v / "I" / "chap.txt").write_text(".\nalpha\n/Seccion\nbeta\n", encoding="utf-8")
    with open(v / "I.txt", "w", encoding="utf-8") as f:
        f.write("0.txt\n.\nchap.txt\n")
    return v


def test_boot_and_cycle_views(qapp, void, monkeypatch):
    # Unique IPC name so we never join a running Voider's channel.
    import ipc
    monkeypatch.setattr(ipc, "_SERVER_NAME", f"voider_test_{uuid.uuid4().hex}")

    import app_config
    cfg = {"void_dir": str(void), "book_dir": str(void / "I"),
           "font_family": "Consolas", "font_size": 11, "keybindings": {}}
    with open(app_config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)

    from new_interface import FullscreenCircleApp
    app = FullscreenCircleApp()
    try:
        # F1..F5 and back — every view builds and switches cleanly.
        for v in (0, 1, 2, 3, 4, 2, 1, 0):
            app.switch_to_view(v)
            assert app.current_view == v
    finally:
        app.close()
