"""Ctrl+B: copiar el void entero a un pendrive, CON el historial de git.

El _backup_vault viejo abría un diálogo de carpeta y copiaba sólo los .txt, así
que perdía el .git — es decir, todo el historial. Esto es lo que roadmap/
pending.txt pide en su lugar: detectar el pendrive, mostrar qué se va a escribir
y a dónde, confirmar, commitear el void, y recién ahí copiar todo tal cual está.
"""
import os
import types

import pytest

from helpers import make_ring_app


BACKUP_METHODS = ('_detect_drives', '_backup_plan', '_backup_folder_name',
                  '_backup_copy')


def _app(tmp_path):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.void_dir = str(tmp_path / 'void')
    os.makedirs(os.path.join(app.void_dir, 'I'), exist_ok=True)
    for name in BACKUP_METHODS:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))
    return app


def _write(path, text=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# ── el plan: qué se copiaría, sin escribir nada ───────────────────────────────

def test_el_historial_de_git_viaja(tmp_path):
    """La razón entera por la que esto se reescribe."""
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: refs/heads/main')
    files, total, skipped = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert any(r.startswith('.git') for r in rels), f'se perdió el historial: {rels}'


def test_los_txt_tambien_obviamente(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '0.txt'), 'x')
    files, total, skipped = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert os.path.join('I', 'a.txt') in rels
    assert '0.txt' in rels


def test_un_enlace_a_otro_disco_se_anota_pero_no_se_sigue(tmp_path):
    """O/ apunta a /mnt/data: seguirlo copiaría 76 mil libros del corpus."""
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    afuera = tmp_path / 'corpus'
    afuera.mkdir()
    _write(str(afuera / 'enorme.txt'), 'x' * 5000)
    os.symlink(str(afuera), os.path.join(app.void_dir, 'O'))

    files, total, skipped = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert not any(r.startswith('O') for r in rels), 'siguió el enlace'
    assert 'O' in skipped
    assert total == len('hola')


def test_el_plan_no_escribe_nada(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    app._backup_plan(app.void_dir)
    assert os.listdir(destino) == [], 'tocó el destino antes de confirmar'


def test_un_void_vacio_no_rompe(tmp_path):
    app = _app(tmp_path)
    files, total, skipped = app._backup_plan(app.void_dir)
    assert files == [] and total == 0


# ── el nombre de la carpeta ───────────────────────────────────────────────────

def test_la_carpeta_lleva_el_nombre_del_void_y_la_fecha(tmp_path):
    app = _app(tmp_path)
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    nombre = app._backup_folder_name(str(destino), fecha='25-08-28')
    assert nombre == 'void_25-08-28(1)'


def test_dos_backups_el_mismo_dia_no_se_pisan(tmp_path):
    app = _app(tmp_path)
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    primero = app._backup_folder_name(str(destino), fecha='25-08-28')
    os.makedirs(os.path.join(str(destino), primero))
    segundo = app._backup_folder_name(str(destino), fecha='25-08-28')
    assert segundo != primero
    assert segundo.endswith('(2)')


# ── la copia ──────────────────────────────────────────────────────────────────

def test_la_copia_reproduce_el_arbol_con_el_git(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, 'I', 'sub', 'b.txt'), 'chau')
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: x')
    destino = tmp_path / 'pendrive'
    destino.mkdir()

    files, _, _ = app._backup_plan(app.void_dir)
    copiados = app._backup_copy(app.void_dir, str(destino / 'dest'), files)

    assert copiados == 3
    with open(destino / 'dest' / 'I' / 'a.txt', encoding='utf-8') as f:
        assert f.read() == 'hola'
    with open(destino / 'dest' / 'I' / 'sub' / 'b.txt', encoding='utf-8') as f:
        assert f.read() == 'chau'
    assert (destino / 'dest' / '.git' / 'HEAD').exists(), 'el historial no llegó'


def test_copiar_no_toca_el_void_original(tmp_path):
    app = _app(tmp_path)
    origen = os.path.join(app.void_dir, 'I', 'a.txt')
    _write(origen, 'intacto')
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    files, _, _ = app._backup_plan(app.void_dir)
    app._backup_copy(app.void_dir, str(destino / 'dest'), files)
    with open(origen, encoding='utf-8') as f:
        assert f.read() == 'intacto'


# ── detectar el pendrive ──────────────────────────────────────────────────────

def test_se_buscan_los_puntos_de_montaje_de_medios(tmp_path, monkeypatch):
    app = _app(tmp_path)
    falso = tmp_path / 'run' / 'media' / 'federico'
    (falso / 'SESANTA').mkdir(parents=True)
    (falso / 'OTRO').mkdir()
    monkeypatch.setattr(app, '_backup_media_roots', lambda: [str(falso)], raising=False)
    encontrados = app._detect_drives()
    assert sorted(os.path.basename(d) for d in encontrados) == ['OTRO', 'SESANTA']


def test_sin_pendrive_no_se_encuentra_nada(tmp_path, monkeypatch):
    app = _app(tmp_path)
    monkeypatch.setattr(app, '_backup_media_roots',
                        lambda: [str(tmp_path / 'no-existe')], raising=False)
    assert app._detect_drives() == []


def test_backup_vault_solo_llama_a_metodos_que_existen(tmp_path):
    """Los diálogos de Qt hacen que _backup_vault no se pueda correr en un test,
    así que un nombre mal escrito adentro no lo atrapa nada — y explota recién
    al apretar Ctrl+B. (Pasó: decía commit_void_repo, que no existe.)
    Esto revisa los self.<algo>() del cuerpo contra la clase de verdad."""
    import inspect
    import re
    from new_interface import FullscreenCircleApp

    fuente = inspect.getsource(FullscreenCircleApp._backup_vault)
    llamados = set(re.findall(r'self\.(_?[a-zA-Z_][a-zA-Z0-9_]*)\(', fuente))
    faltantes = [n for n in sorted(llamados) if not hasattr(FullscreenCircleApp, n)]
    assert not faltantes, f'_backup_vault llama a métodos inexistentes: {faltantes}'


# ── lo que no vale la pena copiar ─────────────────────────────────────────────

def test_las_voces_generadas_no_viajan(tmp_path):
    """tts/ son cientos de MB de modelos .onnx que se vuelven a bajar. El backup
    es para lo que NO se puede recuperar."""
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, 'tts', 'voz.onnx'), 'x' * 9000)
    files, total, skipped = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert not any(r.startswith('tts') for r in rels), 'se copió tts'
    assert 'tts' in skipped, 'la omisión tiene que verse, no esconderse'
    assert total == len('hola')


def test_el_scratch_si_viaja(tmp_path):
    """0.txt es el texto vivo; excluir tts no puede llevárselo puesto."""
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', '0.txt'), 'el borrador')
    _write(os.path.join(app.void_dir, '0.txt'), '')
    files, _, _ = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert os.path.join('I', '0.txt') in rels
    assert '0.txt' in rels


def test_un_archivo_que_se_llama_tts_no_se_confunde_con_la_carpeta(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'tts.txt'), 'sobre las voces')
    files, _, skipped = app._backup_plan(app.void_dir)
    rels = [f[0] for f in files]
    assert os.path.join('I', 'tts.txt') in rels, 'se comió un texto por el nombre'
