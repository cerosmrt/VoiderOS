"""El tamaño de fuente no tiene tope arbitrario arriba.

Estaba limitado a 48pt. No defendía nada: F2 ya escala bien el espaciado, así
que agrandar no rompe la vista. Si alguien quiere la letra enorme, es su
pantalla y su texto.

Abajo sí hay un piso, y ése es real: por debajo de unos pocos puntos no se lee
nada, incluido el propio panel para volver a subirla.
"""
import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from settings_panel import SettingsPanel


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_se_puede_pasar_de_48(qapp):
    p = SettingsPanel()
    p.size_spin.setValue(72)
    assert p.size_spin.value() == 72, "sigue topado"


def test_se_puede_ir_mucho_mas_arriba(qapp):
    p = SettingsPanel()
    p.size_spin.setValue(200)
    assert p.size_spin.value() == 200


def test_abajo_hay_un_piso_para_no_quedarse_sin_ver(qapp):
    p = SettingsPanel()
    p.size_spin.setValue(0)
    assert p.size_spin.value() >= 4, "0pt es invisible, incluido este panel"
