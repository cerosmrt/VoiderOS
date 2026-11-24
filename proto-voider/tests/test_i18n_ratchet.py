"""Trinquete: los textos de la interfaz salen del catálogo (t('clave')), no escritos en
español dentro del código. Falla si aparece un literal con letras del español (tildes,
ñ, ¿, ¡) fuera de print(), comentarios y docstrings, en los módulos ya traducidos."""
import ast
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Módulos ya traducidos. F8 (books*, book_*, imposition, chapter_picker, bookbinder_dialog)
# queda afuera hasta que se decida su destino.
TRANSLATED = ('gravitor_mixin.py', 'widgets.py', 'keys_panel.py', 'keys_model.py',
              'commands_mixin.py', 'f4_mixin.py', 'menu_model.py')   # transcriber: su español es el filtro de Whisper (datos)
# io_mixin tiene texto en español que NO es interfaz (abreviaturas para cortar
# oraciones, el instalador .bat); sus literales de pantalla ya usan t().
PARTIAL = {'io_mixin.py': ('pág', 'núm', 'ÁÉÍÓÚ', 'programa', 'quedo', 'Listo:')}

ACCENTS = set('áéíóúñÁÉÍÓÚÑ¿¡')
LANGUAGE_NAMES = {'Español'}   # cada idioma se nombra a sí mismo; además es un valor


def _spanish_literals(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], 'value', None), ast.Constant):
                skip.add(id(body[0].value))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'print'):
            for sub in ast.walk(node):
                skip.add(id(sub))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in skip and n.value not in LANGUAGE_NAMES and ACCENTS & set(n.value)]


def test_no_hardcoded_spanish_ui_in_translated_modules():
    for name in TRANSLATED:
        found = _spanish_literals(os.path.join(HERE, name))
        assert not found, f'{name}: texto en español escrito en el código: {found[:3]}'


def test_no_new_hardcoded_spanish_in_io_mixin():
    found = [s for s in _spanish_literals(os.path.join(HERE, 'io_mixin.py'))
             if not any(ok in s for ok in PARTIAL['io_mixin.py'])]
    assert not found, f'io_mixin.py: texto en español escrito en el código: {found[:3]}'
