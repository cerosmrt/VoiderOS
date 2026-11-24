# commands_mixin.py — los comandos de F1 (`!rem …`) que actúan sobre el texto de F2.
#
# La lógica pura está en f1_commands.py; acá está lo que toca el archivo y los avisos.
import os

import f1_commands
import gravitor
from i18n import t


class CommandsMixin:

    def _f1_command(self, name, args):
        """Despachar un comando de F1. Uno desconocido avisa y no escribe nada."""
        if name == 'rem':
            self._cmd_rem(args)
            return
        if name == 'sinpuntos':
            self._cmd_sinpuntos()
            return
        self._cmd_unknown(name)

    def _cmd_unknown(self, name):
        self._cmd_message(f'No conozco el comando !{name}.\n\n'
                          'Los que existen:\n  !rem <palabras>\n  !sinpuntos', warn=True)

    def _cmd_rem_apply(self, args):
        """`!rem <palabras>`: del archivo de F2, borrar las líneas que NO tienen las
        palabras. → (estado, quedaron, había); estado: 'ok', 'noquery', 'missing',
        'nomatch' o 'error'. Sin Qt: se prueba solo."""
        query = gravitor.parse_query(args)
        if query is None:
            return ('noquery', 0, 0)
        path = self.f2_file
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.rstrip('\n') for l in f]
        except OSError:
            return ('missing', 0, 0)
        out = f1_commands.remove_lines_without(lines, query)
        if out is None:
            return ('nomatch', 0, f1_commands.count_lines(lines))
        # Un solo paso de deshacer (Ctrl+Z en F2) y un .bak del archivo anterior.
        self._undo_begin()
        ok = self._atomic_write_lines(path, out.lines, backup=True)
        self._undo_commit(key=('rem', path))
        if not ok:
            return ('error', 0, out.total)
        if os.path.abspath(self.current_file_path) == os.path.abspath(path):
            self.load_doc_lines()
        return ('ok', out.kept, out.total)

    def _cmd_rem(self, args):
        status, kept, total = self._cmd_rem_apply(args)
        name = os.path.basename(self.f2_file)
        text = {
            'ok': t('cmd.rem.ok', kept=kept, total=total, name=name),
            'noquery': t('cmd.rem.noquery'),
            'missing': t('cmd.missing', name=name),
            'nomatch': t('cmd.rem.nomatch', total=total, name=name, args=args),
            'error': t('cmd.error', name=name),
        }[status]
        self._cmd_message(text, warn=(status != 'ok'))

    def _cmd_sinpuntos_apply(self):
        """`!sinpuntos`: del archivo de F2, quitar los separadores (las líneas que son
        sólo un punto); queda un solo párrafo. → (estado, separadores quitados,
        líneas); estado: 'ok', 'same' (ya era un párrafo), 'empty', 'missing' o
        'error'. Sin Qt: se prueba solo."""
        path = self.f2_file
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.rstrip('\n') for l in f]
        except OSError:
            return ('missing', 0, 0)
        out = f1_commands.remove_separators(lines)
        if out is None:
            return ('empty', 0, 0)
        if out.lines == [l.strip() for l in lines if l.strip()]:
            return ('same', 0, out.kept)
        self._undo_begin()
        ok = self._atomic_write_lines(path, out.lines, backup=True)
        self._undo_commit(key=('sinpuntos', path))
        if not ok:
            return ('error', 0, out.kept)
        if os.path.abspath(self.current_file_path) == os.path.abspath(path):
            self.load_doc_lines()
        return ('ok', out.removed, out.kept)

    def _cmd_sinpuntos(self):
        status, removed, kept = self._cmd_sinpuntos_apply()
        name = os.path.basename(self.f2_file)
        text = {
            'ok': t('cmd.sinpuntos.ok', removed=removed, name=name, kept=kept),
            'same': t('cmd.sinpuntos.same', name=name),
            'empty': t('cmd.sinpuntos.empty', name=name),
            'missing': t('cmd.missing', name=name),
            'error': t('cmd.error', name=name),
        }[status]
        self._cmd_message(text, warn=(status in ('missing', 'error')))

    def _cmd_message(self, text, warn=False):
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox.warning if warn else QMessageBox.information
        box(self, '!', text)
