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
                  '_backup_copy', '_parse_mtp_list', '_detect_phones',
                  '_phone_backup_root', '_mount_phone', '_unmount_phone',
                  '_copy_file', '_backup_zip', '_backup_deliver',
                  '_program_plan', '_windows_bundle_ready', '_backup_zip_entries',
                  '_backup_entries', '_installer_bat', '_requirements_txt', '_arc',
                  '_run_in_thread', '_copy_chunks', '_progress_label')


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

def test_la_carpeta_arranca_con_la_fecha_y_termina_con_el_void(tmp_path):
    app = _app(tmp_path)
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    nombre = app._backup_folder_name(str(destino), fecha='25-08-28')
    assert nombre == '25-08-28(1)_void'


def test_dos_backups_el_mismo_dia_no_se_pisan(tmp_path):
    app = _app(tmp_path)
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    primero = app._backup_folder_name(str(destino), fecha='25-08-28')
    os.makedirs(os.path.join(str(destino), primero))
    segundo = app._backup_folder_name(str(destino), fecha='25-08-28')
    assert segundo != primero
    assert segundo.endswith('(2)_void')


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

    fuente = (inspect.getsource(FullscreenCircleApp._backup_vault)
              + inspect.getsource(FullscreenCircleApp._backup_to))
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


# ââ el telÃ©fono (MTP): sÃ³lo los .txt, en Download/Void Backup âââââââââââââââââ

def test_el_plan_solo_txt_deja_afuera_el_git(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '0.txt'), 'x')
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: x')
    _write(os.path.join(app.void_dir, 'I', 'nota.png'), 'img')
    files, total, _ = app._backup_plan(app.void_dir, only_txt=True)
    rels = sorted(f[0] for f in files)
    assert rels == ['0.txt', os.path.join('I', 'a.txt')]
    assert total == len('hola') + len('x')


def test_el_plan_por_defecto_sigue_llevando_el_git(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: x')
    files, _, _ = app._backup_plan(app.void_dir)
    assert any(f[0].startswith('.git') for f in files)


def test_parse_de_jmtpfs_list(tmp_path):
    app = _app(tmp_path)
    salida = ('Device 0 (VID=2717 and PID=ff40) is a Xiaomi Mi 9 Lite.\n'
              'Available devices (busLocation, devNum, productId, vendorId, product, vendor):\n'
              '1, 7, 0xff40, 0x2717, Mi 9 Lite, Xiaomi\n')
    assert app._parse_mtp_list(salida) == [('1', '7', 'Xiaomi Mi 9 Lite')]


def test_parse_sin_dispositivos(tmp_path):
    app = _app(tmp_path)
    assert app._parse_mtp_list('') == []
    assert app._parse_mtp_list('Available devices (busLocation, devNum, productId, vendorId, product, vendor):\n') == []


def test_sin_jmtpfs_no_hay_telefonos_y_no_explota(tmp_path, monkeypatch):
    import subprocess
    app = _app(tmp_path)
    def boom(*a, **k):
        raise FileNotFoundError('jmtpfs')
    monkeypatch.setattr(subprocess, 'run', boom)
    assert app._detect_phones() == []


def test_raiz_del_telefono_es_download_void_backup(tmp_path):
    app = _app(tmp_path)
    mp = tmp_path / 'mp'
    (mp / 'Almacenamiento interno compartido' / 'Download').mkdir(parents=True)
    raiz = app._phone_backup_root(str(mp))
    assert raiz == str(mp / 'Almacenamiento interno compartido' / 'Download' / 'Void Backup')


def test_telefono_bloqueado_no_tiene_almacenamiento(tmp_path):
    app = _app(tmp_path)
    mp = tmp_path / 'mp'
    mp.mkdir()
    assert app._phone_backup_root(str(mp)) is None


# ── el progreso: que se vea, y que se pueda parar ─────────────────────────────

def _void_con(app, n):
    for i in range(n):
        _write(os.path.join(app.void_dir, 'I', f'{i}.txt'), f'texto {i}')


def test_la_copia_avisa_el_progreso_archivo_por_archivo(tmp_path):
    app = _app(tmp_path)
    _void_con(app, 3)
    files, _, _ = app._backup_plan(app.void_dir)
    visto = []
    app._backup_copy(app.void_dir, str(tmp_path / 'dest'), files,
                     on_progress=lambda i, n, rel: visto.append((i, n)) or True)
    assert visto == [(1, 3), (2, 3), (3, 3)]


def test_cancelar_corta_la_copia_y_lo_dice(tmp_path):
    app = _app(tmp_path)
    _void_con(app, 5)
    files, _, _ = app._backup_plan(app.void_dir)
    copiados = app._backup_copy(app.void_dir, str(tmp_path / 'dest'), files,
                                on_progress=lambda i, n, rel: i < 2)
    assert copiados == 1, 'siguió copiando después de cancelar'
    assert app._backup_cancelled is True


def test_sin_cancelar_no_queda_marcado_como_cancelado(tmp_path):
    app = _app(tmp_path)
    _void_con(app, 2)
    files, _, _ = app._backup_plan(app.void_dir)
    app._backup_copy(app.void_dir, str(tmp_path / 'dest'), files)
    assert app._backup_cancelled is False


# ── un solo zip: una transferencia en vez de novecientas ──────────────────────

def _leer_zip(path):
    import zipfile
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n).decode('utf-8') for n in z.namelist() if not n.endswith('/')}


def test_el_zip_trae_los_archivos_dentro_de_una_carpeta_con_el_nombre_del_backup(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '0.txt'), 'scratch')
    files, _, _ = app._backup_plan(app.void_dir)
    destino = str(tmp_path / 'x.zip')
    assert app._backup_zip(app.void_dir, destino, files, '26-11-05(1)_void') is True
    assert _leer_zip(destino) == {
        '26-11-05(1)_void/I/a.txt': 'hola',
        '26-11-05(1)_void/0.txt': 'scratch',
    }


def test_el_zip_lleva_el_git_si_el_plan_lo_trae(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: x')
    files, _, _ = app._backup_plan(app.void_dir)
    destino = str(tmp_path / 'x.zip')
    app._backup_zip(app.void_dir, destino, files, 'b')
    assert 'b/.git/HEAD' in _leer_zip(destino)


def test_el_zip_respeta_los_nombres_con_signos_de_pregunta(tmp_path):
    """Dentro de un zip no hace falta sanear nada: el nombre se conserva."""
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', '¿Quién?.txt'), 'texto')
    files, _, _ = app._backup_plan(app.void_dir)
    destino = str(tmp_path / 'x.zip')
    app._backup_zip(app.void_dir, destino, files, 'b')
    assert _leer_zip(destino) == {'b/I/¿Quién?.txt': 'texto'}


def test_cancelar_mientras_se_arma_el_zip_no_deja_nada(tmp_path):
    app = _app(tmp_path)
    _void_con(app, 5)
    files, _, _ = app._backup_plan(app.void_dir)
    destino = str(tmp_path / 'x.zip')
    ok = app._backup_zip(app.void_dir, destino, files, 'b',
                         on_progress=lambda i, n, rel: i < 3)
    assert ok is False
    assert app._backup_cancelled is True
    assert not os.path.exists(destino), 'quedó un zip a medias'


def test_el_zip_avisa_el_progreso(tmp_path):
    app = _app(tmp_path)
    _void_con(app, 3)
    files, _, _ = app._backup_plan(app.void_dir)
    visto = []
    app._backup_zip(app.void_dir, str(tmp_path / 'x.zip'), files, 'b',
                    on_progress=lambda i, n, rel: visto.append((i, n)) or True)
    assert visto == [(1, 3), (2, 3), (3, 3)]


def test_entregar_copia_el_zip_y_verifica_el_tamano(tmp_path):
    app = _app(tmp_path)
    origen = tmp_path / 'a.zip'
    origen.write_bytes(b'x' * 5000)
    destino = tmp_path / 'tel' / 'a.zip'
    destino.parent.mkdir()
    assert app._backup_deliver(str(origen), str(destino)) is True
    assert destino.read_bytes() == b'x' * 5000


def test_entregar_detecta_una_copia_incompleta_y_la_borra(tmp_path, monkeypatch):
    """Si el teléfono corta a la mitad, 'Listo' no puede salir."""
    import shutil
    app = _app(tmp_path)
    origen = tmp_path / 'a.zip'
    origen.write_bytes(b'x' * 5000)
    destino = tmp_path / 'tel' / 'a.zip'
    destino.parent.mkdir()

    def a_medias(src, dst, on_progress=None):
        with open(dst, 'wb') as f:
            f.write(b'x' * 100)
        return True
    monkeypatch.setattr(app, '_copy_chunks', a_medias)
    assert app._backup_deliver(str(origen), str(destino)) is False
    assert not destino.exists(), 'quedó una copia rota que parece buena'


def test_entregar_devuelve_false_si_el_destino_falla(tmp_path):
    app = _app(tmp_path)
    origen = tmp_path / 'a.zip'
    origen.write_bytes(b'x')
    assert app._backup_deliver(str(origen), str(tmp_path / 'no' / 'existe' / 'a.zip')) is False


def test_el_contador_cuenta_zips_del_mismo_dia(tmp_path):
    app = _app(tmp_path)
    destino = tmp_path / 'pendrive'
    destino.mkdir()
    (destino / '25-08-28(1)_void.zip').write_bytes(b'z')
    assert app._backup_folder_name(str(destino), fecha='25-08-28') == '25-08-28(2)_void'


# ── el programa en el pendrive: instalador para Windows, offline ──────────────

def _programa_falso(base):
    """Un proto-voider en miniatura, con lo que viaja y lo que no."""
    for rel, txt in {
        'voider.py': 'print(1)', 'io_mixin.py': 'x', 'voider.spec': 'spec',
        'voider.ico': 'ico', 'fonts/EBGaramond.ttf': 'ttf', 'fonts/OFL.txt': 'ofl',
        'VOIDER — Instrucciones.txt': 'leeme', 'BUILD-WINDOWS.md': 'md',
        # lo que NO viaja: rutas personales, el void de prueba, tests, caché
        'config.json': '{"void_dir": "/home/federico/void"}', 'state.json': '{}',
        'void/0.txt': 'sandbox', 'tests/test_x.py': 't', '__pycache__/a.pyc': 'c',
        'd': 'basura', 'PENDING.md': 'notas',
    }.items():
        _write(os.path.join(base, rel), txt)
    return base


def test_el_programa_lleva_codigo_spec_icono_fuentes_e_instrucciones(tmp_path):
    app = _app(tmp_path)
    src = _programa_falso(str(tmp_path / 'proto'))
    rels = sorted(r for r, _ in app._program_plan(src))
    assert rels == sorted([
        'voider.py', 'io_mixin.py', 'voider.spec', 'voider.ico',
        os.path.join('fonts', 'EBGaramond.ttf'), os.path.join('fonts', 'OFL.txt'),
        'VOIDER — Instrucciones.txt', 'BUILD-WINDOWS.md',
    ])


def test_el_programa_no_lleva_rutas_personales_ni_el_void_de_prueba(tmp_path):
    app = _app(tmp_path)
    src = _programa_falso(str(tmp_path / 'proto'))
    rels = [r for r, _ in app._program_plan(src)]
    for no in ('config.json', 'state.json', 'd', 'PENDING.md'):
        assert no not in rels, f'viajó {no}'
    assert not any(r.split(os.sep)[0] in ('void', 'tests', '__pycache__') and os.sep in r
                   for r in rels)


def _cache_falsa(base, con_python=True, con_wheels=True):
    os.makedirs(base, exist_ok=True)
    if con_python:
        _write(os.path.join(base, 'python-3.10.11-amd64.exe'), 'py')
    if con_wheels:
        _write(os.path.join(base, 'wheels', 'PyQt6-6.7.0-cp38-abi3-win_amd64.whl'), 'w')
    return base


def test_sin_cache_el_programa_no_se_puede_agregar_y_dice_por_que(tmp_path):
    app = _app(tmp_path)
    ok, motivo = app._windows_bundle_ready(str(tmp_path / 'no-existe'))
    assert ok is False and motivo


def test_cache_sin_python_o_sin_wheels_no_alcanza(tmp_path):
    app = _app(tmp_path)
    assert app._windows_bundle_ready(_cache_falsa(str(tmp_path / 'a'), con_python=False))[0] is False
    assert app._windows_bundle_ready(_cache_falsa(str(tmp_path / 'b'), con_wheels=False))[0] is False


def test_cache_completa_esta_lista(tmp_path):
    app = _app(tmp_path)
    assert app._windows_bundle_ready(_cache_falsa(str(tmp_path / 'c'))) == (True, '')


def test_sin_programa_el_zip_queda_como_siempre(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    files, _, _ = app._backup_plan(app.void_dir)
    entries = app._backup_entries(files, 'b')
    destino = str(tmp_path / 'x.zip')
    assert app._backup_zip_entries(destino, entries) is True
    assert _leer_zip(destino) == {'b/I/a.txt': 'hola'}


def test_con_programa_el_zip_trae_void_programa_e_instalador(tmp_path):
    app = _app(tmp_path)
    _write(os.path.join(app.void_dir, 'I', 'a.txt'), 'hola')
    _write(os.path.join(app.void_dir, '.git', 'HEAD'), 'ref: x')
    src = _programa_falso(str(tmp_path / 'proto'))
    cache = _cache_falsa(str(tmp_path / 'cache'))
    files, _, _ = app._backup_plan(app.void_dir)
    entries = app._backup_entries(files, 'b', program_src=src, bundle_cache=cache)
    destino = str(tmp_path / 'x.zip')
    app._backup_zip_entries(destino, entries)
    z = _leer_zip(destino)
    assert z['b/void/I/a.txt'] == 'hola'
    assert 'b/void/.git/HEAD' in z, 'el backup con programa perdió el historial'
    assert z['b/programa/voider.py'] == 'print(1)'
    assert 'b/programa/fonts/EBGaramond.ttf' in z
    assert 'b/programa/python-3.10.11-amd64.exe' in z
    assert 'b/programa/wheels/PyQt6-6.7.0-cp38-abi3-win_amd64.whl' in z
    assert 'b/programa/requirements.txt' in z
    assert 'b/INSTALAR.bat' in z
    assert not any(k.endswith('config.json') for k in z), 'viajaron tus rutas'


def test_zip_entries_avisa_y_se_puede_cancelar(tmp_path):
    app = _app(tmp_path)
    entries = [(f'b/{i}.txt', b'x') for i in range(4)]
    destino = str(tmp_path / 'x.zip')
    ok = app._backup_zip_entries(destino, entries, on_progress=lambda i, n, r: i < 2)
    assert ok is False and not os.path.exists(destino)


def test_el_instalador_es_offline_y_usa_el_spec(tmp_path):
    app = _app(tmp_path)
    bat = app._installer_bat()
    assert '\r\n' in bat, 'un .bat con finales de línea de Linux falla en cmd'
    assert '--no-index' in bat and '--find-links' in bat, 'tiene que andar sin internet'
    assert 'voider.spec' in bat
    assert 'pause' in bat.lower(), 'si falla, la ventana tiene que quedar abierta'


def test_pyaudio_es_opcional(tmp_path):
    """Si pyaudio no instala, el resto tiene que compilar igual."""
    app = _app(tmp_path)
    req = app._requirements_txt()
    assert 'PyQt6' in req and 'pyinstaller' in req.lower()
    assert 'pyaudio' not in req.lower()
    assert 'pyaudio' in app._installer_bat().lower()


# ── que Voider no se cuelgue: lo pesado va a un hilo ──────────────────────────

@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_run_in_thread_devuelve_el_resultado_desde_otro_hilo(tmp_path, qapp):
    import threading
    app = _app(tmp_path)
    principal = threading.get_ident()
    hilo, valor = app._run_in_thread(lambda: (threading.get_ident(), 42))
    assert valor == 42
    assert hilo != principal, 'corrió en el hilo de la interfaz'


def test_run_in_thread_deja_vivir_a_la_interfaz_mientras_espera(tmp_path, qapp):
    """Lo que congelaba a Voider: mientras el trabajo corre, Qt tiene que
    seguir procesando eventos (si no, Hyprland ofrece 'terminar el programa')."""
    import time
    from PyQt6.QtCore import QTimer
    app = _app(tmp_path)
    vivo = []
    QTimer.singleShot(0, lambda: vivo.append(True))
    app._run_in_thread(lambda: time.sleep(0.3))
    assert vivo, 'la interfaz no procesó eventos durante el trabajo'


def test_run_in_thread_propaga_el_error(tmp_path, qapp):
    app = _app(tmp_path)
    def boom():
        raise OSError('se desenchufó')
    with pytest.raises(OSError, match='desenchufó'):
        app._run_in_thread(boom)


def test_run_in_thread_llama_al_tick_mientras_trabaja(tmp_path, qapp):
    import time
    app = _app(tmp_path)
    ticks = []
    app._run_in_thread(lambda: time.sleep(0.3), on_tick=lambda: ticks.append(1))
    assert len(ticks) >= 2


def test_entregar_avisa_el_avance_en_bytes(tmp_path):
    app = _app(tmp_path)
    origen = tmp_path / 'a.zip'
    origen.write_bytes(b'x' * (3 * 1024 * 1024 + 5))
    destino = tmp_path / 'a-copia.zip'
    visto = []
    ok = app._backup_deliver(str(origen), str(destino),
                             on_progress=lambda hecho, total: visto.append((hecho, total)) or True)
    assert ok is True
    assert visto[-1] == (3 * 1024 * 1024 + 5, 3 * 1024 * 1024 + 5)
    assert [h for h, _ in visto] == sorted(h for h, _ in visto)
    assert destino.read_bytes() == origen.read_bytes()


def test_cancelar_la_entrega_borra_la_copia_a_medias(tmp_path):
    app = _app(tmp_path)
    origen = tmp_path / 'a.zip'
    origen.write_bytes(b'x' * (3 * 1024 * 1024))
    destino = tmp_path / 'a-copia.zip'
    ok = app._backup_deliver(str(origen), str(destino),
                             on_progress=lambda hecho, total: hecho < 1024 * 1024)
    assert ok is False
    assert app._backup_cancelled is True
    assert not destino.exists(), 'quedó una copia a medias que parece buena'


def test_la_etiqueta_de_la_barra_no_crece_con_nombres_largos(tmp_path):
    """La barra se veía cortada: el texto cambiaba de ancho en cada archivo."""
    app = _app(tmp_path)
    largo = 'I/' + 'una frase larguísima de título de capítulo ' * 5 + '.txt'
    etiqueta = app._progress_label('Armando el zip', 3, 938, largo)
    assert all(len(linea) <= 60 for linea in etiqueta.splitlines())
    assert '3 de 938' in etiqueta
    assert etiqueta.splitlines()[1].endswith('.txt'), 'se perdió el final del nombre'

