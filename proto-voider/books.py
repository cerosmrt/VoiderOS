"""books.py — el modelo de libros del empaquetador (F8). Puro, sin Qt.

Un capítulo es un single y un libro es un álbum: el libro REFERENCIA los
archivos de I/ por nombre y no los copia, así que el mismo capítulo puede estar
en varios libros y editarlo una vez lo cambia en todos. Una variante es otro
capítulo (F3 duplica con Alt+Shift+↑/↓).

Se guarda en <void>/books.json:

  {"version": 1,
   "libros": [{"id": "l1", "titulo": "Mitad Humana",
               "capitulos": ["Prologo.txt", "Uno.txt"],
               "hojas": 4,          # hojas por cuadernillo
               "autor": "", "colofon": ""}]}

Renombrar o borrar un capítulo en F3 tiene que llegar acá (rename_chapter_everywhere
y drop_chapter_everywhere), o los libros quedan apuntando a archivos que no existen.
"""
import copy
import json
import os

VERSION = 1
DEFAULT_SHEETS = 4
ROLES = ('prologo', 'dedicatoria', 'epilogo')    # lugares con nombre
MIN_CAPS = 6                                      # capítulos que se muestran siempre


def empty():
    return {'version': VERSION, 'libros': []}


# ── un libro ─────────────────────────────────────────────────────────────────

def _normalize(book):
    """Un libro de un archivo viejo o a medias, con todos sus campos. None si no
    es un libro."""
    if not isinstance(book, dict):
        return None
    roles = {r: str(book.get(r) or '').strip() for r in ROLES}
    caps, seen = [], {v for v in roles.values() if v}   # un archivo, un solo lugar
    for c in book.get('capitulos') or []:
        if isinstance(c, str) and c and c not in seen:
            seen.add(c)
            caps.append(c)
    try:
        hojas = max(1, int(book.get('hojas', DEFAULT_SHEETS)))
    except (TypeError, ValueError):
        hojas = DEFAULT_SHEETS
    titulo = str(book.get('titulo') or '').strip() or 'Sin título'
    return {'id': str(book.get('id') or ''), 'titulo': titulo, 'capitulos': caps,
            'hojas': hojas, 'autor': str(book.get('autor') or ''),
            'colofon': str(book.get('colofon') or ''),
            **roles,
            'portada': bool(book.get('portada', True)),
            'referencia': bool(book.get('referencia', True))}


def _id_number(book_id):
    return int(book_id[1:]) if book_id[:1] == 'l' and book_id[1:].isdigit() else 0


def _next_id(data):
    """l1, l2, … Nunca reusa un número, ni el de un libro ya borrado: se guarda el
    más alto que se dio (_ultimo)."""
    n = max([data.get('_ultimo', 0)] + [_id_number(x['id']) for x in data['libros']]) + 1
    data['_ultimo'] = n
    return f'l{n}'


def new_book(data, titulo, capitulos=()):
    book = _normalize({'titulo': titulo, 'capitulos': list(capitulos)})
    book['id'] = _next_id(data)
    data['libros'].append(book)
    return book


def find(data, book_id):
    return next((x for x in data['libros'] if x['id'] == book_id), None)


def rename_book(book, titulo):
    book['titulo'] = str(titulo).strip() or book['titulo']


def delete_book(data, book_id):
    data['libros'] = [x for x in data['libros'] if x['id'] != book_id]


def move_book(data, book_id, delta):
    """Sube o baja un libro en la lista, sin dar la vuelta. False si no se movió."""
    ids = [x['id'] for x in data['libros']]
    if book_id not in ids:
        return False
    i = ids.index(book_id)
    j = i + delta
    if not 0 <= j < len(ids):
        return False
    data['libros'][i], data['libros'][j] = data['libros'][j], data['libros'][i]
    return True


def duplicate_book(data, book_id):
    """Una edición: los mismos capítulos, en una lista propia, justo debajo."""
    src = find(data, book_id)
    if src is None:
        return None
    copia = copy.deepcopy(src)
    copia['id'] = _next_id(data)
    copia['titulo'] = f"{src['titulo']} (copia)"
    data['libros'].insert(data['libros'].index(src) + 1, copia)
    return copia


def from_f3_group(data, titulo, lines):
    """Un libro a partir de un grupo de F3. `lines` arranca en el punto que abre el
    grupo (o justo después) y sigue hasta el siguiente punto: lo que viene después
    es otro libro. Los portales ('0.txt') no son capítulos."""
    names, started = [], False
    for l in lines:
        if l == '.':
            if started:
                break
            continue
        started = True
        if l and l != '0.txt':
            names.append(l)
    return new_book(data, titulo, names)


def group_at(lines, index):
    """Los capítulos del libro de F3 donde está el cursor. `lines` es la biblioteca
    (con los '.' que separan libros); parado en un capítulo o en el punto que abre
    el grupo, es ese grupo. Los portales ('0.txt') no son capítulos."""
    n = len(lines)
    if not n:
        return []
    i = max(0, min(index, n - 1))
    if lines[i] == '.':
        start = i + 1
    else:
        j = i
        while j >= 0 and lines[j] != '.':
            j -= 1
        start = j + 1
    out, k = [], start
    while k < n and lines[k] != '.':
        if lines[k] and lines[k] != '0.txt':
            out.append(lines[k])
        k += 1
    return out


# ── capítulos de un libro ────────────────────────────────────────────────────

def add_chapter(book, fname, at=None):
    """Agrega un capítulo al final o en `at`. False si el libro ya lo tiene."""
    if fname in book['capitulos']:
        return False
    if at is None:
        book['capitulos'].append(fname)
    else:
        book['capitulos'].insert(max(0, min(at, len(book['capitulos']))), fname)
    return True


def remove_chapter(book, fname):
    """Saca el archivo del libro, esté en un capítulo o en un lugar con nombre."""
    found = False
    if fname in book['capitulos']:
        book['capitulos'].remove(fname)
        found = True
    for r in ROLES:
        if book.get(r) == fname:
            book[r] = ''
            found = True
    return found


def move_chapter(book, fname, delta):
    caps = book['capitulos']
    if fname not in caps:
        return False
    i = caps.index(fname)
    j = i + delta
    if not 0 <= j < len(caps):
        return False
    caps[i], caps[j] = caps[j], caps[i]
    return True


def chapters_of(book):
    """Los archivos del libro en el orden en que se imprimen: prólogo, dedicatoria,
    los capítulos y el epílogo (los lugares vacíos no se imprimen)."""
    out = [book.get(r) for r in ('prologo', 'dedicatoria')]
    out += book['capitulos']
    out.append(book.get('epilogo'))
    return [f for f in out if f]


def books_containing(data, fname):
    """¿En qué libros está este capítulo? (el single buscando sus álbumes)"""
    return [x for x in data['libros'] if fname in chapters_of(x)]


def missing_chapters(book, existing):
    """Los archivos del libro que ya no existen."""
    return [c for c in chapters_of(book) if c not in existing]


# ── el esqueleto: lugares que se llenan o quedan vacíos ──────────────────────
#
# Portada · Título · Autor · Prólogo · Dedicatoria · Cap 1 … Cap n · Epílogo ·
# Referencia al software · .   Los capítulos se llenan en orden (siempre se
# muestran 6 como mínimo y uno vacío después del último: se agregan tantos como
# hagan falta). Portada y referencia son interruptores.

def slot_file(book, key):
    """El archivo que llena un lugar ('prologo', 'cap:3', …), o '' si está vacío."""
    if key in ROLES:
        return book.get(key, '')
    if key.startswith('cap:'):
        i = int(key[4:]) - 1
        return book['capitulos'][i] if 0 <= i < len(book['capitulos']) else ''
    return ''


def assign(book, key, fname):
    """Pone un archivo en un lugar. Un archivo está en un solo lugar del libro: si ya
    estaba en otro, se mueve. En un capítulo ocupado, reemplaza; más allá del último,
    agrega al final."""
    if key in ROLES:
        remove_chapter(book, fname)
        book[key] = fname
        return True
    if not key.startswith('cap:'):
        return False
    caps = book['capitulos']
    idx = int(key[4:]) - 1
    if idx < len(caps) and caps[idx] == fname:
        return True
    for r in ROLES:
        if book.get(r) == fname:
            book[r] = ''
    if fname in caps:
        j = caps.index(fname)
        caps.pop(j)
        if j < idx:
            idx -= 1
    if idx < len(caps):
        caps[idx] = fname
    else:
        caps.append(fname)
    return True


def clear_slot(book, key):
    """Vacía un lugar. Un capítulo vacío cierra el hueco (los de abajo suben)."""
    if key in ROLES:
        if book.get(key):
            book[key] = ''
            return True
        return False
    if key.startswith('cap:'):
        i = int(key[4:]) - 1
        if 0 <= i < len(book['capitulos']):
            book['capitulos'].pop(i)
            return True
    return False


def toggle(book, key):
    """Prende o apaga 'portada' o 'referencia'. Devuelve el valor nuevo."""
    if key in ('portada', 'referencia'):
        book[key] = not book.get(key, True)
        return book[key]
    return None


def _title_of(fname):
    return fname[:-4] if fname.lower().endswith('.txt') else fname


def rows(book):
    """Las filas del esqueleto, en orden, para mostrar en F8: key, label y text."""
    def row(key, label, value):
        return {'key': key, 'label': label, 'text': f'{label} · {value}'}
    yesno = lambda v: 'sí' if v else 'no'
    out = [row('portada', 'Portada', yesno(book.get('portada', True))),
           row('titulo', 'Título', book['titulo']),
           row('autor', 'Autor', book['autor'] or '—')]
    for key, label in (('prologo', 'Prólogo'), ('dedicatoria', 'Dedicatoria')):
        out.append(row(key, label, _title_of(book[key]) if book.get(key) else '—'))
    caps = book['capitulos']
    for i in range(max(MIN_CAPS, len(caps) + 1)):
        out.append(row(f'cap:{i + 1}', f'Cap {i + 1}', _title_of(caps[i]) if i < len(caps) else '—'))
    out.append(row('epilogo', 'Epílogo', _title_of(book['epilogo']) if book.get('epilogo') else '—'))
    out.append(row('referencia', 'Referencia al software', yesno(book.get('referencia', True))))
    out.append({'key': '.', 'label': '.', 'text': '.'})
    return out


# ── lo que pasa en F3 y tiene que llegar a los libros ────────────────────────

def rename_chapter_everywhere(data, old, new):
    """Un capítulo cambió de nombre en F3: todos los libros que lo tienen lo siguen,
    en el mismo lugar (capítulo o lugar con nombre). Si un libro ya tenía `new`, no
    queda duplicado. Devuelve en cuántos libros cambió."""
    n = 0
    for book in data['libros']:
        changed = False
        caps = book['capitulos']
        if old in caps:
            i = caps.index(old)
            if new in chapters_of(book) and new != old:
                caps.pop(i)
            else:
                caps[i] = new
            changed = True
        for r in ROLES:
            if book.get(r) == old:
                book[r] = '' if (new in chapters_of(book)) else new
                changed = True
        n += changed
    return n


def drop_chapter_everywhere(data, fname):
    """Un capítulo se borró: sale de todos los libros (de un capítulo o de un lugar
    con nombre, que queda vacío). Devuelve de cuántos."""
    return sum(1 for book in data['libros'] if remove_chapter(book, fname))


# ── guardar y cargar ─────────────────────────────────────────────────────────

def load(path):
    """El catálogo, o uno vacío si el archivo falta o está roto. Un archivo roto
    NO se toca: quizás sea reparable a mano."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return empty()
    if not isinstance(raw, dict):
        return empty()
    data = empty()
    for item in raw.get('libros') or []:
        book = _normalize(item)
        if book is not None:
            data['libros'].append(book)
    try:
        ultimo = max(int(raw.get('_ultimo', 0)), 0)
    except (TypeError, ValueError):
        ultimo = 0
    ultimo = max([ultimo] + [_id_number(x['id']) for x in data['libros']])
    if ultimo:
        data['_ultimo'] = ultimo
    for book in data['libros']:
        if not book['id']:
            book['id'] = _next_id(data)
    return data


def _count_books(text):
    try:
        raw = json.loads(text)
    except ValueError:
        return 0
    libros = raw.get('libros') if isinstance(raw, dict) else None
    return len(libros) if isinstance(libros, list) else 0


def save(path, data):
    """Escribe de forma atómica. Antes deja la versión anterior como .bak, pero sólo
    si tenía libros y cambió: un guardado vacío no pisa la última copia buena."""
    text = json.dumps({k: v for k, v in data.items() if not k.startswith('_') or k == '_ultimo'},
                      ensure_ascii=False, indent=2)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            old = f.read()
        if old != text and _count_books(old):
            with open(path + '.bak', 'w', encoding='utf-8') as g:
                g.write(old)
    except OSError:
        pass
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)
