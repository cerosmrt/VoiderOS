"""imposition.py — acomodar las páginas de un libro en hojas para coser. Puro, sin Qt.

Hojas A4 apaisadas con 2 páginas A5 por cara (izquierda y derecha). Se imprime de
los dos lados, se dobla cada hoja por la mitad, se apilan las hojas de un
cuadernillo (la 1 afuera) y se cosen los cuadernillos por el lomo.

Un cuadernillo de N hojas tiene 4N páginas. Las páginas se numeran desde 1; las que
pasan del total del libro son páginas en blanco (None) que completan el último
cuadernillo.

Orden dentro de un cuadernillo de S = 4N páginas (numeradas 1..S), hoja j de 1..N
contando desde la de afuera:
    frente:  izquierda = S - 2j + 2    derecha = 2j - 1
    dorso:   izquierda = 2j            derecha = S - 2j + 1
El dorso se imprime volteando la hoja por el borde corto (como una página de libro):
lo que está atrás de la derecha del frente es la izquierda del dorso.
"""
from dataclasses import dataclass


@dataclass
class Sheet:
    signature: int      # número de cuadernillo, desde 1
    sheet: int          # hoja dentro del cuadernillo, desde 1 (la de afuera)
    front: tuple        # (izquierda, derecha), None = página en blanco
    back: tuple
    sheets_in_signature: int = 0
    signatures: int = 0


@dataclass
class Face:
    """Una página física del PDF (una cara de una hoja A4)."""
    pages: tuple        # (izquierda, derecha) del libro, None = en blanco
    label: str = ''     # marca de compaginación, ej. 'C3/10 · H2/4'
    texts: tuple = None  # texto fijo (sólo la hoja de prueba)


@dataclass
class Row:
    sheets: int
    pages_per_signature: int
    signatures: int
    blank: int
    best: bool = False


# ── cuántas hojas, cuántas en blanco ─────────────────────────────────────────

def _check(sheets):
    if sheets < 1:
        raise ValueError('un cuadernillo necesita al menos 1 hoja')


def pad_to_signatures(total_pages, sheets):
    """→ (páginas completadas, cuadernillos, páginas en blanco)."""
    _check(sheets)
    size = 4 * sheets
    n = -(-total_pages // size) if total_pages > 0 else 0
    return n * size, n, n * size - max(total_pages, 0)


def best_sheets(total_pages, options=range(2, 9)):
    """La cantidad de hojas por cuadernillo que deja menos páginas en blanco. Con
    empate, la más cercana a 4 (el estándar); y con otro empate, la más finita."""
    return min(options, key=lambda s: (pad_to_signatures(total_pages, s)[2],
                                       abs(s - 4), s))


def signature_table(total_pages, options=range(2, 9)):
    """Una fila por opción, con la mejor marcada: lo que ves mientras cambiás las
    hojas por cuadernillo."""
    options = list(options)
    best = best_sheets(total_pages, options)
    rows = []
    for s in options:
        padded, n, blank = pad_to_signatures(total_pages, s)
        rows.append(Row(s, 4 * s, n, blank, best=(s == best)))
    return rows


# ── el orden de las páginas ──────────────────────────────────────────────────

def impose(total_pages, sheets):
    """Todas las hojas del libro, cuadernillo por cuadernillo y de afuera hacia
    adentro. Las páginas que pasan del total son None."""
    _check(sheets)
    padded, n_sig, _ = pad_to_signatures(total_pages, sheets)
    size = 4 * sheets

    def page(p):
        return p if p <= total_pages else None

    out = []
    for k in range(n_sig):
        base = k * size
        for j in range(1, sheets + 1):
            out.append(Sheet(
                signature=k + 1, sheet=j,
                front=(page(base + size - 2 * j + 2), page(base + 2 * j - 1)),
                back=(page(base + 2 * j), page(base + size - 2 * j + 1)),
                sheets_in_signature=sheets, signatures=n_sig))
    return out


def _label(sheet):
    return (f'C{sheet.signature}/{sheet.signatures} · '
            f'H{sheet.sheet}/{sheet.sheets_in_signature}')


def duplex_pages(sheets):
    """Para una impresora de doble cara automática: frente y dorso de cada hoja,
    una detrás de la otra."""
    out = []
    for s in sheets:
        out.append(Face(s.front, _label(s)))
        out.append(Face(s.back, _label(s)))
    return out


def manual_passes(sheets):
    """Para dar vuelta las hojas a mano: primero todos los frentes en orden; después
    los dorsos en orden inverso, para que al reponer la pila coincidan."""
    fronts = [Face(s.front, _label(s)) for s in sheets]
    backs = [Face(s.back, _label(s)) for s in reversed(sheets)]
    return fronts, backs


def test_sheet():
    """Una sola hoja con las cuatro posiciones marcadas, para comprobar cómo da
    vuelta la impresora antes de gastar el libro entero."""
    return [
        Face((None, None), 'PRUEBA', ('1 · frente · izquierda', '2 · frente · derecha')),
        Face((None, None), 'PRUEBA', ('3 · dorso · izquierda', '4 · dorso · derecha')),
    ]
