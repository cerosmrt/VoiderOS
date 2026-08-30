from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QSpinBox, QPushButton, QLineEdit,
                             QFontComboBox)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, pyqtSignal


class SettingsPanel(QWidget):
    """F10 — settings panel: font family, size, text color, bg color."""

    applied = pyqtSignal(dict)   # emitted when user presses Apply

    _LABEL_STYLE = 'color:#aaaaaa; font-size:11pt;'
    _INPUT_STYLE = ('QComboBox, QSpinBox, QLineEdit, QFontComboBox {'
                    'background:#1a1a1a; color:#ffffff; border:1px solid #444;'
                    'padding:4px; font-size:11pt;}'
                    'QComboBox::drop-down, QFontComboBox::drop-down {border:none;}')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background:#0d0d0d;')
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner = QWidget()
        inner.setFixedWidth(480)
        lay = QVBoxLayout(inner)
        lay.setSpacing(18)
        lay.setContentsMargins(0, 0, 0, 0)

        title = QLabel('Settings')
        title.setStyleSheet('color:#ffffff; font-size:18pt; font-weight:bold;'
                            'margin-bottom:12px;')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        # Font family
        lay.addWidget(self._label('Font family'))
        self.font_combo = QFontComboBox()
        self.font_combo.setStyleSheet(self._INPUT_STYLE)
        lay.addWidget(self.font_combo)

        # Font size
        lay.addWidget(self._label('Font size (pt)'))
        self.size_spin = QSpinBox()
        # Sin tope arbitrario arriba: si querés la letra enorme, es tu pantalla y
        # tu texto. El 48 de antes no defendía nada — ahora que F2 escala bien el
        # espaciado, agrandar no rompe la vista. Abajo sí hay un piso: por
        # debajo de 4pt no se lee, y no se puede volver a subir sin ver nada.
        self.size_spin.setRange(4, 999)
        self.size_spin.setStyleSheet(self._INPUT_STYLE)
        lay.addWidget(self.size_spin)

        # Text color
        lay.addWidget(self._label('Text color (hex, e.g. #ffffff)'))
        self.text_color_edit = QLineEdit()
        self.text_color_edit.setPlaceholderText('#ffffff')
        self.text_color_edit.setStyleSheet(self._INPUT_STYLE)
        lay.addWidget(self.text_color_edit)

        # Background color
        lay.addWidget(self._label('Background color (hex, e.g. #000000)'))
        self.bg_color_edit = QLineEdit()
        self.bg_color_edit.setPlaceholderText('#000000')
        self.bg_color_edit.setStyleSheet(self._INPUT_STYLE)
        lay.addWidget(self.bg_color_edit)

        # Buttons
        btn_row = QHBoxLayout()
        apply_btn = QPushButton('Apply')
        apply_btn.setStyleSheet(
            'QPushButton { background:#2a2a2a; color:#ffffff; border:1px solid #555;'
            'padding:8px 24px; font-size:11pt; }'
            'QPushButton:hover { background:#3a3a3a; }'
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        lay.addLayout(btn_row)

        hint = QLabel('Press F10 or Esc to close without applying')
        hint.setStyleSheet('color:#555555; font-size:9pt;')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)

        outer.addWidget(inner)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(self._LABEL_STYLE)
        return lbl

    def load(self, config):
        """Populate fields from config dict."""
        self.font_combo.setCurrentFont(QFont(config.get('font_family', 'Consolas')))
        self.size_spin.setValue(int(config.get('font_size', 11)))
        self.text_color_edit.setText(config.get('text_color', '#ffffff'))
        self.bg_color_edit.setText(config.get('bg_color', '#000000'))

    def _on_apply(self):
        settings = {
            'font_family': self.font_combo.currentFont().family(),
            'font_size': self.size_spin.value(),
            'text_color': self.text_color_edit.text().strip() or '#ffffff',
            'bg_color': self.bg_color_edit.text().strip() or '#000000',
        }
        self.applied.emit(settings)
