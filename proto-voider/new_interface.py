# new_interface.py - App principal con sistema de 2 vistas + vault (F3)
import os
import sys
import json
import random
import datetime
import shutil
import subprocess
import threading
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QFileDialog, QLineEdit
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtGui import QFont, QCursor, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, QTimer, qInstallMessageHandler, QtMsgType

from files import setup_file_handling, void_line
from controls import setup_controls
from line_ring import LineRing
from circular_view import CircularView
from widgets import CustomLineEdit
from views import NormalView
from metronome_view import MetronomeView
from fx_panel import FxPanel
from help_overlay import HelpOverlay


def _qt_msg_handler(msg_type, context, message):
    if 'Painter not active' in message or 'Paint device returned engine == 0' in message:
        return
    import sys
    print(message, file=sys.stderr)

qInstallMessageHandler(_qt_msg_handler)

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
    'F11': Qt.Key.Key_F11, 'F12': Qt.Key.Key_F12,
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


def _zodiac_sign(month, day):
    """Return the Spanish zodiac sign name for a given month/day."""
    if (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return 'capricornio'
    elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
        return 'acuario'
    elif (month == 2 and day >= 19) or (month == 3 and day <= 20):
        return 'piscis'
    elif (month == 3 and day >= 21) or (month == 4 and day <= 19):
        return 'aries'
    elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
        return 'tauro'
    elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
        return 'geminis'
    elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
        return 'cancer'
    elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
        return 'leo'
    elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
        return 'virgo'
    elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
        return 'libra'
    elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
        return 'escorpio'
    else:
        return 'sagitario'



class FullscreenCircleApp(QMainWindow):
    """
    F1: center entry — write/navigate active file
    F2: circular view — edit/swap active file lines
    F3: book browser — navigate/reorder files in current book folder
    F4: vault browser — browse shuffled lines from void folder, pick into active file
    """

    def __init__(self):
        super().__init__()

        self.config = _load_config()
        self._kb = {
            action: _parse_keybinding(ks)
            for action, ks in self.config.get('keybindings', {}).items()
        }

        # Resolve void_dir: config → dialog
        void_dir = self.config.get('void_dir', '')
        if not void_dir or not os.path.isdir(void_dir):
            void_dir = self._pick_void_directory()
            if not void_dir:
                sys.exit(0)
            self.config['void_dir'] = void_dir
            _save_config(self.config)

        self.void_dir = void_dir

        # Resolve book_dir: config → default to void_dir
        book_dir = self.config.get('book_dir', '')
        if not book_dir or not os.path.isdir(book_dir):
            book_dir = void_dir
        self.book_dir = book_dir

        # Resolve active_file: config → default to book_dir/0.txt
        active_file = self.config.get('active_file', '')
        if not active_file or not os.path.isfile(active_file):
            active_file = os.path.join(self.book_dir, '0.txt')
        self.book_files = []      # kept for compatibility
        self.book_ring = LineRing()
        self._library_lines = []  # raw lines from library.txt (filenames + '.')
        self._library_path_cache = {}  # filename → absolute path

        self.tts_active = False
        self._tts_process = None
        self._tts_prefetch_data = None
        self._tts_prefetch_text = None
        self._tts_timer = QTimer(self)
        self._tts_timer.setInterval(50)
        self._tts_timer.timeout.connect(self._tts_poll)

        self.opacity = 1.0
        self._setup_opacity_shortcuts()
        self.txt_files = []
        self.current_file_index = 0
        self.current_view = 0  # 0=F1, 1=F2, 2=F3(book), 3=F4(vault)
        self.use_spacebar_for_void = self.config.get('void_key', 'enter') == 'space'
        self._pending_vault_remove = False  # True when staging a vault line in F1
        self._para_focus = False            # True when in paragraph focus mode
        self._para_focus_content = []       # Ordered list of absolute ring indices for focused paragraph

        # Font / color from config
        _font_family = self.config.get('font_family', 'Consolas')
        _font_size = int(self.config.get('font_size', 11))
        _text_color = self.config.get('text_color', '#ffffff')
        self._app_font = QFont(_font_family, _font_size)

        # Window setup
        self.setWindowTitle("Voider")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setCursor(QCursor(Qt.CursorShape.BlankCursor))
        self.setStyleSheet("background-color: black; color: white;")

        # Entry (F1)
        self.entry = CustomLineEdit(self)
        self.entry.setFont(self._app_font)
        self.entry.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {_text_color};
                border: none;
                selection-background-color: {_text_color};
                selection-color: black;
            }}
        """)
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.setFocus()

        # Search bars (F2 and F3) — hidden by default, shown at bottom of screen
        _search_style = f"""
            QLineEdit {{
                background: transparent;
                color: {_text_color};
                border: none;
                border-bottom: 1px solid {_text_color};
                selection-background-color: {_text_color};
                selection-color: black;
            }}
        """
        self._f2_search_bar = QLineEdit(self)
        self._f2_search_bar.setFont(self._app_font)
        self._f2_search_bar.setStyleSheet(_search_style)
        self._f2_search_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f2_search_bar.setPlaceholderText('search lines…')
        self._f2_search_bar.hide()
        self._f2_search_bar.textChanged.connect(self._f2_search_changed)
        self._f2_search_bar.returnPressed.connect(self._f2_search_confirm)

        self._f3_search_bar = QLineEdit(self)
        self._f3_search_bar.setFont(self._app_font)
        self._f3_search_bar.setStyleSheet(_search_style)
        self._f3_search_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f3_search_bar.setPlaceholderText('search files…')
        self._f3_search_bar.hide()
        self._f3_search_bar.textChanged.connect(self._f3_search_changed)
        self._f3_search_bar.returnPressed.connect(self._f3_search_confirm)

        # Doc ring (active file lines, ordered) and vault ring (void files, shuffled)
        self.line_ring = LineRing()
        self.vault_ring = LineRing()

        # O/ state — F5/F6/F7/F8
        self.o_dir = os.path.join(self.void_dir, 'O')
        self.o_browser_files = []   # relative paths to .txt files in O/
        self.o_browser_ring = LineRing(['.'])
        self.o_reader_ring = LineRing(['.'])
        self.o_reader_file = None   # currently open O/ book path
        self.o_reader_line_idx = 0  # line index forked into F5
        self.oracle_o_ring = LineRing(['.', '...'])
        # Working set: 100-book window, persisted across sessions
        self._ws_loaded = False
        self._ws_books = []  # [{"path": str, "position": int}, ...]
        self._ws_browser_index = 1  # last highlighted position in F7 browser
        self._ws_all_o_files = []   # full O/ file list, loaded from cache at startup

        # View stack
        self.stack = QStackedWidget()
        self.normal_view = NormalView(self)
        self.circular_view = None   # F2: CircularView over doc ring
        self.scratch_view = None    # F1 Tab: CircularView of 0.txt scratch pool
        self._f1_scratch_mode = False
        self.book_view = None       # F3: CircularView over book_ring (filenames)
        self.book_concat_view = None          # view 9: read-only concatenated group
        self.book_concat_ring = LineRing(['.'])
        self._book_concat_header_indices = set()
        self._book_pending_new = False        # True while user names a new F3 entry
        self._book_last_index = 0             # remembered F3 cursor (for re-entry)
        # Search state — display rings are separate from real rings (never mutated)
        self._f2_search_active = False
        self._f2_search_saved = None   # saved cursor index before search
        self._f2_display_ring = None   # temp ring shown during search
        self._f3_search_active = False
        self._f3_search_saved = None   # saved cursor index before search
        self._f3_display_ring = None   # temp ring shown during search
        self.vault_view = None      # F4: Oracle from I/
        self.transform_view = None  # F5: Transform — editable O/ line → I/
        self.o_reader_view = None   # F6: Reader — circular view of O/ book
        self.o_browser_view = None  # F7: Book browser for O/
        self.oracle_o_view = None   # F8: Oracle from O/
        self.metronome_view = None  # F9: Metronome/tempo
        self._help_overlay = None   # F11: Help/instructions
        self.stack.addWidget(self.normal_view)

        # File setup — F1 is always 0.txt; F2 follows F3 selection
        self.f1_file = os.path.join(self.void_dir, 'I', '0.txt')
        os.makedirs(os.path.join(self.void_dir, 'I'), exist_ok=True)
        if not os.path.exists(self.f1_file):
            open(self.f1_file, 'w', encoding='utf-8').close()
        self.f2_file = active_file if active_file and os.path.isfile(active_file) else self.f1_file
        self.current_file_path = self.f1_file  # F1 starts on 0.txt
        self.void_file_path = self.f1_file     # fallback when a file is emptied/deleted
        os.makedirs(self.book_dir, exist_ok=True)
        # Migrate library.txt → I.txt
        _old_lib = os.path.join(self.void_dir, 'library.txt')
        _new_lib = os.path.join(self.void_dir, 'I.txt')
        if os.path.exists(_old_lib) and not os.path.exists(_new_lib):
            try:
                os.rename(_old_lib, _new_lib)
                print("📚 Migrated library.txt → I.txt")
            except Exception as _e:
                print(f"⚠️ Could not migrate library.txt: {_e}")
        if not os.path.exists(self.f2_file):
            open(self.f2_file, 'w', encoding='utf-8').close()

        self.scan_txt_files()
        setup_file_handling(self)
        setup_controls(self)

        self.load_doc_lines()
        self.load_vault_lines()
        # Load O/ file list from disk cache, then rebuild in background to catch new books
        self._ws_load_o_files_cache()
        self._ws_rebuild_o_files_cache()
        # NOTE: the stray-0.txt merge is NO LONGER run automatically at startup.
        # It deleted files (every subfolder 0.txt + any dots-only .txt) with no
        # confirmation, and raced with load_doc_lines on the same 0.txt. It is now
        # available only on demand via Ctrl+Shift+F in F3 (_merge_zero_files).
        # Generate I_preview.txt from current folder structure
        self._generate_i_preview()

        # Void key connection
        self._print_void_mode_status()
        self._void_enter_connection = None
        self._void_space_connection = None
        self._connect_void_key()
        # F1 scratch mode removed: Tab now recycles a random line (see widgets.py).
        # The scratch 0.txt is still reachable as a circular view via the '0' portal → F2.

        self.init_ui()
        self.switch_to_view(0)
        self.entry.clear()

    # ── Directory picker ──────────────────────────────────────────────────────

    def _pick_void_directory(self):
        path = QFileDialog.getExistingDirectory(
            None,
            "Select Void Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        return path or None

    def change_void_directory(self):
        new_dir = self._pick_void_directory()
        if not new_dir or new_dir == self.void_dir:
            return
        self.void_dir = new_dir
        self.f1_file = os.path.join(new_dir, 'I', '0.txt')
        self.void_file_path = self.f1_file
        self.config['void_dir'] = new_dir
        _save_config(self.config)
        os.makedirs(self.void_dir, exist_ok=True)

        self.scan_txt_files()
        self.load_vault_lines()
        self.switch_to_view(self.current_view)
        print(f"📁 Void dir changed to: {new_dir}")

    # ── Backup ───────────────────────────────────────────────────────────────

    def _backup_vault(self):
        """Ctrl+B: pick a destination folder, copy void_dir there.
        Folder name: {voidname}_{YY}-{MM}-{DD}({n})
        where n is how many backups of this vault already exist in that destination."""
        dest_root = QFileDialog.getExistingDirectory(
            self, "Backup destination folder", os.path.expanduser("~"))
        if not dest_root:
            return  # cancelled
        try:
            now = datetime.datetime.now()
            src_dir = self.void_dir
            vault_name = os.path.basename(os.path.normpath(src_dir))
            date_str = now.strftime(f'{str(now.year)[2:]}-{now.strftime("%m-%d")}')
            prefix = f"{vault_name}_{date_str}"
            # Count existing backups of this vault on this date
            existing = [d for d in os.listdir(dest_root)
                        if os.path.isdir(os.path.join(dest_root, d))
                        and d.startswith(f"{prefix}")]
            n = len(existing) + 1
            folder_name = f"{prefix}({n})"
            backup_dest = os.path.join(dest_root, folder_name)
            os.makedirs(backup_dest, exist_ok=True)
            count = 0
            for root, dirs, files in os.walk(src_dir):
                for fname in files:
                    if not fname.lower().endswith('.txt'):
                        continue
                    src = os.path.join(root, fname)
                    rel = os.path.relpath(root, src_dir)
                    dst_dir = os.path.join(backup_dest, rel)
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.copy2(src, os.path.join(dst_dir, fname))
                    count += 1
            print(f"📦 Backup: {count} archivos → {folder_name}")
        except Exception as e:
            print(f"⚠️ Backup error: {e}")

    # ── Loaders ───────────────────────────────────────────────────────────────

    def load_doc_lines(self):
        """Load active file into the doc ring (ordered, no shuffle). Preserves index."""
        doc_path = self.current_file_path
        lines = []
        read_failed = False
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                for raw in f:
                    s = raw.strip()
                    if s:
                        lines.append(s)
        except FileNotFoundError:
            # Genuinely absent file → an empty doc is correct, saving is safe.
            pass
        except Exception as e:
            # Transient/permission/decode error on an EXISTING file. Do NOT load an
            # empty ring — a subsequent save would overwrite the file with just a dot.
            read_failed = True
            print(f"⚠️ Error reading {os.path.basename(doc_path)}: {e}")
        # Block saves whenever a read of an existing file failed, so live-save and
        # auto_save_circular cannot clobber the on-disk content we couldn't read.
        self._doc_load_failed = read_failed
        # Ensure a leading dot so the last paragraph and first paragraph
        # are always separated when wrapping around the ring.
        if lines and lines[0] != '.':
            lines.insert(0, '.')
        self.line_ring = LineRing(lines or ["."])
        self._restore_last_line()
        # Empty doc (only dots) that loaded cleanly: append a blank editable line and
        # park the cursor on it, so F2 shows a blinking cursor to start typing into
        # (otherwise the only line is a read-only dot you can't write on). The blank
        # line isn't persisted until you type — live-save ignores empty text and
        # reload strips blank lines.
        if not read_failed and not any(l != '.' for l in self.line_ring.lines):
            self.line_ring.lines.append('')
            self.line_ring.index = len(self.line_ring.lines) - 1
        if self.circular_view:
            self.circular_view.ring = self.line_ring
            self.circular_view._offset = 0.0
        print(f"📄 {len(lines)} lines loaded from {os.path.basename(doc_path)}")

    def _pick_oracle_line(self, source_dir):
        """Pick one random non-empty, non-dot line from source_dir."""
        txt_files = []
        for root, _, files in os.walk(source_dir):
            for f in files:
                if f.lower().endswith('.txt') and f.lower() != '0.txt':
                    txt_files.append(os.path.join(root, f))
        if not txt_files:
            return "..."
        for _ in range(20):
            fpath = random.choice(txt_files)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [l.strip() for l in f if l.strip() and l.strip() != '.']
                if lines:
                    return random.choice(lines)
            except Exception:
                continue
        return "..."

    def _refresh_oracle(self):
        """Pick a fresh oracle line from I/ and update the vault ring."""
        source = os.path.join(self.void_dir, 'I')
        line = self._pick_oracle_line(source)
        self.vault_ring = LineRing(['.', line])
        self.vault_ring.index = 1
        if self.vault_view:
            self.vault_view.ring = self.vault_ring
            self.vault_view._offset = 0.0
        print(f"🔮 Oracle: '{line[:80]}'")

    def load_vault_lines(self):
        self._refresh_oracle()

    # ── Config / keybinding helpers ───────────────────────────────────────────

    def _matches(self, key, modifiers, action):
        kb = self._kb.get(action)
        return kb is not None and key == kb[0] and modifiers == kb[1]

    # ── Void key ─────────────────────────────────────────────────────────────

    def _print_void_mode_status(self):
        print("VOID MODE:", "Spacebar" if self.use_spacebar_for_void else "Enter")

    def _connect_void_key(self):
        self._disconnect_void_key()
        if self.use_spacebar_for_void:
            self._void_space_connection = self.entry.spacePressed.connect(self._handle_void_line)
        else:
            self._void_enter_connection = self.entry.returnPressed.connect(self._handle_void_line)

    def _handle_void_line(self):
        if self.current_view == 4:
            self._f5_fork()
            return
        void_line(self)
        self.load_doc_lines()
        if hasattr(self, 'last_inserted_index') and self.last_inserted_index is not None:
            self.line_ring.index = min(self.last_inserted_index, len(self.line_ring.lines) - 1)

    def _f5_fork(self):
        text = self.entry.text().strip()
        if not text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        self.o_reader_ring.move(1)
        while self.o_reader_ring.current() in ('.', ''):
            self.o_reader_ring.move(1)
        self.entry.setText(self.o_reader_ring.current())
        self.entry.setCursorPosition(len(self.entry.text()))
        print(f"✅ F5 fork→I/[{insert_pos}]: '{text}'")

    def _f5_navigate(self, delta):
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() in ('.', ''):
            self.o_reader_ring.move(delta)
        self.entry.setText(self.o_reader_ring.current())
        self.entry.setCursorPosition(len(self.entry.text()))

    def _disconnect_void_key(self):
        if self._void_enter_connection:
            try:
                self.entry.returnPressed.disconnect(self._void_enter_connection)
            except Exception:
                pass
            self._void_enter_connection = None
        if self._void_space_connection:
            try:
                self.entry.spacePressed.disconnect(self._void_space_connection)
            except Exception:
                pass
            self._void_space_connection = None

    def toggle_void_key_mode(self):
        self.use_spacebar_for_void = not self.use_spacebar_for_void
        self.config['void_key'] = 'space' if self.use_spacebar_for_void else 'enter'
        _save_config(self.config)
        self._print_void_mode_status()
        self._connect_void_key()

    # ── Views ─────────────────────────────────────────────────────────────────

    def switch_to_view(self, view_index):
        # Close search bars when leaving their view
        if self._f2_search_active and view_index != 1:
            self._close_f2_search(restore=True)
        if self._f3_search_active and view_index != 2:
            self._close_f3_search(restore=True)
        # F3 → F2: point F2 at the highlighted book then load it
        if self.current_view == 2 and view_index == 1:
            if not self._book_try_rename():
                return
            fname = self._library_current_fname()
            if fname:
                fpath = self._library_path_cache.get(fname)
                if fpath:
                    self._set_f2_file(fpath)
        # Save last line when leaving F2
        if self.current_view == 1:
            self._save_last_line()
        # Save reading position when leaving F6
        if self.current_view == 5:
            self._ws_save_position()
        # F7 → F6: load the highlighted book into the reader on demand
        if self.current_view == 6 and view_index == 5:
            slot = self._ws_cur_slot()
            if slot is not None and not self._ws_slot_is_empty(self._ws_books[slot]):
                fpath = os.path.join(self.o_dir, self._ws_books[slot]['path'])
                if os.path.exists(fpath):
                    self._load_o_reader(fpath)
        # Save F7 browser position when leaving F7
        if self.current_view == 6:
            self._ws_browser_index = self.o_browser_ring.index
            self._save_working_set()
        # Cancel staged vault line if user navigates away without voiding
        if view_index == 3:
            self._pending_vault_remove = False
        # Reset F1 scratch mode when leaving F1
        if self.current_view == 0 and self._f1_scratch_mode and view_index != 0:
            self._f1_scratch_mode = False
            if self.scratch_view:
                self.scratch_view.edit_mode = False
                self.scratch_view.editor.hide()
        old_view = self.current_view
        # Remember which F3 entry we were on, so re-entering F3 returns to the same
        # one (e.g. a specific '0' portal) instead of snapping to the first match.
        if old_view == 2 and self.book_ring.lines:
            self._book_last_index = self.book_ring.index
        self.current_view = view_index
        print(f"📍 F{old_view+1} → F{view_index+1} | Index: {self.line_ring.index} | Line: '{self.line_ring.current()}'")

        if view_index == 0:  # F1 — always 0.txt, entry starts blank
            # Fork only from F6 (O/ reader) — F2 fork is handled explicitly by _doc_confirm_edit
            fork_line = None
            if old_view == 5:
                cur = self.o_reader_ring.current()
                if cur and cur != '.':
                    fork_line = cur
            if self.current_file_path != self.f1_file:
                self.current_file_path = self.f1_file
                self.load_doc_lines()
            if self.circular_view:
                self.circular_view.edit_mode = False
                self.circular_view.editor.hide()
            if self.book_view:
                self.book_view.edit_mode = False
                self.book_view.editor.hide()
            self._f1_scratch_mode = False
            if self.scratch_view:
                self.scratch_view.edit_mode = False
                self.scratch_view.editor.hide()
            self.stack.setCurrentWidget(self.normal_view)
            self.entry.show()
            self.entry.raise_()
            if fork_line:
                # Pre-fill with the F2 line so user can edit and re-void it
                self.entry.setText(fork_line)
                self.entry.selectAll()
            else:
                self.entry.clear()
            self.entry.setFocus()

        elif view_index == 1:  # F2 — circular doc view (follows F3 selection)
            if getattr(self, '_f2_peek_0', False):
                self._f2_peek_0 = False
                self.current_file_path = self.f1_file
                self.load_doc_lines()
            elif self.current_file_path != self.f2_file:
                self.current_file_path = self.f2_file
                self.load_doc_lines()
            if not self.circular_view:
                self.circular_view = CircularView(self.line_ring, self)
                self.circular_view.zero_marker = True
                self.circular_view.setFont(self._app_font)
                self.circular_view.editor.returnPressed.disconnect()
                self.circular_view.editor.returnPressed.connect(self._doc_confirm_edit)
                self.circular_view.editor.textEdited.connect(self._doc_live_save)
                self.circular_view.editor.upPressed.connect(lambda: self._doc_navigate(-1))
                self.circular_view.editor.downPressed.connect(lambda: self._doc_navigate(1))
                self.circular_view.editor.backspaceAtStart.connect(self._doc_join_prev)
                self.circular_view.editor.splitAtCursor.connect(self._doc_split_line)
                self.circular_view.editor.wordSwapLeft.connect(lambda: self._swap_words(-1))
                self.circular_view.editor.wordSwapRight.connect(lambda: self._swap_words(1))
                self.circular_view.editor.deleteLineToZero.connect(self._delete_line_to_zero)
                self.circular_view.editor.deleteAtEnd.connect(self._doc_join_next)
                self.circular_view.editor.tabPressed.connect(self._doc_tab)
                self.stack.addWidget(self.circular_view)
            else:
                self.circular_view.ring = self.line_ring
                self.circular_view._offset = 0.0

            self.stack.setCurrentWidget(self.circular_view)
            self.entry.hide()
            self.circular_view.update()
            self._doc_show_editor()

        elif view_index == 2:  # F3 — book browser (library.txt)
            self._load_library()
            if not self.book_view:
                self.book_view = CircularView(self.book_ring, self)
                self.book_view.zero_marker = False
                self.book_view.setFont(self._app_font)
                self.book_view.editor.returnPressed.disconnect()
                self.book_view.editor.returnPressed.connect(self._book_confirm_edit)
                self.book_view.editor.splitAtCursor.connect(lambda pos: self._book_confirm_edit())
                self.book_view.editor.upPressed.connect(lambda: self._book_navigate(-1))
                self.book_view.editor.downPressed.connect(lambda: self._book_navigate(1))
                self.book_view.editor.dotPressed.connect(self._book_insert_separator)
                self.book_view.editor.shiftReturnPressed.connect(self._book_new_entry)
                self.book_view.editor.ctrlDeletePressed.connect(self._book_send_to_zero)
                self.book_view.editor.tabPressed.connect(self._book_random)
                self.book_view.editor.intercept_period = True
                self.stack.addWidget(self.book_view)
            else:
                self.book_view.ring = self.book_ring
                self.book_view._offset = 0.0
            # Sync cursor to the active F2 file (including 0.txt). If the entry we
            # last sat on still points at that same file (e.g. the specific '0'
            # portal we used), return to it instead of snapping to the first match —
            # so multiple '0' portals are each individually reachable.
            active_fname = os.path.basename(self.f2_file)
            last = getattr(self, '_book_last_index', None)
            if (last is not None and 0 <= last < len(self._library_lines)
                    and self._library_lines[last] == active_fname):
                self.book_ring.index = last
            else:
                try:
                    self.book_ring.index = self._library_lines.index(active_fname)
                except ValueError:
                    pass
            self.stack.setCurrentWidget(self.book_view)
            self.entry.hide()
            self.book_view.update()
            self._book_show_editor()

        elif view_index == 3:  # F4 — oracle (lazy, picks from I/)
            self._refresh_oracle()
            if not self.vault_view:
                self.vault_view = CircularView(self.vault_ring, self)
                self.vault_view.setFont(self._app_font)
                self.vault_view.editor.returnPressed.disconnect()
                self.vault_view.editor.returnPressed.connect(self._vault_confirm_edit)
                self.vault_view.editor.upPressed.connect(lambda: self._vault_navigate(-1))
                self.vault_view.editor.downPressed.connect(lambda: self._vault_navigate(1))
                self.stack.addWidget(self.vault_view)
            else:
                self.vault_view.ring = self.vault_ring
                self.vault_view._offset = 0.0

            self.stack.setCurrentWidget(self.vault_view)
            self.entry.hide()
            self.vault_view.update()
            self._vault_show_editor()

        elif view_index == 4:  # F5 — mirrors F1 but for O/: edit a forked line, Enter → I/
            self.stack.setCurrentWidget(self.normal_view)
            self.entry.show()
            self.entry.raise_()
            cur = self.o_reader_ring.current()
            self.entry.setText('' if not cur or cur == '.' else cur)
            self.entry.setCursorPosition(len(self.entry.text()))
            self.entry.setFocus()

        elif view_index == 5:  # F6 — reader: circular view of O/ book (read-only)
            if not self.o_reader_view:
                self.o_reader_view = CircularView(self.o_reader_ring, self)
                self.o_reader_view.setFont(self._app_font)
                self.o_reader_view.editor.returnPressed.disconnect()
                self.o_reader_view.editor.returnPressed.connect(lambda: self.switch_to_view(0))
                self.o_reader_view.editor.upPressed.connect(lambda: self._reader_navigate(-1))
                self.o_reader_view.editor.downPressed.connect(lambda: self._reader_navigate(1))
                self.o_reader_view.editor.tabPressed.connect(self._reader_random_line)
                self.stack.addWidget(self.o_reader_view)
            else:
                self.o_reader_view.ring = self.o_reader_ring
                self.o_reader_view._offset = 0.0
            self.stack.setCurrentWidget(self.o_reader_view)
            self.entry.hide()
            self.o_reader_view.update()
            self._reader_show_editor()

        elif view_index == 6:  # F7 — O/ book browser
            self._load_o_browser()
            # Restore last cursor position in the browser
            n = len(self.o_browser_ring.lines)
            idx = self._ws_browser_index
            if 0 < idx < n:
                self.o_browser_ring.index = idx
                if self.o_browser_ring.current() == '.':
                    self.o_browser_ring.move(1)
            if not self.o_browser_view:
                self.o_browser_view = CircularView(self.o_browser_ring, self)
                self.o_browser_view.setFont(self._app_font)
                self.o_browser_view.editor.returnPressed.disconnect()
                self.o_browser_view.editor.returnPressed.connect(self._o_browser_open)
                self.o_browser_view.editor.upPressed.connect(lambda: self._o_browser_navigate(-1))
                self.o_browser_view.editor.downPressed.connect(lambda: self._o_browser_navigate(1))
                self.o_browser_view.editor.tabPressed.connect(self._ws_tab_randomize)
                self.o_browser_view.editor.shiftReturnPressed.connect(self._ws_add_slot)
                self.o_browser_view.editor.ctrlDeletePressed.connect(self._ws_remove_slot)
                self.stack.addWidget(self.o_browser_view)
            else:
                self.o_browser_view.ring = self.o_browser_ring
                self.o_browser_view._offset = 0.0
            self.stack.setCurrentWidget(self.o_browser_view)
            self.entry.hide()
            self.o_browser_view.update()
            self._o_browser_show_editor()

        elif view_index == 7:  # F8 — oracle from O/ (lazy)
            self._refresh_oracle_o()
            if not self.oracle_o_view:
                self.oracle_o_view = CircularView(self.oracle_o_ring, self)
                self.oracle_o_view.setFont(self._app_font)
                self.oracle_o_view.editor.returnPressed.disconnect()
                self.oracle_o_view.editor.returnPressed.connect(self._oracle_o_confirm)
                self.oracle_o_view.editor.upPressed.connect(lambda: self._oracle_o_navigate(-1))
                self.oracle_o_view.editor.downPressed.connect(lambda: self._oracle_o_navigate(1))
                self.stack.addWidget(self.oracle_o_view)
            else:
                self.oracle_o_view.ring = self.oracle_o_ring
                self.oracle_o_view._offset = 0.0
            self.stack.setCurrentWidget(self.oracle_o_view)
            self.entry.hide()
            self.oracle_o_view.update()
            self._oracle_o_show_editor()

        elif view_index == 8:  # F9 — metronome
            if not self.metronome_view:
                self.metronome_view = MetronomeView(self)
                self.stack.addWidget(self.metronome_view)
            self.stack.setCurrentWidget(self.metronome_view)
            self.entry.hide()
            self.metronome_view.activate()

        elif view_index == 9:  # Book concat — read-only group view (Enter on dot in F3)
            if not self.book_concat_view:
                self.book_concat_view = CircularView(self.book_concat_ring, self)
                self.book_concat_view.setFont(self._app_font)
                self.book_concat_view.editor.returnPressed.disconnect()
                self.book_concat_view.editor.returnPressed.connect(lambda: self.switch_to_view(2))
                self.book_concat_view.editor.upPressed.connect(lambda: self._book_concat_navigate(-1))
                self.book_concat_view.editor.downPressed.connect(lambda: self._book_concat_navigate(1))
                self.stack.addWidget(self.book_concat_view)
            else:
                self.book_concat_view.ring = self.book_concat_ring
                self.book_concat_view._offset = 0.0
            self.stack.setCurrentWidget(self.book_concat_view)
            self.entry.hide()
            self.book_concat_view.update()
            self._book_concat_show_editor()

        self._tts_on_view(view_index)

    def auto_save_circular(self):
        """Save doc ring state to active file (atomic write)."""
        import tempfile
        if getattr(self, '_doc_load_failed', False):
            print("⛔ Save blocked: active file failed to load; refusing to overwrite it.")
            return
        doc_path = self.current_file_path
        dir_path = os.path.dirname(doc_path) or '.'
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for line in self.line_ring.lines:
                        f.write(line + '\n')
                os.replace(tmp_path, doc_path)
            except Exception:
                os.unlink(tmp_path)
                raise
            print(f"💾 Saved to 0.txt (index={self.line_ring.index})")
        except Exception as e:
            print(f"❌ Save error: {e}")

    def _atomic_write_lines(self, path, lines, backup=False):
        """Write lines to path crash-safely (temp file + os.replace).

        If backup=True, copy the existing file to path+'.bak' first so a bad
        rewrite (e.g. reformat) can be undone. Each item in `lines` is written
        with a trailing newline. Returns True on success.
        """
        import tempfile, shutil
        if backup and os.path.exists(path):
            try:
                shutil.copy2(path, path + '.bak')
            except Exception as e:
                print(f"⚠️ Could not write backup {os.path.basename(path)}.bak: {e}")
        dir_path = os.path.dirname(path) or '.'
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    for line in lines:
                        f.write(line + '\n')
                os.replace(tmp_path, path)
                return True
            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise
        except Exception as e:
            print(f"❌ Write error on {os.path.basename(path)}: {e}")
            return False

    # ── Reformat ─────────────────────────────────────────────────────────────

    def _generate_i_preview(self):
        """On startup: create CAPS title files and write I_preview.txt to I/."""
        i_dir = os.path.join(self.void_dir, 'I')
        preview_fname = 'I_preview.txt'
        preview_path = os.path.join(i_dir, preview_fname)
        skip_lower = {'0.txt', 'i_preview.txt'}

        # Create CAPS prologue files for each direct I/ subfolder (skip 0/ — reserved)
        try:
            for entry in os.scandir(i_dir):
                if not entry.is_dir():
                    continue
                caps_name = entry.name.upper() + '.txt'
                if caps_name.lower() in skip_lower:
                    continue
                caps_path = os.path.join(i_dir, caps_name)
                if not os.path.exists(caps_path):
                    open(caps_path, 'w', encoding='utf-8').close()
        except Exception as e:
            print(f"⚠️ I_preview CAPS error: {e}")

        # Walk every directory in I/ and collect files directly inside each one
        raw = []  # list of (abs_path, [filenames])
        try:
            for dirpath, dirs, files in os.walk(i_dir):
                dirs.sort(key=lambda x: x.lower())
                txts = sorted(
                    [f for f in files
                     if f.lower().endswith('.txt') and f.lower() not in skip_lower],
                    key=lambda x: x.lower()
                )
                if txts:
                    raw.append((dirpath, txts))
        except Exception as e:
            print(f"⚠️ I_preview walk error: {e}")

        if not raw:
            return

        # Put I/ root group last (CAPS + stray files); subfolders first
        subdir_groups = [(p, f) for p, f in raw if p != i_dir]
        root_group    = [(p, f) for p, f in raw if p == i_dir]
        ordered = subdir_groups + root_group

        # Compute labels: leaf folder name; add parent/ prefix on collision
        leaf_names = [os.path.basename(p) for p, _ in ordered]
        counts = {}
        for n in leaf_names:
            counts[n.lower()] = counts.get(n.lower(), 0) + 1

        groups = []
        for path, filenames in ordered:
            leaf = os.path.basename(path)
            if path == i_dir:
                label = 'I/'
            elif counts.get(leaf.lower(), 0) > 1:
                parent = os.path.basename(os.path.dirname(path))
                label = f'{parent}/{leaf}/'
            else:
                label = f'{leaf}/'
            groups.append((label, filenames))

        # Resolve duplicate filenames across groups with _2, _3 … suffix
        seen = {}
        def resolve(fname):
            key = fname.lower()
            if key not in seen:
                seen[key] = True
                return fname
            stem, ext = os.path.splitext(fname)
            i = 2
            while f'{stem}_{i}{ext}'.lower() in seen:
                i += 1
            new = f'{stem}_{i}{ext}'
            seen[new.lower()] = True
            return new

        lines = []
        for label, filenames in groups:
            lines.append('.')
            lines.append(label)
            for f in filenames:
                lines.append(resolve(f))

        try:
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except Exception as e:
            print(f"⚠️ Could not write I_preview.txt: {e}")
            return

        # Add I_preview.txt + CAPS files to I.txt so they appear in F3
        lib_path = self._library_path()
        if os.path.exists(lib_path):
            try:
                with open(lib_path, 'r', encoding='utf-8') as f:
                    lib_lines = [l.rstrip('\n') for l in f]
                to_add = [preview_fname]
                for entry in os.scandir(i_dir):
                    if not entry.is_dir():
                        continue
                    caps = entry.name.upper() + '.txt'
                    if caps.lower() not in skip_lower:
                        to_add.append(caps)
                changed = False
                for fname in to_add:
                    if fname not in lib_lines:
                        lib_lines.append(fname)
                        changed = True
                if changed:
                    with open(lib_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lib_lines) + '\n')
            except Exception as e:
                print(f"⚠️ Could not update I.txt: {e}")

        n = sum(len(g[1]) for g in groups)
        print(f"📋 I_preview.txt: {n} entries across {len(groups)} groups")

    def _merge_zero_files(self, silent=True):
        """Absorb every I/ subdirectory 0.txt into ~/void/I/0.txt.

        Runs at startup (silent, background) and on Ctrl+Shift+F in F3
        (explicit, refreshes the view after merging).
        """
        root_zero = self.f1_file
        i_dir = os.path.join(self.void_dir, 'I')
        absorbed = []
        deleted_empty = []

        for dirpath, _, filenames in os.walk(i_dir):
            for fname in filenames:
                if not fname.lower().endswith('.txt'):
                    continue
                fpath = os.path.join(dirpath, fname)
                is_root_zero = os.path.abspath(fpath) == os.path.abspath(root_zero)

                if fname.lower() == '0.txt' and not is_root_zero:
                    # Absorb stray 0.txt into root scratch
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                            lines = [l.rstrip('\n') for l in f if l.strip()]
                    except Exception as e:
                        print(f"⚠️ Cannot read {fpath}: {e}")
                        continue
                    try:
                        with open(root_zero, 'a', encoding='utf-8') as f:
                            f.write('\n.\n')
                            if lines:
                                f.write('\n'.join(lines) + '\n')
                        os.remove(fpath)
                        absorbed.append(fpath)
                    except Exception as e:
                        print(f"⚠️ Cannot merge {fpath}: {e}")
                        continue

                # NOTE: the previous "delete any .txt with no real content" branch was
                # removed — a dots-only or momentarily-empty file is no longer deleted.
                # Only genuine subfolder 0.txt files are absorbed (above).

                # Remove now-empty parent directories
                parent = os.path.dirname(fpath)
                if os.path.abspath(parent) != os.path.abspath(i_dir):
                    try:
                        if not os.listdir(parent):
                            os.rmdir(parent)
                    except Exception:
                        pass

        changed = absorbed or deleted_empty
        if absorbed:
            print(f"🌀 {'Merged' if not silent else 'Startup merged'} {len(absorbed)} 0.txt file(s) into root")
        if deleted_empty:
            print(f"🗑️ Deleted {len(deleted_empty)} empty document(s)")
        if not silent and not changed:
            print("✓ Nothing to clean up")

        if changed:
            self._append_new_files_to_library()

        if not silent and changed:
            # Remember which title was selected so we can restore after reload
            _saved_title = None
            if self.book_ring.lines and self.book_ring.current() != '.':
                _saved_title = self.book_ring.current()
            if self.current_file_path == self.f1_file:
                self.load_doc_lines()
            self.switch_to_view(2)
            # Restore cursor to the same book title if it still exists
            if _saved_title:
                try:
                    idx = self.book_ring.lines.index(_saved_title)
                    self.book_ring.index = idx
                    if self.book_view:
                        self.book_view._offset = 0.0
                        self.book_view.editor.setText(_saved_title)
                        self.book_view.editor.setReadOnly(False)
                        self.book_view.editor.setCursorPosition(0)
                        self.book_view.update()
                except ValueError:
                    pass

    def reformat_active_file(self):
        """Ctrl+Shift+F: split raw pasted text into one sentence per line.

        Rules:
        - Blank lines (paragraph breaks) → '.' separator line
        - Within a paragraph, split at sentence boundaries:
          period (or ! or ?) followed by a space and an uppercase letter
        - Exceptions (no split):
          * Ellipsis: ...
          * Abbreviations: Mr. Dr. Mrs. Ms. St. Prof. Jr. Sr.
          * Spanish abbrevs: Ud. Vd. pág. núm. art. ed. vol. fig. cap.
          * Latin: e.g. i.e. etc. vs. cf.
          * Initials: single letter followed by dot (e.g. J. K.)
          * Decimal numbers: digit.digit
        """
        import re

        # Abbreviations that should NOT trigger a split
        ABBREVS = {
            'mr', 'dr', 'mrs', 'ms', 'st', 'prof', 'jr', 'sr',
            'ud', 'vd', 'pág', 'núm', 'art', 'ed', 'vol', 'fig', 'cap',
            'e.g', 'i.e', 'etc', 'vs', 'cf', 'no',
        }

        def is_exception(text, dot_pos):
            """Return True if the dot at dot_pos should NOT be a sentence boundary."""
            # Ellipsis
            if text[dot_pos:dot_pos+3] == '...':
                return True
            if dot_pos >= 2 and text[dot_pos-2:dot_pos] == '..':
                return True
            # Decimal number: digit.digit
            if (dot_pos > 0 and text[dot_pos-1].isdigit() and
                    dot_pos+1 < len(text) and text[dot_pos+1].isdigit()):
                return True
            # Single initial: one uppercase letter before dot
            if dot_pos > 0 and text[dot_pos-1].isupper():
                # Check it's a standalone letter (preceded by space or start)
                if dot_pos == 1 or text[dot_pos-2] in (' ', '\t'):
                    return True
            # Known abbreviation: word before dot matches list
            word_start = dot_pos - 1
            while word_start > 0 and text[word_start-1].isalpha():
                word_start -= 1
            word = text[word_start:dot_pos].lower()
            if word in ABBREVS:
                return True
            return False

        def split_sentences(text):
            """Split a single-paragraph text string into a list of sentences."""
            sentences = []
            current_start = 0
            i = 0
            while i < len(text):
                ch = text[i]
                if ch in '.!?':
                    if ch == '.' and is_exception(text, i):
                        i += 1
                        continue
                    # Consume consecutive punctuation (e.g. ?" or .")
                    end = i + 1
                    while end < len(text) and text[end] in '.!?\'"»)':
                        end += 1
                    rest = text[end:]
                    if not rest.strip():
                        sentences.append(text[current_start:end].strip())
                        current_start = end
                        i = end
                        continue
                    m = re.match(r'\s+([A-ZÁÉÍÓÚÜÑ"«¿¡(])', rest)
                    if m:
                        sentences.append(text[current_start:end].strip())
                        current_start = end + m.end() - 1
                        i = current_start
                        continue
                i += 1
            tail = text[current_start:].strip()
            if tail:
                sentences.append(tail)
            return [s for s in sentences if s]

        doc_path = self.current_file_path
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            print(f"❌ Reformat read error: {e}")
            return

        # If already in Voider format (starts with '.'), split sentences + collapse dots
        if raw.strip().startswith('.'):
            lines = [l.rstrip() for l in raw.strip().splitlines()]
            result = []
            prev_dot = False
            for line in lines:
                is_dot = line == '.' or (line and all(c == '.' for c in line))
                if is_dot:
                    if not prev_dot:
                        result.append('.')
                    prev_dot = True
                else:
                    text = re.sub(r'\s+', ' ', line.strip())
                    split = split_sentences(text)
                    if split:
                        result.extend(split)
                    elif text:
                        result.append(text)
                    prev_dot = False
            if not self._atomic_write_lines(doc_path, result, backup=True):
                return
            self.load_doc_lines()
            self._doc_show_editor()
            return

        # Split into paragraphs (one or more blank lines)
        paragraphs = re.split(r'\n\s*\n+', raw.strip())

        result_lines = []
        for para_idx, para in enumerate(paragraphs):
            # Collapse internal newlines/whitespace into single spaces
            text = re.sub(r'\s+', ' ', para.strip())

            if not text:
                continue

            # If paragraph is just a dot separator, keep it
            if text == '.':
                result_lines.append('.')
                continue

            # Add dot separator between paragraphs (not before the first)
            if para_idx > 0:
                result_lines.append('.')

            result_lines.extend(split_sentences(text))

        # Ensure leading dot
        if result_lines and result_lines[0] != '.':
            result_lines.insert(0, '.')

        if not self._atomic_write_lines(doc_path, result_lines, backup=True):
            return
        print(f"✅ Reformatted: {len(result_lines)} lines → {doc_path} (backup: {os.path.basename(doc_path)}.bak)")

        # Reload into ring
        self.load_doc_lines()
        self._doc_show_editor()

    def _shuffle_zero(self):
        """Ctrl+Shift+R in F2: randomise all lines of the scratch 0.txt.

        Only acts on 0.txt — the formless chaos that documents are formed from.
        Collects every content line (drops '.' separators), shuffles them, and
        rewrites the file as a single leading dot + the shuffled lines. Writes a
        0.txt.bak first so the shuffle can be undone.
        """
        if os.path.abspath(self.current_file_path) != os.path.abspath(self.f1_file):
            print("⛔ Shuffle only applies to 0.txt (the scratch).")
            return
        content = [l for l in self.line_ring.lines if l.strip() and l.strip() != '.']
        if len(content) < 2:
            print("↩ Nothing to shuffle (need at least 2 lines).")
            return
        random.shuffle(content)
        new_lines = ['.'] + content
        if not self._atomic_write_lines(self.current_file_path, new_lines, backup=True):
            return
        print(f"🎲 Shuffled 0.txt: {len(content)} lines "
              f"(backup: {os.path.basename(self.current_file_path)}.bak)")
        self.load_doc_lines()
        self._doc_show_editor()

    def _zero_blocks(self):
        """Parse the current ring (0.txt) into paragraph blocks.

        Returns a list of blocks; each block is the list of consecutive non-dot
        lines between '.' separators (order preserved)."""
        blocks = []
        cur = []
        for line in self.line_ring.lines:
            if line.strip() == '.':
                if cur:
                    blocks.append(cur)
                    cur = []
            elif line.strip():
                cur.append(line)
        if cur:
            blocks.append(cur)
        return blocks

    def _split_zero_to_docs(self):
        """Ctrl+Shift+F in 0.txt: FORMAT, then SPLIT.

        Formatting is the base operation, splitting is a layer on top:
        1. Reformat the whole scratch into single sentence-lines (also writes the
           0.txt.bak of the original).
        2. Send every block whose LAST line is a '/name' marker to void/I/name.txt
           and remove it from 0.txt (chaos → documents). Because we reformatted
           first, moved blocks arrive already formatted.

        - '/name'  → target name.txt (append if it exists, else create).
        - '/'      → auto name 'YY-M-D_N' (sequential within this run).
        - A newly created doc is inserted in the library right below the '0'
          portal you came from, so it shows up there in F3.
        - Blocks without a trailing '/' marker stay in 0.txt.
        Only acts on 0.txt.
        """
        if os.path.abspath(self.current_file_path) != os.path.abspath(self.f1_file):
            print("⛔ Format/split only applies to 0.txt (the scratch).")
            return

        # 1. Format first (reformat_active_file backs up to 0.txt.bak and reloads).
        self.reformat_active_file()

        # 2. Split the now-formatted scratch by '/name' markers.
        blocks = self._zero_blocks()
        i_dir = os.path.join(self.void_dir, 'I')

        # Auto-name generator: YY-M-D_N, skipping names already taken on disk/this run
        now = datetime.datetime.now()
        date_base = f"{now.year % 100}-{now.month}-{now.day}"
        used = set()
        def _auto_name():
            n = 1
            while True:
                cand = f"{date_base}_{n}"
                if cand not in used and not os.path.exists(os.path.join(i_dir, cand + '.txt')):
                    used.add(cand)
                    return cand
                n += 1

        kept = []          # blocks that stay in 0.txt
        moves = []         # (target_name, content_lines)
        for blk in blocks:
            last = blk[-1].strip()
            if last.startswith('/'):
                content = blk[:-1]
                if not content:
                    kept.append(blk)        # only a marker, nothing to move
                    continue
                name = last[1:].strip()
                if not name:
                    name = _auto_name()
                moves.append((name, content))
            else:
                kept.append(blk)

        if not moves:
            # Formatting already happened above; there's just nothing to split out.
            print("✓ Formatted 0.txt — no '/name' blocks to split.")
            return

        created = []       # (fname, fpath) for new docs to insert in the library
        for name, content in moves:
            fname = name if name.lower().endswith('.txt') else name + '.txt'
            fpath = os.path.join(i_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        existing = [l.rstrip('\n') for l in f]
                except Exception as e:
                    print(f"⚠️ Cannot read {fname}, skipping that block: {e}")
                    kept.append(content)   # keep it in 0.txt so it isn't lost
                    continue
                combined = existing + ['.'] + content
            else:
                combined = ['.'] + content
                created.append((fname, fpath))
            if not self._atomic_write_lines(fpath, combined):
                kept.append(content)       # write failed → keep in 0.txt
                if (fname, fpath) in created:
                    created.remove((fname, fpath))
                continue
            print(f"📤 {len(content)} line(s) → {fname}")

        # Rewrite 0.txt from the kept blocks. backup=False: reformat_active_file
        # above already wrote 0.txt.bak holding the original (pre-format) text.
        new_zero = []
        for blk in kept:
            new_zero.append('.')
            new_zero.extend(blk)
        if not new_zero:
            new_zero = ['.']
        if not self._atomic_write_lines(self.current_file_path, new_zero, backup=False):
            return

        # Insert newly created docs into the library, just below the '0' portal
        if created:
            if self._book_is_portal(self.book_ring.index):
                ins = self.book_ring.index + 1
            else:
                ins = next((k + 1 for k, raw in enumerate(self._library_lines)
                            if raw.lower() == '0.txt'), len(self._library_lines))
            for fname, fpath in created:
                display = os.path.splitext(fname)[0]
                self._library_lines.insert(ins, fname)
                self.book_ring.lines.insert(ins, display)
                self._library_path_cache[fname] = fpath
                ins += 1
            self._save_library()

        print(f"✂️ Split 0.txt: {len(moves)} block(s) moved, "
              f"{len(created)} new doc(s) (backup: {os.path.basename(self.current_file_path)}.bak)")
        self.load_doc_lines()
        self._doc_show_editor()

    # ── Book order ────────────────────────────────────────────────────────────

    def _library_path(self):
        return os.path.join(self.void_dir, 'I.txt')

    def _load_library(self):
        """Load ~/void/library.txt into book_ring. Auto-generates on first use."""
        lib_path = self._library_path()
        if not os.path.exists(lib_path):
            self._generate_library(lib_path)
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                raw_lines = [l.rstrip('\n') for l in f]
        except Exception:
            raw_lines = []
        # Build parallel structures
        self._library_lines = []
        ring_lines = []
        for raw in raw_lines:
            s = raw.strip()
            if s == '.':
                self._library_lines.append('.')
                ring_lines.append('.')
            elif s:
                self._library_lines.append(s)
                ring_lines.append(os.path.splitext(s)[0])
        if not ring_lines:
            self._library_lines = ['.']
            ring_lines = ['.']
        self.book_ring = LineRing(ring_lines)
        for i, l in enumerate(ring_lines):
            if l != '.':
                self.book_ring.index = i
                break
        if self.book_view:
            self.book_view.ring = self.book_ring
            self.book_view._offset = 0.0
            # Immediately sync editor text to prevent stale text from causing wrong renames
            cur = self.book_ring.current()
            if cur == '.':
                self.book_view.editor.setText('· · ·')
                self.book_view.editor.setReadOnly(True)
            elif self._book_is_portal():
                self.book_view.editor.setText('0')
                self.book_view.editor.setReadOnly(True)
            else:
                self.book_view.editor.setText(cur)
                self.book_view.editor.setReadOnly(False)
            self.book_view.editor.setCursorPosition(0)
        self._build_library_path_cache()
        n_books = sum(1 for l in self._library_lines if l != '.')
        print(f"📚 Library: {n_books} books")

    def _generate_library(self, lib_path):
        """Scan I/ and write all .txt filenames to library.txt."""
        i_dir = os.path.join(self.void_dir, 'I')
        files = []
        try:
            for root, _, fnames in os.walk(i_dir):
                for f in sorted(fnames):
                    if f.lower().endswith('.txt'):
                        files.append(f)
        except Exception:
            pass
        files.sort()
        try:
            with open(lib_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(files))
        except Exception as e:
            print(f"⚠️ Could not generate library.txt: {e}")

    def _append_new_files_to_library(self):
        """Add any I/ files not yet in I.txt to the end, preserving existing order."""
        lib_path = self._library_path()
        i_dir = os.path.join(self.void_dir, 'I')
        try:
            existing = set()
            lines = []
            if os.path.exists(lib_path):
                with open(lib_path, 'r', encoding='utf-8') as f:
                    lines = [l.rstrip('\n') for l in f]
                existing = {l.lower() for l in lines if l and l != '.'}
            new_files = []
            for root, _, fnames in os.walk(i_dir):
                for f in sorted(fnames):
                    if f.lower().endswith('.txt') and f.lower() not in existing:
                        new_files.append(f)
                        existing.add(f.lower())
            if new_files:
                lines.extend(new_files)
                with open(lib_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines) + '\n')
                print(f"📚 Added {len(new_files)} new file(s) to I.txt")
        except Exception as e:
            print(f"⚠️ Could not update I.txt: {e}")

    def _build_library_path_cache(self):
        """Map filename → absolute path by scanning I/ recursively.

        The library (I.txt / _library_lines) keys on bare filename, so two files
        with the same basename in different folders would collide. Previously the
        last one scanned silently won — opening/deleting one could hit the other.
        Now we keep the FIRST occurrence (deterministic) and warn about the rest,
        so a collision is visible instead of dangerous.
        """
        self._library_path_cache = {}
        i_dir = os.path.join(self.void_dir, 'I')
        try:
            for root, _, fnames in os.walk(i_dir):
                for f in fnames:
                    if not f.lower().endswith('.txt'):
                        continue
                    full = os.path.join(root, f)
                    if f in self._library_path_cache:
                        print(f"⚠️ Duplicate basename {f!r}: keeping "
                              f"{self._library_path_cache[f]!r}, ignoring {full!r}")
                        continue
                    self._library_path_cache[f] = full
        except Exception:
            pass

    def _save_library(self):
        try:
            with open(self._library_path(), 'w', encoding='utf-8') as f:
                f.write('\n'.join(self._library_lines))
        except Exception as e:
            print(f"⚠️ Could not save library.txt: {e}")

    def _library_current_fname(self):
        """Return the filename.txt at the current ring position, or None."""
        idx = self.book_ring.index
        if idx >= len(self._library_lines):
            return None
        raw = self._library_lines[idx]
        return None if raw == '.' else raw

    def _last_lines_path(self):
        return os.path.join(self.book_dir, '_last_lines.json')

    def _save_last_line(self):
        """Save current line index for the active file into _last_lines.json."""
        fname = os.path.basename(self.current_file_path)
        path = self._last_lines_path()
        try:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
            data[fname] = self.line_ring.index
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving last line: {e}")

    def _restore_last_line(self):
        """Restore last known line index for the active file from _last_lines.json."""
        fname = os.path.basename(self.current_file_path)
        path = self._last_lines_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            idx = data.get(fname)
            if idx is not None:
                n = len(self.line_ring.lines)
                self.line_ring.index = max(0, min(idx, n - 1))
        except Exception:
            pass  # no saved state yet, stay at 0


    def _set_active_file(self, path):
        """Change active file (and book_dir if it changed), reload doc ring."""
        self.current_file_path = path
        new_book_dir = os.path.dirname(os.path.abspath(path))
        if new_book_dir != self.book_dir:
            self.book_dir = new_book_dir
            self.config['book_dir'] = new_book_dir
        self.config['active_file'] = path
        _save_config(self.config)
        os.makedirs(self.book_dir, exist_ok=True)
        if not os.path.exists(path):
            open(path, 'w', encoding='utf-8').close()
        self.load_doc_lines()
        # Reset navigation state for new file
        self.current_active_line_index = None
        self.last_inserted_index = None
        print(f"📄 Active: {os.path.basename(path)}")

    def _set_f2_file(self, path):
        """Set which file F2 shows. switch_to_view(1) will reload if needed."""
        new_book_dir = os.path.dirname(os.path.abspath(path))
        if new_book_dir != self.book_dir:
            self.book_dir = new_book_dir
            self.config['book_dir'] = new_book_dir
        self.f2_file = path
        self.config['active_file'] = path
        _save_config(self.config)
        if not os.path.exists(path):
            open(path, 'w', encoding='utf-8').close()
        self.current_active_line_index = None
        self.last_inserted_index = None
        print(f"📄 F2 → {os.path.basename(path)}")

    # ── Book directory / file pickers ─────────────────────────────────────────

    def pick_active_file(self):
        """Ctrl+F2: pick any .txt file → sets active file + book folder."""
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Active File",
            self.book_dir,
            "Text files (*.txt)"
        )
        if not path or not os.path.isfile(path):
            return
        self._set_f2_file(path)
        self.switch_to_view(1)

    def pick_book_directory(self):
        """Ctrl+F3: pick book folder, switch active file if it's outside new folder."""
        path = QFileDialog.getExistingDirectory(
            None, "Select Book Folder",
            self.book_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not path or not os.path.isdir(path):
            return
        self.book_dir = path
        self.config['book_dir'] = path
        _save_config(self.config)
        print(f"📁 Book dir: {path}")
        self.switch_to_view(self.current_view)

    def _apply_editor_style(self, editor, red=False):
        """Apply red or white stylesheet to a circular view editor."""
        if red:
            editor.setStyleSheet("""
                QLineEdit {
                    background-color: black;
                    color: rgb(255, 40, 40);
                    border: none;
                    qproperty-alignment: AlignCenter;
                    selection-background-color: rgb(255, 40, 40);
                    selection-color: black;
                }
            """)
        else:
            editor.setStyleSheet("""
                QLineEdit {
                    background-color: black;
                    color: white;
                    border: none;
                    qproperty-alignment: AlignCenter;
                    selection-background-color: white;
                    selection-color: black;
                }
            """)

    _ZERO_GLYPH = 'ø'

    def _doc_editor_text(self):
        """Text the F2 editor should show for the current line: the ø glyph when
        parked on the index-0 marker (so it stays marked while highlighted instead
        of looking like a plain '.'), otherwise the line itself. The ring keeps
        '.' — this is display only, and the marker line is read-only."""
        cur = self.line_ring.current()
        if self.circular_view.zero_marker and self.line_ring.index == 0 and cur == '.':
            return self._ZERO_GLYPH
        return cur

    def _doc_show_editor(self):
        """Show F2 editor with current doc line, cursor at start."""
        if not self.line_ring.lines:
            return
        view = self.circular_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self._doc_editor_text())
        view.editor.setCursorPosition(0)
        view.editor.setReadOnly(self.line_ring.current() == '.')
        is_zero_dot = view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(view.editor, red=is_zero_dot)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _doc_random_line(self):
        """* in F2: jump to a random non-dot line in the current document."""
        candidates = [i for i, l in enumerate(self.line_ring.lines) if l != '.']
        if not candidates:
            return
        self.line_ring.index = random.choice(candidates)
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        self.circular_view.editor.setCursorPosition(0)
        is_zero_dot = self.circular_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(self.circular_view.editor, red=is_zero_dot)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _random_line_from_dir(self, directory, exclude_path=None):
        """Pick a random non-empty, non-dot line from a random .txt in directory
        (recursively). Returns the line or None. The source file is never
        modified — this is a copy (cut-up)."""
        try:
            txts = []
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if f.lower().endswith('.txt') and not f.startswith('.'):
                        p = os.path.join(root, f)
                        if exclude_path and os.path.abspath(p) == os.path.abspath(exclude_path):
                            continue
                        txts.append(p)
            random.shuffle(txts)
            for p in txts:
                try:
                    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
                        lines = [l.strip() for l in fh
                                 if l.strip() and l.strip() != '.']
                except OSError:
                    continue
                if lines:
                    return random.choice(lines)
        except Exception as e:
            print(f"⚠️ random line scan failed: {e}")
        return None

    def _doc_refresh_editor(self, select=False):
        """Repaint F2 and sync the editor to the current ring line."""
        cur = self.line_ring.current()
        ed = self.circular_view.editor
        self.circular_view._offset = 0.0
        ed.setText(self._doc_editor_text())
        if select:
            ed.selectAll()
        else:
            ed.setCursorPosition(0)
        ed.setReadOnly(cur == '.')
        is_zero_dot = self.circular_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(ed, red=is_zero_dot)
        self.circular_view.update()

    def _doc_tab(self):
        """Contextual Tab in F2:
          - on the ø zero-marker (index 0): shuffle the paragraph ORDER (each
            paragraph keeps its lines in their relative order).
          - on a '.' separator: shuffle the LINES within that paragraph.
          - on a content line: insert a random I/ line below the cursor,
            selected, so repeated Tab re-rolls it (source file untouched).
        """
        ring = self.line_ring
        if not ring.lines:
            return
        if self.circular_view.zero_marker and ring.index == 0:
            self._doc_shuffle_paragraphs()
        elif ring.current() == '.':
            self._doc_shuffle_para_lines()
        else:
            self._doc_insert_random_i_line()

    def _doc_shuffle_paragraphs(self):
        """Tab on ø: shuffle paragraph order; lines keep their order inside each."""
        _, paragraphs = self._paragraphs_from_ring()
        if len(paragraphs) < 2:
            return
        random.shuffle(paragraphs)
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = 0          # stay on the ø
        self.auto_save_circular()
        self._doc_tab_cand = None
        self._doc_refresh_editor()

    def _doc_shuffle_para_lines(self):
        """Tab on a '.': shuffle the lines within that paragraph (needs >=2)."""
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        if len(paragraphs[k]) < 2:
            return
        random.shuffle(paragraphs[k])
        dot_idx = self._dot_line_index(k, paragraphs)
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = dot_idx    # stay on the same separator
        self.auto_save_circular()
        self._doc_tab_cand = None
        self._doc_refresh_editor()

    def _doc_insert_random_i_line(self):
        """Tab on a content line: insert (or re-roll) a random I/ line, selected.

        First Tab inserts a candidate line below the cursor and selects it.
        Tab again — while still parked on that unchanged candidate — swaps it for
        another random line in place. Typing or navigating away commits it.
        """
        ring = self.line_ring
        cand = getattr(self, '_doc_tab_cand', None)
        rerolling = (cand is not None
                     and cand['idx'] == ring.index
                     and 0 <= ring.index < len(ring.lines)
                     and ring.lines[ring.index] == cand['text'])
        line = self._random_line_from_dir(self.book_dir,
                                          exclude_path=self.current_file_path)
        if not line:
            print("↩ No I/ lines to pull.")
            return
        if rerolling:
            ring.lines[ring.index] = line
        else:
            ring.lines.insert(ring.index + 1, line)
            ring.index += 1
        self._doc_tab_cand = {'idx': ring.index, 'text': line}
        self.auto_save_circular()
        self._doc_refresh_editor(select=True)

    def _doc_navigate(self, delta):
        """Move doc ring and update F2 editor text."""
        self._save_last_line()
        if self._para_focus and self._para_focus_content:
            content = self._para_focus_content
            cur = self.line_ring.index
            pos = content.index(cur) if cur in content else 0
            self.line_ring.index = content[(pos + delta) % len(content)]
        else:
            self.line_ring.move(delta)
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self._doc_editor_text())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(self.line_ring.current() == '.')
        is_zero_dot = self.circular_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(self.circular_view.editor, red=is_zero_dot)
        self.circular_view.update()

    def _doc_join_prev(self):
        """Backspace at line start: join current line with previous (blocked by dots)."""
        ring = self.line_ring
        cur = ring.index
        n = len(ring.lines)
        if n < 2:
            return
        prev = (cur - 1) % n
        if ring.lines[prev] == '.':
            return  # never join across a paragraph boundary
        join_pos = len(ring.lines[prev])
        ring.lines[prev] = ring.lines[prev] + ring.lines[cur]
        ring.lines.pop(cur)
        ring.index = prev
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i < cur else i - 1
                for i in self._para_focus_content
                if i != cur
            ]
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(join_pos)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_join_next(self):
        """Delete at line end: join current line with next (blocked by dots)."""
        ring = self.line_ring
        cur = ring.index
        n = len(ring.lines)
        if n < 2:
            return
        nxt = (cur + 1) % n
        if ring.lines[nxt] == '.':
            return  # never join across a paragraph boundary
        join_pos = len(ring.lines[cur])
        ring.lines[cur] = ring.lines[cur] + ring.lines[nxt]
        ring.lines.pop(nxt)
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i < nxt else i - 1
                for i in self._para_focus_content
                if i != nxt
            ]
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(join_pos)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_split_line(self, pos):
        """Split current line at cursor pos into two lines."""
        ring = self.line_ring
        cur = ring.index
        text = ring.lines[cur]
        before, after = text[:pos], text[pos:]
        ring.lines[cur] = before
        ring.lines.insert(cur + 1, after)
        ring.index = cur + 1
        # Adjust para_focus indices
        if self._para_focus:
            self._para_focus_content = [
                i if i <= cur else i + 1
                for i in self._para_focus_content
            ]
            # Insert new line right after cur in focus
            if cur in self._para_focus_content:
                ins = self._para_focus_content.index(cur) + 1
                self._para_focus_content.insert(ins, cur + 1)
            if self.circular_view:
                dot_idx = self._get_focus_dot_idx()
                self.circular_view.focus_indices = set(self._para_focus_content) | {dot_idx}
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _doc_live_save(self, text):
        """Save on every keystroke in F2 editor."""
        if text.strip():
            self.line_ring.lines[self.line_ring.index] = text
            self.auto_save_circular()
            self.circular_view.update()

    def _doc_confirm_edit(self):
        """Enter in F2: focus mode on dot; on text line fork to F1 pre-filled."""
        if self.line_ring.current() == '.' and not self._para_focus:
            self._enter_para_focus()
        else:
            fork_line = self.line_ring.current()
            idx = self.line_ring.index
            self._exit_para_focus() if self._para_focus else None
            self.current_active_line_index = None
            self.last_inserted_index = idx
            self.switch_to_view(0)
            if fork_line and fork_line != '.':
                self.entry.setText(fork_line)
                self.entry.setCursorPosition(0)

    def _enter_para_focus(self):
        ring = self.line_ring
        n = len(ring.lines)
        dot_idx = ring.index
        content = []
        i = (dot_idx + 1) % n
        for _ in range(n - 1):
            if ring.lines[i] == '.':
                break
            content.append(i)
            i = (i + 1) % n
        if not content:
            return
        self._para_focus = True
        self._para_focus_content = content
        self.circular_view.focus_indices = set(content) | {dot_idx}
        ring.index = content[0]
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.editor.setReadOnly(False)
        self.circular_view.update()

    def _exit_para_focus(self):
        self._para_focus = False
        self._para_focus_content = []
        self.circular_view.focus_indices = None
        # Return to the dot that precedes this paragraph
        ring = self.line_ring
        n = len(ring.lines)
        idx = (ring.index - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                break
            idx = (idx - 1) % n
        self._doc_show_editor()

    def _get_focus_dot_idx(self):
        """Return the ring index of the dot preceding the focused paragraph."""
        ring = self.line_ring
        n = len(ring.lines)
        if not self._para_focus_content:
            return 0
        idx = (self._para_focus_content[0] - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                return idx
            idx = (idx - 1) % n
        return 0

    def _vault_show_editor(self):
        """Show the vault inline editor with the current vault line, cursor at start."""
        if not self.vault_ring.lines:
            return
        view = self.vault_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.vault_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    # ── F1 scratch mode (Tab toggle) ──────────────────────────────────────────

    def _f1_tab_toggle(self):
        """Tab in F1: toggle between write entry and 0.txt scratch circular view."""
        if self.current_view != 0:
            return
        if not self._f1_scratch_mode:
            self._enter_f1_scratch()
        else:
            self._exit_f1_scratch()

    def _enter_f1_scratch(self):
        self._f1_scratch_mode = True
        if not self.scratch_view:
            self.scratch_view = CircularView(self.line_ring, self)
            self.scratch_view.zero_marker = True
            self.scratch_view.setFont(self._app_font)
            self.scratch_view.editor.returnPressed.disconnect()
            self.scratch_view.editor.returnPressed.connect(self._scratch_enter)
            self.scratch_view.editor.textEdited.connect(self._scratch_live_save)
            self.scratch_view.editor.upPressed.connect(lambda: self._scratch_navigate(-1))
            self.scratch_view.editor.downPressed.connect(lambda: self._scratch_navigate(1))
            self.scratch_view.editor.deleteLineToZero.connect(self._scratch_delete_line)
            self.scratch_view.editor.tabPressed.connect(self._f1_tab_toggle)
            self.stack.addWidget(self.scratch_view)
        else:
            self.scratch_view.ring = self.line_ring
            self.scratch_view._offset = 0.0
        self.stack.setCurrentWidget(self.scratch_view)
        self.entry.hide()
        self.scratch_view.update()
        self._scratch_show_editor()

    def _exit_f1_scratch(self, fork_line=None):
        self._f1_scratch_mode = False
        if self.scratch_view:
            self.scratch_view.edit_mode = False
            self.scratch_view.editor.hide()
        self.stack.setCurrentWidget(self.normal_view)
        self.entry.show()
        self.entry.raise_()
        if fork_line:
            self.entry.setText(fork_line)
            self.entry.selectAll()
        else:
            self.entry.clear()
        self.entry.setFocus()

    def _scratch_show_editor(self):
        view = self.scratch_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.line_ring.current())
        view.editor.setCursorPosition(0)
        is_zero_dot = view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(view.editor, red=is_zero_dot)
        view.editor.setReadOnly(self.line_ring.current() == '.')
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _scratch_navigate(self, delta):
        self._save_last_line()
        self.line_ring.move(delta)
        self.scratch_view._offset = 0.0
        self.scratch_view.editor.setText(self.line_ring.current())
        self.scratch_view.editor.setCursorPosition(0)
        is_zero_dot = self.scratch_view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(self.scratch_view.editor, red=is_zero_dot)
        self.scratch_view.editor.setReadOnly(self.line_ring.current() == '.')
        self.scratch_view.update()

    def _scratch_live_save(self, text):
        if text.strip():
            self.line_ring.lines[self.line_ring.index] = text
            self.auto_save_circular()
            self.scratch_view.update()

    def _scratch_enter(self):
        """Enter in F1 scratch: fork current line to entry and return to write mode."""
        cur = self.line_ring.current()
        fork_line = cur if cur and cur != '.' else None
        self._exit_f1_scratch(fork_line=fork_line)

    def _scratch_delete_line(self):
        """Ctrl+Delete in F1 scratch: permanently delete (already in 0.txt)."""
        lines = self.line_ring.lines
        n = len(lines)
        cur = self.line_ring.index
        if n <= 1:
            return
        line = lines[cur]
        new_lines = [l for i, l in enumerate(lines) if i != cur]
        new_index = min(cur, len(new_lines) - 1)
        self.line_ring.lines = new_lines
        self.line_ring.index = new_index
        self.auto_save_circular()
        self.scratch_view._offset = 0.0
        self.scratch_view.editor.setText(self.line_ring.current())
        self.scratch_view.editor.setCursorPosition(0)
        self.scratch_view.update()
        print(f"🗑️ Scratch deleted: {line[:60]}")

    # ── Book browser (F3) ─────────────────────────────────────────────────────

    def _book_is_portal(self, idx=None):
        """True if the F3 entry at idx (default current) is the read-only '0'
        scratch portal. A portal is any library entry named '0' / '0.txt'; it is
        not renamable and Enter on it jumps to the scratch 0.txt."""
        if idx is None:
            idx = self.book_ring.index
        if idx < 0 or idx >= len(self.book_ring.lines):
            return False
        if self.book_ring.lines[idx] == '0':
            return True
        return (idx < len(self._library_lines)
                and self._library_lines[idx].lower() == '0.txt')

    def _book_show_editor(self):
        """Show F3 editor; dots and the '0' portal show read-only."""
        if not self.book_ring.lines:
            return
        view = self.book_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        if self.book_ring.current() == '.':
            view.editor.setText('· · ·')
            view.editor.setReadOnly(True)
        elif self._book_is_portal():
            view.editor.setText('0')
            view.editor.setReadOnly(True)
        else:
            view.editor.setText(self.book_ring.current())
            view.editor.setReadOnly(False)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _book_random(self):
        """Tab in F3: jump to a random real book title (skip '.' separators and
        the read-only '0' portals)."""
        if self._book_pending_new:
            return
        self._book_try_rename()
        candidates = [i for i, l in enumerate(self.book_ring.lines)
                      if l != '.' and not self._book_is_portal(i)]
        if not candidates:
            return
        self.book_ring.index = random.choice(candidates)
        self.book_view._offset = 0.0
        self._book_show_editor()

    def _book_navigate(self, delta):
        if self._book_pending_new:
            # Cancel the pending new entry
            idx = self.book_ring.index
            self.book_ring.lines.pop(idx)
            self._library_lines.pop(idx)
            if not self.book_ring.lines:
                self.book_ring.lines = ['.']
                self._library_lines = ['.']
            self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
            self._book_pending_new = False
        self._book_try_rename()
        if len(self.book_ring.lines) < 2:
            return
        self.book_ring.move(delta)
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('· · ·')
            self.book_view.editor.setReadOnly(True)
        elif self._book_is_portal():
            self.book_view.editor.setText('0')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_try_rename(self):
        if self._book_pending_new:
            return True
        # The '0' portal is read-only — never rename it.
        if self._book_is_portal():
            return True
        fname = self._library_current_fname()
        if not fname:
            return True
        new_display = self.book_view.editor.text().strip()
        if not new_display or new_display.startswith('.'):
            self.book_view.editor.setText(self.book_ring.current())
            return True
        # '0' is reserved for the scratch portal. Refuse to rename any real file
        # to '0'/'0.txt' — os.rename overwrites the destination, which would erase
        # the scratch 0.txt. (Use Shift+Enter + '0' to add a portal instead.)
        if new_display == '0' or new_display.lower() == '0.txt':
            print("⛔ '0' is reserved for the scratch portal — rename refused.")
            self.book_view.editor.setText(self.book_ring.current())
            return True
        new_fname = new_display + '.txt'
        if new_fname == fname:
            return True
        old_path = self._library_path_cache.get(fname)
        if not old_path or not os.path.exists(old_path):
            return True
        new_path = os.path.join(os.path.dirname(old_path), new_fname)
        if os.path.exists(new_path):
            print(f"⛔ {new_fname} already exists — rename refused (would overwrite it).")
            self.book_view.editor.setText(self.book_ring.current())
            return True
        try:
            os.rename(old_path, new_path)
            if self.current_file_path == old_path:
                self.current_file_path = new_path
                self.config['active_file'] = new_path
                _save_config(self.config)
            idx = self.book_ring.index
            self._library_lines[idx] = new_fname
            self.book_ring.lines[idx] = new_display
            del self._library_path_cache[fname]
            self._library_path_cache[new_fname] = new_path
            self._save_library()
            print(f"📝 Renamed: {fname} → {new_fname}")
        except Exception as e:
            print(f"⚠️ Rename failed: {e}")
            return False
        return True

    def _book_confirm_edit(self):
        """Enter in F3: handle new-entry mode, dot → concat view, title → F2."""
        if self._book_pending_new:
            text = self.book_view.editor.text().strip()
            idx = self.book_ring.index
            if not text:
                # Empty → cancel, remove placeholder
                self.book_ring.lines.pop(idx)
                self._library_lines.pop(idx)
                if not self.book_ring.lines:
                    self.book_ring.lines = ['.']
                    self._library_lines = ['.']
                self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
            elif text == '.':
                # Convert placeholder to separator
                self.book_ring.lines[idx] = '.'
                self._library_lines[idx] = '.'
                self._save_library()
            elif text == '0':
                # Convert placeholder to a '0' scratch portal — no file is
                # created, no collision with the real 0.txt. Read-only marker.
                self.book_ring.lines[idx] = '0'
                self._library_lines[idx] = '0.txt'
                self._save_library()
            else:
                # Create new file and open in F2
                fname = text + '.txt'
                fpath = os.path.join(self.void_dir, 'I', fname)
                if not os.path.exists(fpath):
                    open(fpath, 'w', encoding='utf-8').close()
                self.book_ring.lines[idx] = text
                self._library_lines[idx] = fname
                self._library_path_cache[fname] = fpath
                self._save_library()
                self._book_pending_new = False
                self._set_f2_file(fpath)
                self.switch_to_view(1)
                return
            self._book_pending_new = False
            self._book_show_editor()
            return

        if self.book_ring.current() == '.':
            self._book_open_concat()
            return
        if self._book_is_portal():
            # Portal → jump to the scratch 0.txt in F2 (no rename, no file ops).
            self._set_f2_file(self.f1_file)
            self.switch_to_view(1)
            return
        if not self._book_try_rename():
            return
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not fpath:
            fpath = os.path.join(self.void_dir, 'I', fname)
        self._set_f2_file(fpath)
        self.switch_to_view(1)

    def _book_new_entry(self):
        """Shift+Enter in F3: insert a blank entry below current for the user to name."""
        if self._book_pending_new:
            return
        self._book_try_rename()
        idx = self.book_ring.index
        self.book_ring.lines.insert(idx + 1, '')
        self._library_lines.insert(idx + 1, '')
        self.book_ring.index = idx + 1
        self._book_pending_new = True
        self.book_view._offset = 0.0
        self.book_view.editor.setText('')
        self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_send_to_zero(self):
        """Ctrl+Delete in F3: on dot → delete separator; on title → send lines to 0.txt and delete file."""
        if self._book_pending_new:
            return
        if self.book_ring.current() == '.':
            self._book_backspace_on_dot()
            return
        if self._book_is_portal():
            # Remove only the portal marker from the library — never touch 0.txt.
            idx = self.book_ring.index
            self.book_ring.lines.pop(idx)
            self._library_lines.pop(idx)
            if not self.book_ring.lines:
                self.book_ring.lines = ['.']
                self._library_lines = ['.']
            n = len(self.book_ring.lines)
            self.book_ring.index = idx % n
            self._save_library()
            self.book_view._offset = 0.0
            self._book_show_editor()
            print("🗑️ Portal '0' removed (0.txt untouched)")
            return
        fname = self._library_current_fname()
        if not fname:
            return
        fpath = self._library_path_cache.get(fname)
        if not fpath or not os.path.exists(fpath):
            return
        if os.path.abspath(fpath) == os.path.abspath(self.f1_file):
            return
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.strip() for l in f if l.strip() and l.strip() != '.']
        except Exception as e:
            print(f"⚠️ Cannot read {fpath}: {e}")
            return
        if lines:
            try:
                with open(self.f1_file, 'a', encoding='utf-8') as f:
                    f.write('\n.\n')
                    f.write('\n'.join(lines) + '\n')
            except Exception as e:
                print(f"⚠️ Cannot append to 0.txt: {e}")
                return
        try:
            os.remove(fpath)
        except Exception as e:
            print(f"⚠️ Cannot delete {fpath}: {e}")
            return
        idx = self.book_ring.index
        self.book_ring.lines.pop(idx)
        self._library_lines.pop(idx)
        if fname in self._library_path_cache:
            del self._library_path_cache[fname]
        if not self.book_ring.lines:
            self.book_ring.lines = ['.']
            self._library_lines = ['.']
        n = len(self.book_ring.lines)
        self.book_ring.index = idx % n
        while self.book_ring.current() == '.' and n > 1:
            self.book_ring.index = (self.book_ring.index + 1) % n
        self._save_library()
        if self.current_file_path == self.f1_file:
            self.load_doc_lines()
        self.book_view._offset = 0.0
        self._book_show_editor()
        print(f"🗑️ {len(lines)} lines from {fname} → 0.txt, file deleted")

    def _book_insert_separator(self):
        """Tab in F3: insert a group separator dot above the current position."""
        if self.book_ring.current() == '.':
            return
        self._book_try_rename()
        idx = self.book_ring.index
        self.book_ring.lines.insert(idx, '.')
        self._library_lines.insert(idx, '.')
        self.book_ring.index = idx
        self._save_library()
        self.book_view._offset = 0.0
        self.book_view.editor.setText('· · ·')
        self.book_view.editor.setReadOnly(True)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_backspace_on_dot(self):
        """Backspace in F3 when on a dot: delete the group separator."""
        if self.book_ring.current() != '.':
            return
        idx = self.book_ring.index
        self.book_ring.lines.pop(idx)
        self._library_lines.pop(idx)
        if not self.book_ring.lines:
            self.book_ring.lines = ['.']
            self._library_lines = ['.']
            self.book_ring.index = 0
        else:
            self.book_ring.index = idx % len(self.book_ring.lines)
            while self.book_ring.current() == '.' and len(self.book_ring.lines) > 1:
                self.book_ring.index = (self.book_ring.index + 1) % len(self.book_ring.lines)
        self._save_library()
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('· · ·')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_open_concat(self):
        """Build a read-only concatenated ring from all files in the current dot group."""
        dot_idx = self.book_ring.index
        n = len(self._library_lines)
        group_fnames = []
        i = (dot_idx + 1) % n
        for _ in range(n - 1):
            if self._library_lines[i] == '.':
                break
            group_fnames.append(self._library_lines[i])
            i = (i + 1) % n
        if not group_fnames:
            return

        lines = ['.']
        header_indices = set()
        for fname in group_fnames:
            fpath = self._library_path_cache.get(fname)
            if not fpath or not os.path.exists(fpath):
                continue
            stem = os.path.splitext(fname)[0].upper()
            header_indices.add(len(lines))
            lines.append(f'── {stem} ──')
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    for raw in f:
                        s = raw.strip()
                        if s and s != '.':
                            lines.append(s)
            except Exception:
                pass
            lines.append('.')

        if len(lines) <= 1:
            return

        self.book_concat_ring = LineRing(lines)
        self._book_concat_header_indices = header_indices
        for start_i in range(len(lines)):
            if lines[start_i] not in ('.', '') and start_i not in header_indices:
                self.book_concat_ring.index = start_i
                break

        self.switch_to_view(9)

    def _book_concat_show_editor(self):
        view = self.book_concat_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move(
            (view.width() - editor_width) // 2,
            center_y - view.editor.sizeHint().height() // 2
        )
        view.editor.setText(self.book_concat_ring.current())
        view.editor.setReadOnly(True)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _book_concat_navigate(self, delta):
        ring = self.book_concat_ring
        n = len(ring.lines)
        for _ in range(n):
            ring.move(delta)
            cur = ring.current()
            if cur not in ('.', '') and ring.index not in self._book_concat_header_indices:
                break
        self.book_concat_view._offset = 0.0
        self.book_concat_view.editor.setText(ring.current())
        self.book_concat_view.editor.setCursorPosition(0)
        self.book_concat_view.update()

    def _book_swap_up(self):
        """Alt+Up in F3: swap current title with nearest non-dot above."""
        idx = self.book_ring.index
        prev = idx - 1
        while prev >= 0 and self.book_ring.lines[prev] == '.':
            prev -= 1
        if prev < 0 or self.book_ring.lines[prev] == '.':
            return
        self.book_ring.lines[idx], self.book_ring.lines[prev] = \
            self.book_ring.lines[prev], self.book_ring.lines[idx]
        self._library_lines[idx], self._library_lines[prev] = \
            self._library_lines[prev], self._library_lines[idx]
        self.book_ring.index = prev
        self._save_library()
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('· · ·')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_swap_down(self):
        """Alt+Down in F3: swap current title with nearest non-dot below."""
        idx = self.book_ring.index
        n = len(self.book_ring.lines)
        nxt = idx + 1
        while nxt < n and self.book_ring.lines[nxt] == '.':
            nxt += 1
        if nxt >= n or self.book_ring.lines[nxt] == '.':
            return
        self.book_ring.lines[idx], self.book_ring.lines[nxt] = \
            self.book_ring.lines[nxt], self.book_ring.lines[idx]
        self._library_lines[idx], self._library_lines[nxt] = \
            self._library_lines[nxt], self._library_lines[idx]
        self.book_ring.index = nxt
        self._save_library()
        self.book_view._offset = 0.0
        if self.book_ring.current() == '.':
            self.book_view.editor.setText('· · ·')
            self.book_view.editor.setReadOnly(True)
        else:
            self.book_view.editor.setText(self.book_ring.current())
            self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_rebase(self):
        """Ctrl+0 in F3: rotate ring so current title becomes first."""
        idx = self.book_ring.index
        if idx == 0:
            return
        self.book_ring.lines = self.book_ring.lines[idx:] + self.book_ring.lines[:idx]
        self._library_lines = self._library_lines[idx:] + self._library_lines[:idx]
        self.book_ring.index = 0
        while self.book_ring.current() == '.' and len(self.book_ring.lines) > 1:
            self.book_ring.move(1)
        self._save_library()
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setReadOnly(False)
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _build_doc_html(self, lines, title):
        """Build centered HTML from a list of lines (dots become spacers)."""
        parts = ['<html><body style="color:black;background:white;'
                 'font-family:Consolas,monospace;">']
        parts.append(f'<h2 style="text-align:center;margin:3em 0 2em;">{title}</h2>')
        for line in lines:
            if line == '.':
                parts.append('<p style="margin:0.8em 0;">&nbsp;</p>')
            else:
                parts.append(f'<p style="text-align:center;margin:0.4em 0;">{line}</p>')
        parts.append('</body></html>')
        return ''.join(parts)

    def _printer_from_dialog(self):
        """Show QPrintDialog and return ready printer, or None if cancelled."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return None
        return printer

    def _printer_from_save_dialog(self, default_path):
        """Show save-as dialog and return a PDF printer, or None if cancelled."""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save as', default_path, 'PDF (*.pdf)')
        if not path:
            return None
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        return printer

    def _send_to_printer(self, printer, html):
        from PyQt6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print(printer)

    def print_book(self):
        """Ctrl+P in F3: send all chapters to physical printer."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        printable = [l for l in self._library_lines if l and l != '.']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = self._library_path_cache.get(fname, '')
            title = os.path.splitext(fname)[0]
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []
            if i > 0:
                html_parts.append('<div style="page-break-before:always;"></div>')
            html_parts.append(self._build_doc_html(lines, title))
        full_html = ('<html><body style="color:black;background:white;'
                     'font-family:Consolas,monospace;">'
                     + ''.join(html_parts) + '</body></html>')
        self._send_to_printer(printer, full_html)

    def export_book(self):
        """Ctrl+S in F3: save all books from library as PDF."""
        book_name = os.path.basename(os.path.normpath(self.void_dir))
        default_path = os.path.join(self.void_dir, book_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        printable = [l for l in self._library_lines if l and l != '.']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = self._library_path_cache.get(fname, '')
            title = os.path.splitext(fname)[0]
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []
            if i > 0:
                html_parts.append('<div style="page-break-before:always;"></div>')
            html_parts.append(self._build_doc_html(lines, title))
        full_html = ('<html><body style="color:black;background:white;'
                     'font-family:Consolas,monospace;">'
                     + ''.join(html_parts) + '</body></html>')
        self._send_to_printer(printer, full_html)

    def _vault_navigate(self, delta):
        """Pick a fresh oracle line on each navigation."""
        self._refresh_oracle()
        self.vault_view._offset = 0.0
        self.vault_view.editor.setText(self.vault_ring.current())
        self.vault_view.editor.setCursorPosition(0)
        self.vault_view.update()

    def _vault_confirm_edit(self):
        """Append editor text to doc ring, then pick a fresh oracle line."""
        view = self.vault_view
        new_text = view.editor.text().strip()
        if not new_text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, new_text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        self._refresh_oracle()
        view._offset = 0.0
        view.update()
        view.editor.setText(self.vault_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.setFocus()
        print(f"✅ Oracle→Doc[{insert_pos}]: '{new_text}'")

    # ── F8: Oracle from O/ ────────────────────────────────────────────────────

    def _refresh_oracle_o(self):
        line = self._pick_oracle_line(self.o_dir)
        self.oracle_o_ring = LineRing(['.', line])
        self.oracle_o_ring.index = 1
        if self.oracle_o_view:
            self.oracle_o_view.ring = self.oracle_o_ring
            self.oracle_o_view._offset = 0.0
        print(f"🔮 Oracle O/: '{line[:80]}'")

    def _oracle_o_show_editor(self):
        view = self.oracle_o_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        view.editor.setText(self.oracle_o_ring.current())
        view.editor.show()
        view.editor.setFocus()
        view.editor.setCursorPosition(0)
        view.update()

    def _oracle_o_navigate(self, delta):
        self._refresh_oracle_o()
        self.oracle_o_view._offset = 0.0
        self.oracle_o_view.editor.setText(self.oracle_o_ring.current())
        self.oracle_o_view.editor.setCursorPosition(0)
        self.oracle_o_view.update()

    def _oracle_o_confirm(self):
        new_text = self.oracle_o_view.editor.text().strip()
        if not new_text:
            return
        self.o_reader_ring = LineRing(['.', new_text])
        self.o_reader_ring.index = 1
        if self.transform_view:
            self.transform_view.ring = self.o_reader_ring
        self.switch_to_view(4)

    # ── F7: O/ book browser — working set ────────────────────────────────────

    _WS_FILE = '.working_set.json'
    _WS_EMPTY = '∅'   # display marker for an empty (unfilled) slot

    def _ws_json_path(self):
        return os.path.join(self.o_dir, self._WS_FILE)

    def _ws_slot_is_empty(self, e):
        return not e.get('path')

    def _load_working_set(self):
        """Load the manual working set from JSON.

        The set is built by hand and uncapped: each entry is a slot the user
        filled by shuffling (Tab). No auto-population. An empty set means a
        single empty slot to start from.
        """
        books = []
        path = self._ws_json_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Support old locked/unlocked format for migration
                if 'books' in data:
                    books = data['books']
                else:
                    books = data.get('locked', []) + data.get('unlocked', [])
                # Keep only slots whose file still exists (empty slots aren't saved).
                books = [e for e in books
                         if e.get('path')
                         and os.path.exists(os.path.join(self.o_dir, e['path']))]
                self._ws_browser_index = data.get('browser_index', 1)
            except Exception:
                pass
        if not books:
            books = [{'path': '', 'position': 0}]   # start from one empty slot
        self._ws_books = books
        self._ws_loaded = True

    def _save_working_set(self):
        try:
            # Persist only filled slots — empty slots are transient.
            saved = [e for e in self._ws_books if not self._ws_slot_is_empty(e)]
            with open(self._ws_json_path(), 'w', encoding='utf-8') as f:
                json.dump({
                    'books': saved,
                    'browser_index': self._ws_browser_index,
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save working set: {e}")

    def _ws_save_position(self):
        if not self.o_reader_file:
            return
        fname = os.path.basename(self.o_reader_file)
        idx = self.o_reader_ring.index
        for e in self._ws_books:
            if e['path'] == fname:
                e['position'] = idx
                break
        self._save_working_set()

    def _ws_fname_from_display(self, display):
        return display.strip()

    def _ws_slot_display(self, e):
        """What a slot shows in the F7 ring: its filename, or the empty marker."""
        return e['path'] if e.get('path') else self._WS_EMPTY

    def _ws_cur_slot(self):
        """Map the current F7 ring position to a _ws_books index.

        The ring is built as ['.', slot0, '.', slot1, ...], so the book at ring
        index r is slot (r-1)//2. Returns None if the ring sits on a separator
        or there are no slots.
        """
        if not self._ws_books:
            return None
        r = self.o_browser_ring.index
        if r <= 0 or r % 2 == 0:   # 0 or even index → a '.' separator
            return None
        i = (r - 1) // 2
        return i if 0 <= i < len(self._ws_books) else None

    def _ws_build_browser_ring(self, slot=None):
        """Rebuild the F7 ring from _ws_books. If slot is given, park the cursor
        on that slot; otherwise keep index 1 (first slot)."""
        entries = []
        for e in self._ws_books:
            entries.extend(['.', self._ws_slot_display(e)])
        self.o_browser_ring = LineRing(entries or ['.'])
        if slot is not None and self._ws_books:
            slot = max(0, min(slot, len(self._ws_books) - 1))
            self.o_browser_ring.index = 2 * slot + 1
        else:
            self.o_browser_ring.index = 1 if len(self.o_browser_ring.lines) > 1 else 0
        if self.o_browser_view:
            self.o_browser_view.ring = self.o_browser_ring
            self.o_browser_view._offset = 0.0

    def _ws_refresh_browser(self, slot):
        """Rebuild + repaint the F7 ring parked on slot, syncing the editor text."""
        self._ws_build_browser_ring(slot=slot)
        if self.o_browser_view:
            self.o_browser_view.editor.setText(self.o_browser_ring.current())
            self.o_browser_view.editor.setCursorPosition(0)
            self.o_browser_view.update()

    def _ws_tab_randomize(self):
        """TAB/* in F7: (re)fill the current slot with a random O/ book, never
        repeating a book already used by another slot."""
        slot = self._ws_cur_slot()
        if slot is None:
            return
        used = {e['path'] for e in self._ws_books if e.get('path')}
        candidates = [f for f in self._ws_all_o_files if f not in used]
        if not candidates:
            print("🔀 TAB: no unused O/ books left")
            return
        prev = self._ws_books[slot].get('path') or self._WS_EMPTY
        self._ws_books[slot] = {'path': random.choice(candidates), 'position': 0}
        self._save_working_set()
        self._ws_refresh_browser(slot)
        print(f"🔀 TAB: {prev} → {self.o_browser_ring.current()}")

    def _ws_add_slot(self):
        """Shift+Enter in F7: insert a new empty slot below the current one and
        move the cursor onto it (then Tab to fill)."""
        slot = self._ws_cur_slot()
        insert_at = (slot + 1) if slot is not None else len(self._ws_books)
        self._ws_books.insert(insert_at, {'path': '', 'position': 0})
        self._save_working_set()   # empty slot itself isn't persisted, but flush index
        self._ws_refresh_browser(insert_at)
        print(f"➕ F7: new empty slot at {insert_at}")

    def _ws_remove_slot(self):
        """Ctrl+Delete in F7: remove the current slot. Never go below one slot —
        if the set empties out, leave a single empty slot to build from again.

        The book currently open in the F6 reader can't be removed (silently):
        that way deleting all the others just leaves that one book loaded, with
        no stale ghost in F6.
        """
        slot = self._ws_cur_slot()
        if slot is None:
            return
        path = self._ws_books[slot].get('path')
        if path and self.o_reader_file and \
                os.path.basename(self.o_reader_file) == path:
            return
        del self._ws_books[slot]
        if not self._ws_books:
            self._ws_books = [{'path': '', 'position': 0}]
            slot = 0
        else:
            slot = min(slot, len(self._ws_books) - 1)
        self._save_working_set()
        self._ws_refresh_browser(slot)
        print(f"🗑️ F7: slot removed → {len(self._ws_books)} slot(s)")

    def _load_o_browser(self):
        if not self._ws_loaded:
            self._load_working_set()
        self._ws_build_browser_ring()

    def _ws_cache_path(self):
        return os.path.join(self.void_dir, '.o_files_cache.txt')

    def _ws_load_o_files_cache(self):
        """Load persisted O/ file list from disk into memory (instant)."""
        path = self._ws_cache_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._ws_all_o_files = [l.rstrip('\n') for l in f if l.strip()]
            print(f"📚 O/ cache: {len(self._ws_all_o_files)} files loaded")
        except FileNotFoundError:
            pass  # first launch — rebuild will create it
        except Exception as e:
            print(f"⚠️ Could not read O/ cache: {e}")

    def _ws_rebuild_o_files_cache(self):
        """Background: re-scan O/ and overwrite the cache file. Catches new books."""
        def _scan():
            try:
                files = sorted(
                    f for f in os.listdir(self.o_dir)
                    if f.lower().endswith('.txt') and not f.startswith('.')
                )
                self._ws_all_o_files = files
                with open(self._ws_cache_path(), 'w', encoding='utf-8') as f:
                    f.write('\n'.join(files))
                print(f"📚 O/ cache rebuilt: {len(files)} files")
            except Exception as e:
                print(f"⚠️ O/ cache rebuild failed: {e}")
        threading.Thread(target=_scan, daemon=True).start()

    def _o_browser_show_editor(self):
        view = self.o_browser_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_browser_ring.current()
        while cur == '.' and len(self.o_browser_ring.lines) > 1:
            self.o_browser_ring.move(1)
            cur = self.o_browser_ring.current()
        view.editor.setText(cur)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _o_browser_navigate(self, delta):
        self.o_browser_ring.move(delta)
        while self.o_browser_ring.current() == '.':
            self.o_browser_ring.move(delta)
        self.o_browser_view._offset = 0.0
        self.o_browser_view.editor.setText(self.o_browser_ring.current())
        self.o_browser_view.editor.setCursorPosition(0)
        self.o_browser_view.update()
        # Persist the highlighted book on every move (robust to watcher hard-kills).
        self._ws_browser_index = self.o_browser_ring.index
        self._save_working_set()

    def _o_browser_open(self):
        """Enter in F7: open the current slot's book in the F6 reader. An empty
        slot does nothing — shuffle (Tab) to fill it first."""
        slot = self._ws_cur_slot()
        if slot is None:
            return
        e = self._ws_books[slot]
        if self._ws_slot_is_empty(e):
            return
        fpath = os.path.join(self.o_dir, e['path'])
        if not os.path.exists(fpath):
            return
        self._load_o_reader(fpath)
        self.switch_to_view(5)

    # ── F6: O/ reader ─────────────────────────────────────────────────────────

    def _load_o_reader(self, fpath):
        """Load an O/ book into the reader ring."""
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception as e:
            print(f"⚠️ Cannot open {fpath}: {e}")
            return
        if not lines or lines[0] != '.':
            lines.insert(0, '.')
        self.o_reader_ring = LineRing(lines)
        self.o_reader_file = fpath
        # Restore saved position, or start at 1 (skip leading dot)
        fname = os.path.basename(fpath)
        saved_pos = next(
            (e.get('position', 1) for e in self._ws_books
             if e['path'] == fname), 1
        )
        self.o_reader_ring.index = min(max(saved_pos, 1), len(lines) - 1)
        if self.o_reader_view:
            self.o_reader_view.ring = self.o_reader_ring
            self.o_reader_view._offset = 0.0
        if self.transform_view:
            self.transform_view.ring = self.o_reader_ring
            self.transform_view._offset = 0.0
        print(f"📖 Opened: {os.path.basename(fpath)} ({len(lines)} lines)")

    def _reader_show_editor(self):
        view = self.o_reader_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_reader_ring.current()
        view.editor.setText(cur if cur != '.' else '')
        view.editor.setReadOnly(True)
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _reader_random_line(self):
        """* in F6: jump to a random non-dot line in the current O/ book."""
        candidates = [i for i, l in enumerate(self.o_reader_ring.lines)
                      if l not in ('.', '')]
        if not candidates:
            return
        self.o_reader_ring.index = random.choice(candidates)
        self.o_reader_view._offset = 0.0
        self.o_reader_view.editor.setText(self.o_reader_ring.current())
        self.o_reader_view.editor.setCursorPosition(0)
        self.o_reader_view.update()

    def _reader_navigate(self, delta):
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(delta)
        self.o_reader_view._offset = 0.0
        cur = self.o_reader_ring.current()
        self.o_reader_view.editor.setText(cur)
        self.o_reader_view.editor.setCursorPosition(0)
        self.o_reader_view.update()
        # Persist on every move — proto's watcher can kill the process without a
        # clean closeEvent, so saving only on view-switch/close loses the position.
        self._ws_save_position()

    def _reader_fork_to_transform(self):
        """Fork current reader line into F5 transform view."""
        cur = self.o_reader_ring.current()
        if not cur or cur == '.':
            return
        self.o_reader_line_idx = self.o_reader_ring.index
        self.switch_to_view(4)

    # ── F5: Transform ─────────────────────────────────────────────────────────

    def _transform_show_editor(self):
        view = self.transform_view
        view.edit_mode = True
        center_y = view.height() // 2
        editor_width = min(view.width() - 100, 800)
        view.editor.setFixedWidth(editor_width)
        view.editor.move((view.width() - editor_width) // 2,
                         center_y - view.editor.sizeHint().height() // 2)
        cur = self.o_reader_ring.current()
        view.editor.setReadOnly(False)
        view.editor.setText(cur if cur != '.' else '')
        view.editor.setCursorPosition(len(view.editor.text()))
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _transform_navigate(self, delta):
        """Advance the reader position and load next line into transform."""
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(delta)
        self.transform_view._offset = 0.0
        cur = self.o_reader_ring.current()
        self.transform_view.editor.setText(cur)
        self.transform_view.editor.setCursorPosition(len(cur))
        self.transform_view.update()

    def _transform_confirm(self):
        """Append edited line to active I/ doc, advance to next reader line."""
        view = self.transform_view
        new_text = view.editor.text().strip()
        if not new_text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, new_text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        # Advance reader to next non-dot line
        self.o_reader_ring.move(1)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(1)
        self.transform_view._offset = 0.0
        self.transform_view.update()
        cur = self.o_reader_ring.current()
        view.editor.setText(cur)
        view.editor.setCursorPosition(len(cur))
        view.editor.setFocus()
        print(f"✅ Transform→Doc[{insert_pos}]: '{new_text}'")

    # ── TTS ───────────────────────────────────────────────────────────────────

    _TTS_MODELS = {
        'en': os.path.expanduser('~/void/tts/en_GB-alan-medium.onnx'),
        'es': os.path.expanduser('~/void/tts/es_ES-sharvard-medium.onnx'),
        'it': os.path.expanduser('~/void/tts/it_IT-riccardo-x_low.onnx'),
    }

    def _detect_lang(self, text):
        try:
            from langdetect import detect
            lang = detect(text)
            return lang if lang in self._TTS_MODELS else 'en'
        except Exception:
            return 'en'

    def _tts_speak(self, text):
        if not text or text == '.':
            return
        self._tts_stop_proc()
        # Use prefetched audio if available
        if self._tts_prefetch_text == text and self._tts_prefetch_data:
            try:
                aplay = subprocess.Popen(
                    ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                data = self._tts_prefetch_data
                self._tts_prefetch_data = None
                self._tts_prefetch_text = None
                # Write in background — pipe buffer blocks main thread otherwise
                def _pipe(proc, buf):
                    try:
                        proc.stdin.write(buf)
                        proc.stdin.close()
                    except Exception:
                        pass
                threading.Thread(target=_pipe, args=(aplay, data), daemon=True).start()
                self._tts_process = aplay
                self._tts_piper = None
                return
            except Exception:
                pass
        lang = self._detect_lang(text)
        model = self._TTS_MODELS.get(lang, self._TTS_MODELS['en'])
        if not os.path.exists(model):
            print(f"⚠️ TTS model not found: {model}")
            return
        try:
            piper = subprocess.Popen(
                ['piper', '--model', model, '--length_scale', '1.15', '--output_raw'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            aplay = subprocess.Popen(
                ['aplay', '-r', '22050', '-f', 'S16_LE', '-t', 'raw', '-'],
                stdin=piper.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            piper.stdin.write(text.encode('utf-8', errors='replace'))
            piper.stdin.close()
            piper.stdout.close()
            self._tts_process = aplay
            self._tts_piper  = piper
        except FileNotFoundError as e:
            print(f"⚠️ TTS error: {e}")

    def _tts_stop_proc(self):
        for proc in (getattr(self, '_tts_piper', None), self._tts_process):
            if proc and proc.poll() is None:
                proc.terminate()
        self._tts_process = None
        self._tts_piper   = None

    def _tts_prefetch(self, text):
        """Pre-render next line's audio in background so playback is gapless."""
        if not text or text in ('.', '') or text == self._tts_prefetch_text:
            return
        self._tts_prefetch_text = text
        self._tts_prefetch_data = None
        lang = self._detect_lang(text)
        model = self._TTS_MODELS.get(lang, self._TTS_MODELS['en'])
        def _fetch():
            try:
                piper = subprocess.Popen(
                    ['piper', '--model', model, '--length_scale', '1.15', '--output_raw'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
                data, _ = piper.communicate(text.encode('utf-8', errors='replace'))
                self._tts_prefetch_data = data
            except Exception:
                self._tts_prefetch_data = b''
        threading.Thread(target=_fetch, daemon=True).start()

    def _tts_stop(self):
        self._tts_timer.stop()
        self._tts_stop_proc()

    def _tts_toggle(self):
        self.tts_active = not self.tts_active
        if not self.tts_active:
            self._tts_stop()
            print("🔇 TTS off")
        else:
            print("🔊 TTS on")
            self._tts_on_view(self.current_view)

    def _tts_on_view(self, view_index):
        """Start TTS behaviour appropriate for the given view."""
        if not self.tts_active:
            return
        self._tts_stop()
        if view_index == 0:                          # F1 — single line
            self._tts_speak(self.line_ring.current())
        elif view_index == 1:                        # F2 — sequential through I/
            cur = self.line_ring.current()
            if cur != '.':
                self._tts_speak(cur)
            self._tts_timer.start()
        elif view_index == 4:                        # F5 — single O/ line
            self._tts_speak(self.entry.text())
        elif view_index == 5:                        # F6 — sequential through O/ book
            cur = self.o_reader_ring.current()
            if cur not in ('.', ''):
                self._tts_speak(cur)
            self._tts_timer.start()
        elif view_index == 3:                        # F4 — oracle I/
            self._tts_speak(self.vault_ring.current())
        elif view_index == 7:                        # F8 — oracle O/
            self._tts_speak(self.oracle_o_ring.current())

    def _tts_poll(self):
        """Poll every 50ms; when aplay finishes, advance and speak next line."""
        if not self.tts_active:
            self._tts_timer.stop()
            return
        if self._tts_process and self._tts_process.poll() is None:
            return  # still speaking
        if self.current_view == 1:                   # F2 sequential
            self.line_ring.move(1)
            while self.line_ring.current() == '.':
                self.line_ring.move(1)
            if self.circular_view:
                self.circular_view._offset = 0.0
                self.circular_view.editor.setText(self.line_ring.current())
                self.circular_view.update()
            self._tts_speak(self.line_ring.current())
            # Prefetch the line after this one
            lines = self.line_ring.lines
            idx = self.line_ring.index
            peek = (idx + 1) % len(lines)
            while lines[peek] == '.' and peek != idx:
                peek = (peek + 1) % len(lines)
            self._tts_prefetch(lines[peek])
        elif self.current_view == 5:                 # F6 sequential
            self.o_reader_ring.move(1)
            while self.o_reader_ring.current() in ('.', ''):
                self.o_reader_ring.move(1)
            if self.o_reader_view:
                self.o_reader_view._offset = 0.0
                self.o_reader_view.editor.setText(self.o_reader_ring.current())
                self.o_reader_view.update()
            self._tts_speak(self.o_reader_ring.current())
            # Prefetch the line after this one
            lines = self.o_reader_ring.lines
            idx = self.o_reader_ring.index
            peek = (idx + 1) % len(lines)
            while lines[peek] in ('.', '') and peek != idx:
                peek = (peek + 1) % len(lines)
            self._tts_prefetch(lines[peek])
        else:
            self._tts_timer.stop()

    def take_screenshot(self):
        """F12: Capture the full screen and save to void_dir/screenshots/."""
        screen = self.screen()
        pixmap = screen.grabWindow(0)
        screenshots_dir = os.path.join(self.void_dir, 'screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(screenshots_dir, f"snap_{ts}.png")
        pixmap.save(path)
        print(f"📸 Screenshot: {path}")

    def print_doc(self):
        """Ctrl+P in F2: send active file to physical printer."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        self._render_doc(printer)

    def export_doc(self):
        """Ctrl+S in F2: save active file as PDF, pre-named after the file."""
        doc_path = self.current_file_path
        file_name = os.path.splitext(os.path.basename(doc_path))[0]
        default_path = os.path.join(os.path.dirname(doc_path), file_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        self._render_doc(printer)

    def print_vault(self):
        """Ctrl+P in F4: send all vault lines to physical printer."""
        printer = self._printer_from_dialog()
        if printer is None:
            return
        self._render_vault(printer)

    def export_vault(self):
        """Ctrl+S in F4: save all vault lines as PDF, pre-named after the vault folder."""
        vault_name = os.path.basename(os.path.normpath(self.void_dir))
        default_path = os.path.join(self.void_dir, vault_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        self._render_vault(printer)

    def _render_vault(self, printer):
        """Build HTML from current vault ring lines and send to printer."""
        lines = [l for l in self.vault_ring.lines if l and l != '.']
        vault_name = os.path.basename(os.path.normpath(self.void_dir))
        self._send_to_printer(printer, self._build_doc_html(lines, vault_name))

    def _render_doc(self, printer):
        """Build HTML from the active file and send to printer."""
        doc_path = self.current_file_path
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception as e:
            print(f"❌ Print error reading file: {e}")
            return
        title = os.path.splitext(os.path.basename(doc_path))[0]
        self._send_to_printer(printer, self._build_doc_html(lines, title))

    def open_screenshots_folder(self):
        """Ctrl+F12: Open the screenshots folder in the system file explorer."""
        screenshots_dir = os.path.join(self.void_dir, 'screenshots')
        os.makedirs(screenshots_dir, exist_ok=True)
        subprocess.Popen(['xdg-open', screenshots_dir])

    def _toggle_help(self):
        if not self._help_overlay:
            self._help_overlay = HelpOverlay(self)
            self._help_overlay.setGeometry(self.rect())
        self._help_overlay.toggle()

    # ── File navigation ───────────────────────────────────────────────────────

    def scan_txt_files(self):
        """Scan book_dir recursively for .txt files."""
        self.txt_files = sorted(
            os.path.join(root, f)
            for root, _, files in os.walk(self.book_dir)
            for f in files
            if f.lower().endswith('.txt')
        )
        if self.current_file_path not in self.txt_files:
            self.txt_files.append(self.current_file_path)
            self.txt_files.sort()
        self.current_file_index = self.txt_files.index(self.current_file_path)

    def switch_to_file(self, file_path):
        if not os.path.exists(file_path):
            open(file_path, 'w', encoding='utf-8').close()
        self.current_file_path = file_path
        self.current_file_index = self.txt_files.index(file_path)
        print(f"📂 Write target: {os.path.basename(file_path)}")
        if self.current_view == 0:
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(0)

    def show_previous_file(self):
        if not self.txt_files:
            return
        self.current_file_index = (self.current_file_index - 1) % len(self.txt_files)
        self.switch_to_file(self.txt_files[self.current_file_index])

    def show_next_file(self):
        if not self.txt_files:
            return
        self.current_file_index = (self.current_file_index + 1) % len(self.txt_files)
        self.switch_to_file(self.txt_files[self.current_file_index])

    # ── Swap operations (F2 doc lines only) ──────────────────────────────────

    def _swap_words(self, direction):
        """Alt+Left/Right: swap word(s) at cursor or selection within the current line.
        Trailing sentence-ending punctuation (.!?…) stays fixed at the end.
        direction: -1=left, +1=right. Wraps circularly."""
        editor = self.circular_view.editor
        text = editor.text()
        if not text.strip():
            return

        # Separate trailing sentence-ending punctuation
        trailing = ''
        core = text
        if text and text[-1] in '.!?…':
            j = len(text) - 1
            while j >= 0 and text[j] in '.!?…':
                j -= 1
            candidate_core = text[:j + 1]
            if candidate_core.strip():
                core = candidate_core
                trailing = text[j + 1:]

        # Split into tokens (split on spaces, drop empties)
        tokens = core.split()
        if len(tokens) < 2:
            return

        # Build span positions for each token in `core`
        spans = []
        search_from = 0
        for tok in tokens:
            idx = core.find(tok, search_from)
            spans.append((idx, idx + len(tok)))
            search_from = idx + len(tok)

        # Determine which token(s) form the "block" to move
        if editor.hasSelectedText():
            sel_start = editor.selectionStart()
            sel_end = sel_start + len(editor.selectedText())
            block_indices = [i for i, (s, e) in enumerate(spans)
                             if s >= sel_start and e <= sel_end]
            if not block_indices:
                block_indices = [i for i, (s, e) in enumerate(spans)
                                 if s < sel_end and e > sel_start]
        else:
            cur = editor.cursorPosition()
            block_indices = [i for i, (s, e) in enumerate(spans) if s <= cur <= e]
            if not block_indices:
                # cursor between tokens: pick nearest
                block_indices = [min(range(len(spans)),
                                     key=lambda i: min(abs(cur - spans[i][0]),
                                                       abs(cur - spans[i][1])))]

        if not block_indices:
            return

        b0, b1 = block_indices[0], block_indices[-1]
        n = len(tokens)
        block = tokens[b0:b1 + 1]

        if direction == -1:  # swap left
            if b0 == 0:
                # wrap: block moves to end
                rest = tokens[b1 + 1:]
                new_tokens = rest + block
                new_b0 = len(rest)
            else:
                new_tokens = tokens[:b0 - 1] + block + [tokens[b0 - 1]] + tokens[b1 + 1:]
                new_b0 = b0 - 1
        else:  # swap right
            if b1 == n - 1:
                # wrap: block moves to start
                rest = tokens[:b0]
                new_tokens = block + rest
                new_b0 = 0
            else:
                new_tokens = tokens[:b0] + [tokens[b1 + 1]] + block + tokens[b1 + 2:]
                new_b0 = b0 + 1

        new_text = ' '.join(new_tokens) + trailing
        had_selection = editor.hasSelectedText()
        editor.setText(new_text)

        # Place cursor at start of moved block; restore selection if there was one
        new_b1 = new_b0 + (b1 - b0)
        sel_start = sum(len(new_tokens[i]) + 1 for i in range(new_b0))
        sel_end = sum(len(new_tokens[i]) + 1 for i in range(new_b1 + 1)) - 1
        if had_selection:
            editor.setSelection(sel_start, sel_end - sel_start)
        else:
            editor.setCursorPosition(sel_start)

        self.line_ring.lines[self.line_ring.index] = new_text
        self.auto_save_circular()
        self.circular_view.update()

    def _delete_line_to_zero(self):
        """Ctrl+Delete / Ctrl+Backspace in F2: send line to 0.txt (recycle bin).
        When already viewing 0.txt, permanently deletes the line."""
        lines = self.line_ring.lines
        n = len(lines)
        cur = self.line_ring.index
        if n <= 1:
            return
        line = lines[cur]
        new_lines = [l for i, l in enumerate(lines) if i != cur]
        new_index = min(cur, len(new_lines) - 1)

        on_scratch = os.path.abspath(self.current_file_path) == os.path.abspath(self.f1_file)

        if not on_scratch:
            try:
                with open(self.f1_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
                print(f"♻️ → 0.txt: {line[:60]}")
            except Exception as e:
                print(f"❌ Delete to 0.txt error: {e}")
                return
        else:
            print(f"🗑️ Deleted: {line[:60]}")

        self.line_ring.lines = new_lines
        self.line_ring.index = new_index
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def _find_move_target(self, start, delta):
        """Find nearest non-dot index in direction delta (wrapping).
        Returns (index, wrapped) where wrapped=True means the boundary was crossed."""
        n = len(self.line_ring.lines)
        idx = (start + delta) % n
        for _ in range(n - 1):
            if self.line_ring.lines[idx] != '.':
                wrapped = (delta == -1 and idx > start) or (delta == 1 and idx < start)
                return idx, wrapped
            idx = (idx + delta) % n
        return None, False

    def _swap_line_in_focus(self, delta):
        """Swap line within para focus content, wrapping circularly inside the paragraph."""
        content = self._para_focus_content
        if not content:
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        pos = content.index(cur) if cur in content else 0
        other_pos = (pos + delta) % len(content)
        other = content[other_pos]
        lines[cur], lines[other] = lines[other], lines[cur]
        # Update focus_content indices to follow swapped positions
        self._para_focus_content[pos], self._para_focus_content[other_pos] = \
            self._para_focus_content[other_pos], self._para_focus_content[pos]
        self.line_ring.index = other
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def swap_line_up(self):
        if len(self.line_ring.lines) < 2:
            return
        if self._para_focus:
            self._swap_line_in_focus(-1)
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        n = len(lines)
        prev = (cur - 1) % n
        lines[cur], lines[prev] = lines[prev], lines[cur]
        self.line_ring.index = prev
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def swap_line_down(self):
        if len(self.line_ring.lines) < 2:
            return
        if self._para_focus:
            self._swap_line_in_focus(+1)
            return
        lines = self.line_ring.lines
        cur = self.line_ring.index
        n = len(lines)
        nxt = (cur + 1) % n
        lines[cur], lines[nxt] = lines[nxt], lines[cur]
        self.line_ring.index = nxt
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    # ── Paragraph helpers ─────────────────────────────────────────────────────
    # Model: each '.' is a paragraph separator. _paragraphs_from_ring extracts
    # paragraph content arrays (no dots). _rebuild_ring_from_paragraphs puts them
    # back, always emitting a dot before each paragraph. This makes circular
    # paragraph operations (including wrapping first↔last) natural.

    def _paragraphs_from_ring(self):
        """Return (dot_indices, paragraphs) where paragraphs[k] is the list of
        content lines between dot_indices[k] and the next dot (or end)."""
        lines = self.line_ring.lines
        dot_indices = [i for i, l in enumerate(lines) if l == '.']
        if not dot_indices:
            return [], [list(lines)]
        paragraphs = []
        for k, d in enumerate(dot_indices):
            next_d = dot_indices[k + 1] if k + 1 < len(dot_indices) else len(lines)
            paragraphs.append(list(lines[d + 1:next_d]))
        return dot_indices, paragraphs

    def _rebuild_ring_from_paragraphs(self, paragraphs):
        """Rebuild ring.lines from paragraph content arrays, inserting a dot before each."""
        new_lines = []
        for para in paragraphs:
            new_lines.append('.')
            new_lines.extend(para)
        self.line_ring.lines = new_lines

    def _dot_line_index(self, para_idx, paragraphs):
        """Return the line index of the dot that precedes paragraphs[para_idx]."""
        return sum(1 + len(paragraphs[j]) for j in range(para_idx))

    def goto_prev_dot(self):
        ring = self.line_ring
        n = len(ring.lines)
        if n == 0:
            return
        idx = (ring.index - 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                return
            idx = (idx - 1) % n

    def goto_next_dot(self):
        ring = self.line_ring
        n = len(ring.lines)
        if n == 0:
            return
        idx = (ring.index + 1) % n
        for _ in range(n):
            if ring.lines[idx] == '.':
                ring.index = idx
                return
            idx = (idx + 1) % n

    def _move_paragraph(self, k, paragraphs, direction):
        """Move paragraph k up (-1) or down (+1). At boundaries: move, not swap."""
        n = len(paragraphs)
        if n <= 1:
            return
        other_k = k + direction
        wrapped = other_k < 0 or other_k >= n
        if not wrapped:
            # Normal: swap adjacent paragraphs
            paragraphs[k], paragraphs[other_k] = paragraphs[other_k], paragraphs[k]
            dest = other_k
        else:
            # Boundary: remove and insert at the other end
            para = paragraphs.pop(k)
            if direction == -1:
                paragraphs.append(para)   # first → becomes last
                dest = len(paragraphs) - 1
            else:
                paragraphs.insert(0, para)  # last → becomes first
                dest = 0
        self._rebuild_ring_from_paragraphs(paragraphs)
        self.line_ring.index = self._dot_line_index(dest, paragraphs)
        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(self.line_ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()

    def _current_para_idx(self):
        """Return the paragraph index (k) whose dot is at ring.index, or None."""
        _, paragraphs = self._paragraphs_from_ring()
        for k in range(len(paragraphs)):
            if self._dot_line_index(k, paragraphs) == self.line_ring.index:
                return k, paragraphs
        return None, None

    def swap_paragraph_up(self):
        if not self.line_ring.lines or self.line_ring.current() != '.':
            return
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        self._move_paragraph(k, paragraphs, -1)

    def swap_paragraph_down(self):
        if not self.line_ring.lines or self.line_ring.current() != '.':
            return
        k, paragraphs = self._current_para_idx()
        if k is None:
            return
        self._move_paragraph(k, paragraphs, +1)

    def rebase_to_index_zero(self):
        """Ctrl+0 in F2: make current line/paragraph the first in the ring."""
        if self.current_view != 1:
            return
        ring = self.line_ring
        _, paragraphs = self._paragraphs_from_ring()

        if ring.current() == '.':
            # Standing on a dot: rotate paragraphs so this one becomes first
            dot_indices, _ = self._paragraphs_from_ring()
            para_idx = dot_indices.index(ring.index) if ring.index in dot_indices else 0
            if para_idx == 0:
                return
            paragraphs = paragraphs[para_idx:] + paragraphs[:para_idx]
            self._rebuild_ring_from_paragraphs(paragraphs)
            ring.index = 0
        else:
            # Standing on a text line: rotate within its paragraph
            for k, para in enumerate(paragraphs):
                dot_pos = self._dot_line_index(k, paragraphs)
                next_dot = dot_pos + 1 + len(para)
                if dot_pos < ring.index < next_dot:
                    offset = ring.index - dot_pos - 1
                    paragraphs[k] = para[offset:] + para[:offset]
                    self._rebuild_ring_from_paragraphs(paragraphs)
                    ring.index = self._dot_line_index(k, paragraphs) + 1
                    break

        self.auto_save_circular()
        self.circular_view._offset = 0.0
        self.circular_view.editor.setText(ring.current())
        self.circular_view.editor.setCursorPosition(0)
        self.circular_view.update()
        print(f"🔁 Rebase | '{ring.current()[:50]}'")

    # ── UI init ───────────────────────────────────────────────────────────────

    def init_ui(self):
        self.showFullScreen()
        self.setCentralWidget(self.stack)
        self._reposition_entry()

        # FxPanel: in-app tuner for Hyprland visual effects (CRT/grain/B&W).
        # Self-contained — writes /tmp/voider-fx and runs `voider-fx-update`.
        # Opened by a Hyprland keybind that drops a request file we poll for.
        self._fx_panel = FxPanel(self)
        self._fx_panel.setGeometry(self.rect())
        self._panel_poll = QTimer(self)
        self._panel_poll.timeout.connect(self._poll_fx_panel)
        self._panel_poll.start(100)

    def _poll_fx_panel(self):
        path = '/tmp/voider-fx-panel'
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                effect = f.read().strip()
            os.unlink(path)
        except OSError:
            return
        if not effect:
            return
        panel = self._fx_panel
        if panel.isVisible() and panel.current_effect == effect:
            panel.close_panel()
        else:
            panel.open_panel(effect)

    def _reposition_entry(self):
        w = self.width()
        h = self.height()
        if w == 0 or h == 0:
            return
        entry_width = min(w, h) - 90
        entry_height = self.entry.sizeHint().height()
        self.entry.setFixedWidth(entry_width)
        self.entry.move(w // 2 - entry_width // 2, h // 2 - entry_height // 2)
        # Search bars sit near the bottom
        bar_width = min(w - 100, 800)
        bar_x = (w - bar_width) // 2
        bar_y = h - entry_height - 24
        self._f2_search_bar.setFixedWidth(bar_width)
        self._f2_search_bar.move(bar_x, bar_y)
        self._f3_search_bar.setFixedWidth(bar_width)
        self._f3_search_bar.move(bar_x, bar_y)

    def closeEvent(self, event):
        self._ws_save_position()
        self._save_working_set()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_entry()
        if self._help_overlay:
            self._help_overlay.setGeometry(self.rect())
        if hasattr(self, '_fx_panel'):
            self._fx_panel.setGeometry(self.rect())

    def leaveEvent(self, event):
        """Restore focus to the active editor when the mouse leaves the window."""
        super().leaveEvent(event)
        self._refocus_active_editor()

    def _setup_opacity_shortcuts(self):
        up = QShortcut(QKeySequence("Ctrl++"), self)
        up.setContext(Qt.ShortcutContext.ApplicationShortcut)
        up.activated.connect(lambda: self._change_opacity(0.1))
        down = QShortcut(QKeySequence("Ctrl+-"), self)
        down.setContext(Qt.ShortcutContext.ApplicationShortcut)
        down.activated.connect(lambda: self._change_opacity(-0.1))

    def _change_opacity(self, delta):
        self.opacity = max(0.0, min(1.0, self.opacity + delta))
        self.setWindowOpacity(self.opacity)

    def _refocus_active_editor(self):
        if self.current_view == 0:
            if self._f1_scratch_mode and self.scratch_view:
                self.scratch_view.editor.setFocus()
            else:
                self.entry.setFocus()
        elif self.current_view == 1 and self.circular_view:
            self.circular_view.editor.setFocus()
        elif self.current_view == 2 and self.book_view:
            self.book_view.editor.setFocus()
        elif self.current_view == 3 and self.vault_view:
            self.vault_view.editor.setFocus()
        elif self.current_view == 9 and self.book_concat_view:
            self.book_concat_view.editor.setFocus()

    # ── Key routing ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        # Route Up/Down to the display ring when search is active (clamped, no wrap)
        if self._f2_search_active and self.current_view == 1 and self._f2_display_ring:
            if key == Qt.Key.Key_Up:
                self._f2_display_ring.index = max(0, self._f2_display_ring.index - 1)
                self.circular_view._offset = 0.0
                self._f2_search_show_center()
                event.accept(); return
            elif key == Qt.Key.Key_Down:
                self._f2_display_ring.index = min(len(self._f2_display_ring.lines) - 1,
                                                  self._f2_display_ring.index + 1)
                self.circular_view._offset = 0.0
                self._f2_search_show_center()
                event.accept(); return
        if self._f3_search_active and self.current_view == 2 and self._f3_display_ring:
            if key == Qt.Key.Key_Up:
                self._f3_display_ring.index = max(0, self._f3_display_ring.index - 1)
                self.book_view._offset = 0.0
                self._f3_search_show_center()
                event.accept(); return
            elif key == Qt.Key.Key_Down:
                self._f3_display_ring.index = min(len(self._f3_display_ring.lines) - 1,
                                                  self._f3_display_ring.index + 1)
                self.book_view._offset = 0.0
                self._f3_search_show_center()
                event.accept(); return

        # Global: view switching
        if self._matches(key, mods, 'view_f1'):
            self.switch_to_view(0); event.accept(); return
        if self._matches(key, mods, 'view_f2'):
            self.switch_to_view(1); event.accept(); return
        if self._matches(key, mods, 'view_f3'):
            if self.current_view != 2:
                self.switch_to_view(2)
            event.accept(); return
        if self._matches(key, mods, 'view_f4'):
            self.switch_to_view(3); event.accept(); return
        if self._matches(key, mods, 'view_f5'):
            self.switch_to_view(4); event.accept(); return
        if self._matches(key, mods, 'view_f6'):
            self.switch_to_view(5); event.accept(); return
        if self._matches(key, mods, 'view_f7'):
            self.switch_to_view(6); event.accept(); return
        if self._matches(key, mods, 'view_f8'):
            self.switch_to_view(7); event.accept(); return
        if self._matches(key, mods, 'view_f9'):
            self.switch_to_view(8); event.accept(); return
        if self._matches(key, mods, 'help'):
            self._toggle_help(); event.accept(); return

        # F1: Ctrl+Enter → temporary peek at 0.txt in F2 (doesn't change f2_file)
        if self.current_view == 0 and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                (mods & Qt.KeyboardModifier.ControlModifier):
            self._f2_peek_0 = True
            self.switch_to_view(1)
            event.accept()
            return

        # Global: rebase (F2 only, enforced inside; F3 handled view-specifically)
        if self._matches(key, mods, 'rebase') and self.current_view != 2:
            self.rebase_to_index_zero(); event.accept(); return

        # Global: reshuffle vault
        if self._matches(key, mods, 'reshuffle'):
            self.load_vault_lines()
            if self.current_view == 3 and self.vault_view:
                self.vault_view.update()
            event.accept(); return

        # Global: file/folder pickers
        if self._matches(key, mods, 'pick_active_file'):
            self.pick_active_file(); event.accept(); return
        if self._matches(key, mods, 'pick_book_dir'):
            self.pick_book_directory(); event.accept(); return
        if self._matches(key, mods, 'pick_dir'):
            self.change_void_directory(); event.accept(); return

        # Print (Ctrl+P) and Export/Save as (Ctrl+S)
        if self._matches(key, mods, 'print_doc') and self.current_view == 2:
            self.print_book(); event.accept(); return
        if self._matches(key, mods, 'print_doc') and self.current_view == 1:
            self.print_doc(); event.accept(); return
        if self._matches(key, mods, 'print_doc') and self.current_view == 3:
            self.print_vault(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 2:
            self.export_book(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 1:
            self.export_doc(); event.accept(); return
        if self._matches(key, mods, 'export_doc') and self.current_view == 3:
            self.export_vault(); event.accept(); return

        # Global: screenshot / open folder
        if self._matches(key, mods, 'screenshot'):
            self.take_screenshot(); event.accept(); return
        if self._matches(key, mods, 'open_screenshots'):
            self.open_screenshots_folder(); event.accept(); return

        if self._matches(key, mods, 'backup'):
            self._backup_vault()
            event.accept(); return

        if self._matches(key, mods, 'tts_toggle'):
            self._tts_toggle(); event.accept(); return

        # View-specific
        if self.current_view == 0:
            self._handle_f1_keys(key, mods)
        elif self.current_view == 1:
            self._handle_f2_keys(key, mods, event)
        elif self.current_view == 2:
            self._handle_f3_keys(key, mods, event)
        elif self.current_view == 3:
            self._handle_f4_keys(key, mods, event)
        elif self.current_view == 4:
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(0); event.accept()
            elif self._matches(key, mods, 'quit'):
                self.close(); event.accept()
            elif key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
                self._f5_navigate(-1); event.accept()
            elif key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
                self._f5_navigate(1); event.accept()
        elif self.current_view in (5, 6, 7):
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(0); event.accept()
            elif self._matches(key, mods, 'quit'):
                self.close(); event.accept()
        elif self.current_view == 9:
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(2); event.accept()
            elif self._matches(key, mods, 'quit'):
                self.close(); event.accept()

    def _handle_f1_keys(self, key, mods):
        if self._f1_scratch_mode and key == Qt.Key.Key_Escape:
            self._exit_f1_scratch()
            return
        if self._matches(key, mods, 'quit'):
            self.close()
        elif self._matches(key, mods, 'file_prev'):
            self.show_previous_file()
        elif self._matches(key, mods, 'file_next'):
            self.show_next_file()
        elif self._matches(key, mods, 'para_prev'):
            self.goto_prev_dot()
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(0)
            self.current_active_line_index = self.line_ring.index
        elif self._matches(key, mods, 'para_next'):
            self.goto_next_dot()
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(0)
            self.current_active_line_index = self.line_ring.index
        elif key == Qt.Key.Key_Up and mods == Qt.KeyboardModifier.NoModifier:
            # If entry is empty and ring is already at the last sent line, show it first
            if not self.entry.text() and self.current_active_line_index is None:
                pass  # don't move, just show current
            else:
                self.line_ring.move(-1)
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(len(self.entry.text()))
            self.current_active_line_index = self.line_ring.index
            print(f"⬆️ F1: index={self.line_ring.index}")
        elif key == Qt.Key.Key_Down and mods == Qt.KeyboardModifier.NoModifier:
            self.line_ring.move(1)
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(0)
            self.current_active_line_index = self.line_ring.index
            print(f"⬇️ F1: index={self.line_ring.index}")

    def _handle_f2_keys(self, key, mods, event):
        # Up/Down/Enter handled by circular_view.editor signals.
        if self._matches(key, mods, 'swap_up'):
            if self.line_ring.current() == '.':
                self.swap_paragraph_up()
            else:
                self.swap_line_up()
            event.accept()
        elif self._matches(key, mods, 'swap_down'):
            if self.line_ring.current() == '.':
                self.swap_paragraph_down()
            else:
                self.swap_line_down()
            event.accept()
        elif self._matches(key, mods, 'para_prev'):
            self.goto_prev_dot()
            self._doc_show_editor()
            event.accept()
        elif self._matches(key, mods, 'para_next'):
            self.goto_next_dot()
            self._doc_show_editor()
            event.accept()
        elif self._matches(key, mods, 'reformat_file'):
            # On 0.txt this key splits the scratch into documents; elsewhere it
            # reformats the active file into one sentence per line.
            if os.path.abspath(self.current_file_path) == os.path.abspath(self.f1_file):
                self._split_zero_to_docs()
            else:
                self.reformat_active_file()
            event.accept()
        elif self._matches(key, mods, 'shuffle_zero'):
            self._shuffle_zero()
            event.accept()
        elif (mods & Qt.KeyboardModifier.ControlModifier) and key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            editor = self.circular_view.editor
            at_start = editor.cursorPosition() == 0
            at_end = editor.cursorPosition() == len(editor.text())
            if (key == Qt.Key.Key_Delete and at_start) or (key == Qt.Key.Key_Backspace and at_end):
                self._delete_line_to_zero()
                event.accept()
        elif mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_F:
            self._open_f2_search(); event.accept()
        elif key == Qt.Key.Key_Escape:
            if self._f2_search_active:
                self._close_f2_search(restore=True)
            elif self._para_focus:
                self._exit_para_focus()
            else:
                self.switch_to_view(0)

    def _handle_f3_keys(self, key, mods, event):
        # Up/Down/Enter handled by book_view.editor signals.
        if mods == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_F:
            self._open_f3_search(); event.accept(); return
        if key == Qt.Key.Key_Escape and self._f3_search_active:
            self._close_f3_search(restore=True); event.accept(); return
        if key == Qt.Key.Key_Escape:
            if self._book_pending_new:
                idx = self.book_ring.index
                self.book_ring.lines.pop(idx)
                self._library_lines.pop(idx)
                if not self.book_ring.lines:
                    self.book_ring.lines = ['.']
                    self._library_lines = ['.']
                self.book_ring.index = max(0, idx - 1) % len(self.book_ring.lines)
                self._book_pending_new = False
                self.book_view._offset = 0.0
                self._book_show_editor()
            else:
                self.switch_to_view(0)
        elif self._matches(key, mods, 'para_prev'):
            ring = self.book_ring
            n = len(ring.lines)
            idx = (ring.index - 1) % n
            for _ in range(n):
                if ring.lines[idx] == '.':
                    ring.index = idx
                    break
                idx = (idx - 1) % n
            self._book_show_editor(); event.accept()
        elif self._matches(key, mods, 'para_next'):
            ring = self.book_ring
            n = len(ring.lines)
            idx = (ring.index + 1) % n
            for _ in range(n):
                if ring.lines[idx] == '.':
                    ring.index = idx
                    break
                idx = (idx + 1) % n
            self._book_show_editor(); event.accept()
        elif self._matches(key, mods, 'swap_up'):
            self._book_swap_up(); event.accept()
        elif self._matches(key, mods, 'swap_down'):
            self._book_swap_down(); event.accept()
        elif self._matches(key, mods, 'rebase'):
            self._book_rebase(); event.accept()
        elif self._matches(key, mods, 'reformat_file'):
            self._merge_zero_files(silent=False); event.accept()
        elif self._matches(key, mods, 'quit'):
            self.close()

    def _handle_f4_keys(self, key, mods, event):
        # Up/Down/Enter handled by vault_view.editor signals.
        if key == Qt.Key.Key_Escape:
            self.vault_view.edit_mode = False
            self.vault_view.editor.hide()
            self.switch_to_view(0)
        elif self._matches(key, mods, 'quit'):
            self.close()

    # ── Search (F2 / F3) ─────────────────────────────────────────────────────
    # A separate _search_ring is used for display — line_ring / book_ring are
    # NEVER mutated during search, so the save pipeline never sees filtered data.

    def _f2_search_show_center(self):
        """Highlight center of display ring; surroundings dimmed. Search bar keeps focus."""
        if not self._f2_display_ring or not self.circular_view:
            return
        view = self.circular_view
        view.edit_mode = False
        view.editor.hide()
        view.search_highlight_center = True
        view.update()
        self._f2_search_bar.setFocus()

    def _open_f2_search(self):
        if self._f2_search_active:
            return
        self._f2_search_active = True
        self._f2_search_saved = self.line_ring.index
        display = [l for l in self.line_ring.lines if l != '.'] or ['.']
        self._f2_display_ring = LineRing(display)
        # Start at the line currently shown in F2
        cur = self.line_ring.current()
        if cur and cur != '.' and cur in display:
            self._f2_display_ring.index = display.index(cur)
        self.circular_view.search_mode = True
        self.circular_view.ring = self._f2_display_ring
        self.circular_view._offset = 0.0
        self._f2_search_bar.clear()
        self._f2_search_bar.show()
        self._f2_search_bar.raise_()
        self._f2_search_show_center()

    def _close_f2_search(self, restore=True):
        if not self._f2_search_active:
            return
        self._f2_search_active = False
        self._f2_search_bar.hide()
        self._f2_display_ring = None
        if restore and self._f2_search_saved is not None:
            self.line_ring.index = self._f2_search_saved
        self.circular_view.search_mode = False
        self.circular_view.search_highlight_center = False
        self.circular_view.ring = self.line_ring
        self._f2_search_saved = None
        self.circular_view._offset = 0.0
        self.circular_view.update()
        self._doc_show_editor()

    def _f2_search_changed(self, text):
        if not self._f2_search_active:
            return
        q = text.strip().lower()
        if not q:
            filtered = [l for l in self.line_ring.lines if l != '.'] or ['.']
        else:
            filtered = [l for l in self.line_ring.lines if l != '.' and q in l.lower()] or ['.']
        self._f2_display_ring = LineRing(filtered)
        self.circular_view.ring = self._f2_display_ring
        self.circular_view._offset = 0.0
        self._f2_search_show_center()

    def _f2_search_confirm(self):
        """Enter: jump to the highlighted match in the full ring and close search."""
        if not self._f2_search_active:
            return
        matched = self._f2_display_ring.current() if self._f2_display_ring else None
        self._f2_search_active = False
        self._f2_search_bar.hide()
        self._f2_display_ring = None
        self._f2_search_saved = None
        if matched and matched != '.' and matched in self.line_ring.lines:
            self.line_ring.index = self.line_ring.lines.index(matched)
        self.circular_view.search_mode = False
        self.circular_view.search_highlight_center = False
        self.circular_view.ring = self.line_ring
        self.circular_view._offset = 0.0
        self.circular_view.update()
        self._doc_show_editor()

    def _f3_search_show_center(self):
        """Highlight center of display ring; surroundings dimmed. Search bar keeps focus."""
        if not self._f3_display_ring or not self.book_view:
            return
        view = self.book_view
        view.edit_mode = False
        view.editor.hide()
        view.search_highlight_center = True
        view.update()
        self._f3_search_bar.setFocus()

    def _open_f3_search(self):
        if self._f3_search_active:
            return
        self._f3_search_active = True
        self._f3_search_saved = self.book_ring.index
        display = [l for l in self.book_ring.lines if l != '.'] or ['.']
        self._f3_display_ring = LineRing(display)
        # Start at the file currently highlighted in F3
        cur = self.book_ring.current()
        if cur and cur != '.' and cur in display:
            self._f3_display_ring.index = display.index(cur)
        self.book_view.search_mode = True
        self.book_view.ring = self._f3_display_ring
        self.book_view._offset = 0.0
        self._f3_search_bar.clear()
        self._f3_search_bar.show()
        self._f3_search_bar.raise_()
        self._f3_search_show_center()

    def _close_f3_search(self, restore=True):
        if not self._f3_search_active:
            return
        self._f3_search_active = False
        self._f3_search_bar.hide()
        self._f3_display_ring = None
        if restore and self._f3_search_saved is not None:
            self.book_ring.index = self._f3_search_saved
        self.book_view.search_mode = False
        self.book_view.search_highlight_center = False
        self.book_view.ring = self.book_ring
        self._f3_search_saved = None
        self.book_view._offset = 0.0
        self.book_view.update()
        self._book_show_editor()

    def _f3_search_changed(self, text):
        if not self._f3_search_active:
            return
        q = text.strip().lower()
        if not q:
            filtered = [l for l in self.book_ring.lines if l != '.'] or ['.']
        else:
            filtered = [l for l in self.book_ring.lines if l != '.' and q in l.lower()] or ['.']
        self._f3_display_ring = LineRing(filtered)
        self.book_view.ring = self._f3_display_ring
        self.book_view._offset = 0.0
        self._f3_search_show_center()

    def _f3_search_confirm(self):
        """Enter: load the highlighted file and close search."""
        if not self._f3_search_active:
            return
        matched_display = self._f3_display_ring.current() if self._f3_display_ring else None
        self._f3_search_active = False
        self._f3_search_bar.hide()
        self._f3_display_ring = None
        self._f3_search_saved = None
        if matched_display and matched_display != '.':
            for i, l in enumerate(self.book_ring.lines):
                if l == matched_display:
                    self.book_ring.index = i
                    break
        self.book_view.search_mode = False
        self.book_view.search_highlight_center = False
        self.book_view.ring = self.book_ring
        self.book_view._offset = 0.0
        self.book_view.update()
        # Sync editor text NOW so switch_to_view's _book_try_rename sees no change
        if matched_display and matched_display != '.':
            self.book_view.editor.setText(matched_display)
            self.book_view.editor.setReadOnly(False)
        fname = self._library_current_fname()
        if fname:
            fpath = self._library_path_cache.get(fname)
            if fpath and os.path.isfile(fpath):
                self.f2_file = fpath
                self.current_file_path = fpath
                self.load_doc_lines()
                self.switch_to_view(1)
                return
        self._book_show_editor()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FullscreenCircleApp()
    sys.exit(app.exec())
