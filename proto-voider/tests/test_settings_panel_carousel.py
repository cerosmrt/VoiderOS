"""F10 — fila nueva: ratio del carrusel de Instagram (F4 / Ctrl+Shift+C)."""
import pytest

from PyQt6.QtWidgets import QApplication

from settings_panel import SettingsPanel


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


def _panel(qapp):
    return SettingsPanel()


def test_load_selects_the_configured_preset(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': '1:1'})
    assert p.carousel_preset_combo.currentText() == '1:1'


def test_load_selects_custom_and_fills_dimensions(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': 'custom', 'carousel_w': 800, 'carousel_h': 600})
    assert p.carousel_preset_combo.currentText() == 'Custom'
    assert p.carousel_w_spin.value() == 800
    assert p.carousel_h_spin.value() == 600


def test_load_defaults_to_4_5_when_unset(qapp):
    p = _panel(qapp)
    p.load({})
    assert p.carousel_preset_combo.currentText() == '4:5'


def test_apply_emits_the_selected_preset(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': '1.91:1'})
    got = {}
    p.applied.connect(lambda s: got.update(s))
    p._on_apply()
    assert got['carousel_preset'] == '1.91:1'


def test_apply_emits_custom_dimensions(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': 'custom', 'carousel_w': 900, 'carousel_h': 900})
    got = {}
    p.applied.connect(lambda s: got.update(s))
    p._on_apply()
    assert got['carousel_preset'] == 'custom'
    assert got['carousel_w'] == 900
    assert got['carousel_h'] == 900


def test_dimension_spinners_disabled_unless_custom(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': '4:5'})
    assert not p.carousel_w_spin.isEnabled()
    assert not p.carousel_h_spin.isEnabled()


def test_dimension_spinners_enabled_on_custom(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': 'custom'})
    assert p.carousel_w_spin.isEnabled()
    assert p.carousel_h_spin.isEnabled()


def test_selecting_custom_in_the_ui_enables_the_spinners(qapp):
    p = _panel(qapp)
    p.load({'carousel_preset': '4:5'})
    p.carousel_preset_combo.setCurrentText('Custom')
    assert p.carousel_w_spin.isEnabled()
    assert p.carousel_h_spin.isEnabled()
