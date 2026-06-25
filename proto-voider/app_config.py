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
    return _KEY_MAP.get(key_str), mods


def _load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config = dict(DEFAULT_CONFIG)
            config.update(data)
            merged_kb = dict(DEFAULT_CONFIG['keybindings'])
            merged_kb.update(data.get('keybindings', {}))
            config['keybindings'] = merged_kb
            return config
        except Exception as e:
            print(f"⚠️ Error loading config: {e}")
    return dict(DEFAULT_CONFIG)


def _save_config(config):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error saving config: {e}")


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
