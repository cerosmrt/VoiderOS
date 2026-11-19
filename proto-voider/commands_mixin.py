# commands_mixin.py — los comandos de F1 (`!rem …`) que actúan sobre el texto de F2.
#
# La lógica pura está en f1_commands.py; acá está lo que toca el archivo y los avisos.
import os

import f1_commands
import gravitor


class CommandsMixin:

    def _f1_command(self, name, args):
        """Despachar un comando de F1. Uno desconocido avisa y no escribe nada."""
        if name == 'rem':
            self._cmd_rem(args)
            return
        self._cmd_unknown(name)

    def _cmd_unknown(self, name):
        self._cmd_message(f'No conozco el comando !{name}.\n\n'
                          'El que existe: !rem <palabras>', warn=True)

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
            'ok': f'Quedaron {kept} de {total} líneas en {name}.',
            'noquery': 'Falta la palabra. Por ejemplo: !rem vision',
            'missing': f'No encuentro {name}.',
            'nomatch': f'Ninguna de las {total} líneas de {name} tiene «{args}». '
                       'No se tocó nada.',
            'error': f'No se pudo escribir {name}.',
        }[status]
        self._cmd_message(text, warn=(status != 'ok'))

    def _cmd_message(self, text, warn=False):
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox.warning if warn else QMessageBox.information
        box(self, '!', text)
