"""Idioma de la interfaz: español e inglés, intercambiables.

Todo texto que se ve en pantalla sale de un catálogo por idioma con t('clave'). Nada del
español se borra: está completo. El inglés es el idioma por defecto y se cambia en F10
(ajuste `language`) con efecto inmediato."""
import pytest

import i18n


@pytest.fixture(autouse=True)
def _restore():
    yield
    i18n.set_language('es')           # el conftest deja los tests en español


# ── t() ──────────────────────────────────────────────────────────────────────

def test_english_is_the_default_language():
    assert i18n.DEFAULT_LANGUAGE == 'en'


def test_t_returns_the_text_in_the_active_language():
    i18n.set_language('en')
    assert i18n.t('menu.file') == 'File'
    i18n.set_language('es')
    assert i18n.t('menu.file') == 'Archivo'


def test_switching_back_and_forth_gives_each_language_untouched():
    for _ in range(3):
        i18n.set_language('en')
        a = i18n.t('menu.item.print_doc')
        i18n.set_language('es')
        b = i18n.t('menu.item.print_doc')
    assert (a, b) == ('Print', 'Imprimir')


def test_language_reports_the_active_one():
    i18n.set_language('es')
    assert i18n.language() == 'es'
    i18n.set_language('en')
    assert i18n.language() == 'en'


def test_an_unknown_language_falls_back_to_the_default():
    i18n.set_language('fr')
    assert i18n.language() == i18n.DEFAULT_LANGUAGE


def test_none_or_empty_language_falls_back_to_the_default():
    for bad in (None, '', 42):
        i18n.set_language(bad)
        assert i18n.language() == i18n.DEFAULT_LANGUAGE


def test_a_missing_key_shows_the_key_itself_so_the_bug_is_visible():
    assert i18n.t('no.existe.esta.clave') == 'no.existe.esta.clave'


def test_a_key_missing_in_one_language_falls_back_to_the_other(monkeypatch):
    monkeypatch.setitem(i18n.CATALOGS['en'], 'solo.en.ingles', 'only english')
    i18n.set_language('es')
    assert i18n.t('solo.en.ingles') == 'only english'


def test_t_fills_in_named_placeholders():
    monkey = {'en': 'Saved {n} of {total}', 'es': 'Guardados {n} de {total}'}
    i18n.CATALOGS['en']['_test.fill'] = monkey['en']
    i18n.CATALOGS['es']['_test.fill'] = monkey['es']
    try:
        i18n.set_language('en')
        assert i18n.t('_test.fill', n=2, total=5) == 'Saved 2 of 5'
        i18n.set_language('es')
        assert i18n.t('_test.fill', n=2, total=5) == 'Guardados 2 de 5'
    finally:
        del i18n.CATALOGS['en']['_test.fill'], i18n.CATALOGS['es']['_test.fill']


def test_a_text_with_braces_but_no_arguments_is_left_alone():
    i18n.CATALOGS['en']['_test.braces'] = 'literal {no_args}'
    try:
        i18n.set_language('en')
        assert i18n.t('_test.braces') == 'literal {no_args}'
    finally:
        del i18n.CATALOGS['en']['_test.braces']


# ── los catálogos tienen que ser parejos ─────────────────────────────────────

def test_both_catalogs_have_exactly_the_same_keys():
    en, es = set(i18n.CATALOGS['en']), set(i18n.CATALOGS['es'])
    assert not (en - es), f'faltan en español: {sorted(en - es)}'
    assert not (es - en), f'faltan en inglés: {sorted(es - en)}'


def test_no_translation_is_empty():
    for lang, cat in i18n.CATALOGS.items():
        vacios = [k for k, v in cat.items() if not str(v).strip()]
        assert not vacios, f'{lang}: vacíos {vacios}'


def test_a_translation_uses_the_same_placeholders_in_both_languages():
    import re
    ph = lambda s: sorted(re.findall(r'\{(\w+)\}', s))
    for k in i18n.CATALOGS['en']:
        assert ph(i18n.CATALOGS['en'][k]) == ph(i18n.CATALOGS['es'][k]), k


def test_the_languages_are_really_different_where_it_matters():
    """Un catálogo copiado del otro sin traducir no sirve."""
    iguales = [k for k in i18n.CATALOGS['en']
               if i18n.CATALOGS['en'][k] == i18n.CATALOGS['es'][k] and len(i18n.CATALOGS['en'][k]) > 12]
    assert len(iguales) < 0.15 * len(i18n.CATALOGS['en']), iguales[:10]


# ── el idioma sale de la configuración ───────────────────────────────────────

def test_the_default_config_is_english():
    from app_config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG['language'] == 'en'


def test_use_config_applies_the_saved_language():
    i18n.use_config({'language': 'es'})
    assert i18n.language() == 'es'
    i18n.use_config({'language': 'en'})
    assert i18n.language() == 'en'


def test_use_config_without_a_language_uses_the_default():
    i18n.set_language('es')
    i18n.use_config({})
    assert i18n.language() == i18n.DEFAULT_LANGUAGE


def test_f10_offers_the_language_as_a_setting():
    from keys_model import SETTING_DEFS
    d = {s.key: s for s in SETTING_DEFS}['language']
    assert d.kind == 'choice' and set(d.choices) == {'en', 'es'}


def test_the_app_starts_in_the_saved_language():
    import inspect
    from new_interface import FullscreenCircleApp
    assert 'i18n.use_config' in inspect.getsource(FullscreenCircleApp.__init__)


def test_changing_the_language_in_f10_applies_it_at_once(tmp_path, monkeypatch):
    import types
    from unittest.mock import MagicMock
    import new_interface
    from new_interface import FullscreenCircleApp
    monkeypatch.setattr(new_interface, '_save_config', lambda c: None)
    app = types.SimpleNamespace(config={}, _menu_bar=MagicMock(), books_view=None,
                                _language_changed=MagicMock())
    app._on_setting_changed = types.MethodType(FullscreenCircleApp._on_setting_changed, app)
    i18n.set_language('es')
    app._on_setting_changed('language', 'en')
    assert i18n.language() == 'en'
    app._language_changed.assert_called_once()


def test_gravitor_texts_exist_in_both_languages():
    import i18n
    for key in ('gravitor.words_help', 'gravitor.search_in', 'gravitor.source.i',
                'gravitor.source.o', 'gravitor.source.both', 'gravitor.searching',
                'gravitor.cancel', 'gravitor.cancelled', 'gravitor.no_corpus'):
        for lang in ('es', 'en'):
            assert key in i18n.CATALOGS[lang], (lang, key)
    i18n.set_language('en')
    assert i18n.t('gravitor.nothing_found', summary='x') == 'Found nothing: x.'
    i18n.set_language('es')
    assert i18n.t('gravitor.nothing_found', summary='x') == 'No encontró nada: x.'
