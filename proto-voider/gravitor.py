"""gravitor.py — juntar todas las oraciones que tienen tal o tales palabras.

Las palabras son un centro y las oraciones gravitan alrededor: se escribe una
consulta, se recorren las fuentes (tus textos en I/, o una muestra al azar de
los libros de O/) y las oraciones que coinciden se juntan en un archivo que
F3 muestra como un capítulo más.

Módulo puro (sin Qt): se prueba solo y lo usa gravitor_mixin.py.

Lo que se escribe:
  luz sombra    → las dos palabras en la MISMA oración (el espacio es "y")
  luz, sombra   → cualquiera de las dos (la coma es "o")
  grav          → sólo la palabra "grav", entera
  grav*         → las palabras que EMPIEZAN con grav (gravedad, gravitar)
  *grav         → las que TERMINAN en grav
  *grav*        → las que la CONTIENEN
  No distingue mayúsculas ni acentos.
"""
import json
import os
import random
import re
import unicodedata
from dataclasses import dataclass, field

CAP = 2000          # tope de oraciones por búsqueda: una palabra común da decenas de miles
_WORD = re.compile(r'[^\W_]+')


# ── texto ────────────────────────────────────────────────────────────────────

_COMBINING = re.compile('[\u0300-\u036f]')    # las marcas que separa la forma NFD


def fold(text):
    """Minúsculas y sin acentos: 'ÁRBOL' → 'arbol'.

    Se llama sobre libros enteros: la marca de acento se saca con una expresión
    regular (C), no letra por letra en Python, que era 10 veces más lento."""
    if text.isascii():
        return text.lower()
    return _COMBINING.sub('', unicodedata.normalize('NFD', text)).lower()


def strip_gutenberg(raw):
    """El texto sin el encabezado y el pie de Project Gutenberg."""
    m = re.search(r'\*{3}\s*START OF (?:THIS|THE) PROJECT GUTENBERG[^\n]*\n',
                  raw, re.IGNORECASE)
    if m:
        raw = raw[m.end():]
    m = re.search(r'\*{3}\s*END OF (?:THIS|THE) PROJECT GUTENBERG[^\n]*',
                  raw, re.IGNORECASE)
    if m:
        raw = raw[:m.start()]
    return raw.strip()


def sentences_from_lines(lines):
    """Un archivo de I/ ya viene una oración por línea: sin vacías ni puntos."""
    out = []
    for line in lines:
        s = line.strip()
        if s and s != '.':
            out.append(s)
    return out


# ── la consulta ──────────────────────────────────────────────────────────────

@dataclass
class Query:
    mode: str       # 'all' (espacio) o 'any' (coma)
    terms: list     # [(núcleo, abierto_al_inicio, abierto_al_final)]

    @staticmethod
    def _hit(term, words):
        core, open_start, open_end = term
        if open_start and open_end:
            return any(core in w for w in words)
        if open_end:                      # grav*  → empieza con
            return any(w.startswith(core) for w in words)
        if open_start:                    # *grav  → termina en
            return any(w.endswith(core) for w in words)
        return core in words              # grav   → la palabra entera

    def matches(self, sentence):
        words = _WORD.findall(fold(sentence))
        if not words:
            return False
        hits = (self._hit(t, words) for t in self.terms)
        return all(hits) if self.mode == 'all' else any(hits)

    def might_match(self, folded_text):
        """Prueba barata sobre un párrafo entero (ya sin acentos ni mayúsculas):
        ¿están los núcleos? Puede dejar pasar de más, nunca de menos."""
        found = (t[0] in folded_text for t in self.terms)
        return all(found) if self.mode == 'all' else any(found)


def parse_query(text):
    """Texto → Query, o None si no hay ninguna palabra."""
    mode = 'any' if ',' in text else 'all'
    terms = []
    for chunk in re.split(r'[\s,]+', text):
        if not chunk:
            continue
        chunk = fold(chunk)
        open_start = chunk.startswith('*')
        open_end = chunk.endswith('*')
        core = ''.join(_WORD.findall(chunk))
        if core:
            terms.append((core, open_start, open_end))
    return Query(mode, terms) if terms else None


def sanitize_name(text):
    """Lo que escribiste, apto como nombre de archivo (Windows y FAT incluidos)."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', text).strip(' .')
    name = name[:120].strip(' .')
    return name or 'gravitor'


# ── resultado ────────────────────────────────────────────────────────────────

@dataclass
class Result:
    sentences: list = field(default_factory=list)
    files: int = 0              # archivos de I/ revisados
    books: int = 0              # libros de O/ revisados
    capped: bool = False
    cancelled: bool = False
    unavailable: bool = False   # el corpus no está (por ejemplo /mnt/data sin montar)

    def summary(self):
        """Dice dónde buscó y cuánto encontró: nunca promete haber visto todo."""
        def plural(n, one, many):
            return f'{n} {one if n == 1 else many}'
        where = []
        if self.files:
            where.append(plural(self.files, 'archivo', 'archivos'))
        if self.books:
            where.append(plural(self.books, 'libro', 'libros'))
        text = ('buscó en ' + ' y '.join(where)) if where else 'no buscó en nada'
        text += f': {plural(len(self.sentences), "oración", "oraciones")}'
        if self.capped:
            text += f' (se cortó en {CAP})'
        if self.cancelled:
            text += ' (cancelada)'
        if self.unavailable:
            text += ' (el corpus no está disponible)'
        return text


# ── fuentes ──────────────────────────────────────────────────────────────────

def _i_files(i_dir, skip):
    out = []
    for root, dirs, names in os.walk(i_dir):
        dirs.sort()
        for n in sorted(names):
            if (n.lower().endswith('.txt') and n.lower() != '0.txt'
                    and n not in skip):
                out.append(os.path.join(root, n))
    return out


def search_i(i_dir, query, skip=(), cap=CAP, on_progress=None):
    """Tus textos: todos los .txt de I/ (menos 0.txt y lo que Gravitor ya generó)."""
    res = Result()
    files = _i_files(i_dir, set(skip))
    seen = set()
    for i, path in enumerate(files, 1):
        if on_progress is not None and on_progress(i, len(files), os.path.basename(path)) is False:
            res.cancelled = True
            break
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.rstrip('\n') for l in f]
        except OSError:
            continue
        res.files += 1
        # Un archivo sin ninguna de las palabras se descarta de un vistazo, sin
        # mirar oración por oración.
        if not query.might_match(fold('\n'.join(lines))):
            continue
        for s in sentences_from_lines(lines):
            if s not in seen and query.matches(s):
                seen.add(s)
                res.sentences.append(s)
                if len(res.sentences) >= cap:
                    res.capped = True
                    return res
    return res


def search_o(o_dir, query, n_books, to_sentences, cap=CAP, rng=None,
            on_progress=None, already=()):
    """El corpus: una muestra al azar de n_books libros de O/.

    to_sentences(texto_crudo) → oraciones (el separador de F6). Es lo caro, así
    que sólo corre sobre los párrafos que PUEDEN coincidir (might_match).
    `already` son oraciones ya encontradas (no se repiten)."""
    res = Result()
    try:
        names = [n for n in os.listdir(o_dir) if n.lower().endswith('.txt')]
    except OSError:
        names = []
    if not names:
        res.unavailable = True
        return res
    rng = rng or random.Random()
    picks = rng.sample(names, min(n_books, len(names)))
    seen = set(already)
    for i, name in enumerate(picks, 1):
        if on_progress is not None and on_progress(i, len(picks), name) is False:
            res.cancelled = True
            break
        try:
            with open(os.path.join(o_dir, name), 'r', encoding='utf-8',
                      errors='replace') as f:
                raw = f.read()
        except OSError:
            continue
        res.books += 1
        for para in re.split(r'\n\s*\n', strip_gutenberg(raw)):
            if not query.might_match(fold(para)):
                continue
            for s in to_sentences(para):
                s = s.strip()
                if s and s not in seen and query.matches(s):
                    seen.add(s)
                    res.sentences.append(s)
                    if len(res.sentences) >= cap:
                        res.capped = True
                        return res
    return res


def search(source, query, i_dir, o_dir, n_books, to_sentences, cap=CAP,
           rng=None, skip=(), on_progress=None):
    """source: 'i' (tus textos), 'o' (corpus) o 'both' (primero I/, después O/)."""
    total = Result()
    if source in ('i', 'both'):
        r = search_i(i_dir, query, skip=skip, cap=cap, on_progress=on_progress)
        total.sentences += r.sentences
        total.files = r.files
        total.capped = r.capped
        total.cancelled = r.cancelled
    if source in ('o', 'both') and not (total.capped or total.cancelled):
        r = search_o(o_dir, query, n_books, to_sentences,
                     cap=cap - len(total.sentences), rng=rng,
                     on_progress=on_progress, already=total.sentences)
        total.sentences += r.sentences
        total.books = r.books
        total.capped = total.capped or r.capped
        total.cancelled = total.cancelled or r.cancelled
        total.unavailable = r.unavailable
    return total


# ── el archivo que se escribe ────────────────────────────────────────────────

def result_lines(sentences):
    """Cada oración es su propio párrafo en el modelo de puntos: '.' al principio
    y uno después de cada oración. Sin resultados, nada (no se crea archivo)."""
    if not sentences:
        return []
    out = ['.']
    for s in sentences:
        out += [s, '.']
    return out


# ── registro de los archivos que Gravitor generó ─────────────────────────────
# Para que una búsqueda en I/ no encuentre los resultados de la anterior.

def load_registry(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {str(x) for x in data} if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def add_to_registry(path, fname):
    names = load_registry(path)
    names.add(fname)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(sorted(names), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
