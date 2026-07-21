# app_config.py — CONFIG_PATH, DEFAULT_CONFIG, key maps, config helpers
import os
import json
import sys
from PyQt6.QtCore import Qt, qInstallMessageHandler, QtMsgType


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    "void_dir": "",
    "book_dir": "",
    "active_file": "",
    "void_key": "enter",
    "font_family": "Consolas",
    "font_size": 11,
    # F4 reading/print font — a book serif, independent of the editing font above.
    "reading_font": "EB Garamond",
    "reading_size": 13,
    # F4 justification hyphenation (Pyphen). "auto" detects each paragraph's
    # language (book is bilingual); a lang like "es_ES" forces one; "" disables.
    "reading_hyphen_lang": "auto",
    "text_color": "#ffffff",
    "working_set_size": 100,
    "keybindings": {
        "view_f1": "F1",
        "view_f2": "F2",
        "view_f3": "F3",
        "view_f4": "F4",
        "view_f5": "F5",
        "view_f6": "F6",
        "view_f7": "F7",
        "view_f8": "F8",
        "view_f9": "F9",
        "view_f10": "F10",
        "help": "F11",
        "quit": "Escape",
        "rebase": "Ctrl+0",
        "reshuffle": "Ctrl+R",
        "opacity_up": "Ctrl+Plus",
        "opacity_down": "Ctrl+Minus",
        "file_prev": "Alt+Up",
        "file_next": "Alt+Down",
        "swap_up": "Alt+Up",
        "swap_down": "Alt+Down",
        "para_prev": "PageUp",
        "para_next": "PageDown",
        "pick_active_file": "Ctrl+F2",
        "pick_book_dir": "Ctrl+F3",
        "pick_dir": "Ctrl+F4",
        "tts_toggle": "Ctrl+T",
        "screenshot": "F12",
        "open_screenshots": "Ctrl+F12",
        "print_doc": "Ctrl+P",
        "export_doc": "Ctrl+S",
        "reformat_file": "Ctrl+Shift+F",
        "shuffle_zero": "Ctrl+Shift+R",
        "dispatch": "Ctrl+Shift+D",
        "split_chapter": "Ctrl+Shift+S",
        "merge_book": "Ctrl+Shift+M",
        "commit_void": "Ctrl+Shift+G",
        "scratch_toggle": "`",
        "title_toggle": "Ctrl+Shift+T",
        "backup": "Ctrl+B"
    }
}

_KEY_MAP = {
    'Up': Qt.Key.Key_Up, 'Down': Qt.Key.Key_Down,
    'Left': Qt.Key.Key_Left, 'Right': Qt.Key.Key_Right,
    'Escape': Qt.Key.Key_Escape, 'Return': Qt.Key.Key_Return,
    'Enter': Qt.Key.Key_Return, 'Space': Qt.Key.Key_Space,
    'F1': Qt.Key.Key_F1, 'F2': Qt.Key.Key_F2, 'F3': Qt.Key.Key_F3,
    'F4': Qt.Key.Key_F4, 'F5': Qt.Key.Key_F5, 'F6': Qt.Key.Key_F6,
    'F7': Qt.Key.Key_F7, 'F8': Qt.Key.Key_F8, 'F9': Qt.Key.Key_F9,
    'F10': Qt.Key.Key_F10, 'F11': Qt.Key.Key_F11, 'F12': Qt.Key.Key_F12,
    'PageUp': Qt.Key.Key_PageUp, 'PageDown': Qt.Key.Key_PageDown,
    '0': Qt.Key.Key_0, '9': Qt.Key.Key_9, 'R': Qt.Key.Key_R, 'P': Qt.Key.Key_P,
    'F': Qt.Key.Key_F, 'B': Qt.Key.Key_B, 'T': Qt.Key.Key_T,
    '.': Qt.Key.Key_Period, '*': Qt.Key.Key_Asterisk,
    '`': Qt.Key.Key_QuoteLeft,
    'Plus': Qt.Key.Key_Plus, 'Minus': Qt.Key.Key_Minus,
    'S': Qt.Key.Key_S,
}

_MOD_MAP = {
    'Ctrl': Qt.KeyboardModifier.ControlModifier,
    'Alt': Qt.KeyboardModifier.AltModifier,
    'Shift': Qt.KeyboardModifier.ShiftModifier,
}


def _parse_keybinding(s):
    """'Ctrl+Up' → (Qt.Key.Key_Up, Qt.KeyboardModifier.ControlModifier)"""
    parts = s.split('+')
    key_str = parts[-1]
    mods = Qt.KeyboardModifier.NoModifier
    for part in parts[:-1]:
        mods |= _MOD_MAP.get(part, Qt.KeyboardModifier.NoModifier)
    key = _KEY_MAP.get(key_str)
    if key is None:                       # any single letter/digit → Key_<X>
        key = getattr(Qt.Key, f'Key_{key_str.upper()}', None)
    return key, mods


# Volatile, per-session runtime state. These live in a separate, git-ignored
# state file (state.json) next to config.json — never in the committed config —
# so a runtime write can't churn or truncate the committed defaults/keybindings
# (and can never wipe void_dir, which would break launch).
STATE_KEYS = ('active_file', 'last_view', 'last_book_index', 'last_book_entry',
              'bg_color')


def _state_path_for(config_path):
    return os.path.join(os.path.dirname(config_path), 'state.json')


def _write_json(path, obj):
    """Atomic JSON write (tmp + os.replace) so a crash can't truncate the file."""
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"⚠️ Error writing {os.path.basename(path)}: {e}")


def _load_config_from(config_path):
    """Committed config (merged over DEFAULT_CONFIG), then runtime state overlaid
    on top. One merged dict — callers keep using self.config[...] unchanged."""
    config = dict(DEFAULT_CONFIG)
    data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading config: {e}")
    config.update(data)
    merged_kb = dict(DEFAULT_CONFIG['keybindings'])
    merged_kb.update(data.get('keybindings', {}))
    config['keybindings'] = merged_kb
    sp = _state_path_for(config_path)
    if os.path.exists(sp):
        try:
            with open(sp, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except Exception as e:
            print(f"⚠️ Error loading state: {e}")
    return config


def _save_config_to(config_path, config):
    """Runtime-state keys → state.json (always). Non-state keys → config.json only
    when their content actually changed, so ordinary navigation never rewrites the
    committed config (no git churn, no truncation risk)."""
    _write_json(_state_path_for(config_path),
                {k: config[k] for k in STATE_KEYS if k in config})
    rest = {k: v for k, v in config.items() if k not in STATE_KEYS}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cur = json.load(f)
    except Exception:
        cur = None
    if cur != rest:
        _write_json(config_path, rest)


def _load_config():
    return _load_config_from(CONFIG_PATH)


def _save_config(config):
    _save_config_to(CONFIG_PATH, config)


def _clean_book_title(fname):
    """Parse a book filename into a clean human-readable title.

    Strips: .txt extension, Project Gutenberg noise, 'by Author' suffixes,
    underscores, leading numeric Gutenberg IDs (e.g. pg1234-).
    """
    import re
    name = os.path.splitext(fname)[0]
    name = re.sub(r'^pg\d+[-_]?\d*[-_]?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^\d+[-_]', '', name)
    name = name.replace('_', ' ').replace('-', ' ')
    name = re.sub(r'\bproject\s+gutenberg\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bebook\s+of\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\bthe\s+ebook\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+by\s+[A-Z][a-zA-Z\s]+$', '', name)
    name = re.sub(r'\s{2,}', ' ', name).strip()
    if name and (name.islower() or name.isupper()):
        name = name.title()
    return name or fname


def _qt_msg_handler(msg_type, context, message):
    if 'Painter not active' in message or 'Paint device returned engine == 0' in message:
        return
    import sys
    print(message, file=sys.stderr)

qInstallMessageHandler(_qt_msg_handler)
