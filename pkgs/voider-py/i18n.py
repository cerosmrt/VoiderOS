"""i18n.py — el idioma de la interfaz: español e inglés, intercambiables.

Todo texto que se ve en pantalla sale de un catálogo por idioma con t('clave'). Los
catálogos viven en i18n_es.py y i18n_en.py y tienen que tener exactamente las mismas
claves (hay un test). Nada del español se borra: está completo, y el inglés es el
idioma por defecto. Se cambia en F10 (ajuste `language`), con efecto inmediato.

Una clave que falta en el idioma activo se busca en el otro; si no está en ninguno se
muestra la clave misma, para que el error se vea y no quede un texto vacío."""
import i18n_en
import i18n_es

DEFAULT_LANGUAGE = 'en'
LANGUAGES = ('en', 'es')
CATALOGS = {'en': dict(i18n_en.STRINGS), 'es': dict(i18n_es.STRINGS)}

_current = DEFAULT_LANGUAGE


def set_language(lang):
    """Activa un idioma. Uno desconocido (o vacío) vuelve al de por defecto."""
    global _current
    _current = lang if isinstance(lang, str) and lang in CATALOGS else DEFAULT_LANGUAGE


def language():
    return _current


def use_config(config):
    """Toma el idioma de config.json (clave `language`)."""
    set_language((config or {}).get('language'))


def t(key, **fmt):
    """El texto de `key` en el idioma activo, con {nombres} reemplazados por fmt."""
    text = CATALOGS[_current].get(key)
    if text is None:
        text = CATALOGS['es' if _current == 'en' else 'en'].get(key)
    if text is None:
        return key
    return text.format(**fmt) if fmt else text
