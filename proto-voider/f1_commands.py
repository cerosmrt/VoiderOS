"""f1_commands.py — la lógica pura de los comandos de F1 (sin Qt).

Un renglón de F1 que empieza con `!` y una letra no se suelta al archivo: es una
orden para el texto que tiene F2. El primero, `!rem vision`, borra del archivo
de F2 todas las líneas que NO tienen la palabra. Las palabras siguen las reglas
de Gravitor (gravitor.parse_query)."""
import re
from dataclasses import dataclass

_CMD = re.compile(r'^!([A-Za-z]\w*)\s*(.*)$', re.S)


def parse_command(text):
    """'!rem luz sombra' → ('rem', 'luz sombra'). None si es escritura común.

    Hace falta `!` + una letra al principio: '¡hola!', 'qué bien!', '! algo' o
    '!!' no son comandos."""
    m = _CMD.match(text.strip())
    if not m:
        return None
    return m.group(1).lower(), m.group(2).strip()


@dataclass
class RemResult:
    lines: list      # el archivo nuevo, en el modelo de puntos
    kept: int        # líneas que se quedaron
    total: int       # líneas que había (sin contar puntos ni vacías)


def count_lines(lines):
    """Líneas de texto de un archivo: sin puntos separadores ni vacías."""
    return sum(1 for l in lines if l.strip() and l.strip() != '.')


def remove_lines_without(lines, query):
    """Deja sólo las líneas que coinciden con `query`.

    Los puntos que separan párrafos se acomodan: un grupo que se queda vacío
    desaparece (nunca quedan dos puntos seguidos) y el resultado empieza y
    termina con un punto. Las líneas vacías y el \\r de un CRLF se descartan.
    Devuelve None si ninguna línea coincide: no hay nada que escribir, y así un
    error de tipeo no vacía el archivo."""
    out, kept, total = [], 0, 0
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s == '.':
            if out and out[-1] != '.':
                out.append('.')
            continue
        total += 1
        if query.matches(s):
            out.append(s)
            kept += 1
    if kept == 0:
        return None
    if out[0] != '.':
        out.insert(0, '.')
    if out[-1] != '.':
        out.append('.')
    return RemResult(out, kept, total)
