# new_interface.py - App principal con sistema de 2 vistas + vault (F3)
import os
import sys
import json
import random
import datetime
import shutil
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QFileDialog
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtGui import QFont, QCursor, QShortcut, QKeySequence
from PyQt6.QtCore import Qt, qInstallMessageHandler, QtMsgType

from files import setup_file_handling, void_line
from controls import setup_controls
from line_ring import LineRing
from circular_view import CircularView
from widgets import CustomLineEdit
from views import NormalView


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
    "keybindings": {
        "view_f1": "F1",
        "view_f2": "F2",
        "view_f3": "F3",
        "view_f4": "F4",
        "view_f5": "F5",
        "view_f6": "F6",
        "view_f7": "F7",
        "view_f8": "F8",
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
        "screenshot": "F12",
        "open_screenshots": "Ctrl+F12",
        "print_doc": "Ctrl+P",
        "export_doc": "Ctrl+S",
        "reformat_file": "Ctrl+Shift+F",
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
    'F7': Qt.Key.Key_F7, 'F8': Qt.Key.Key_F8, 'F12': Qt.Key.Key_F12,
    'PageUp': Qt.Key.Key_PageUp, 'PageDown': Qt.Key.Key_PageDown,
    '0': Qt.Key.Key_0, '9': Qt.Key.Key_9, 'R': Qt.Key.Key_R, 'P': Qt.Key.Key_P,
    'F': Qt.Key.Key_F, 'B': Qt.Key.Key_B,
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
        self.book_files = []    # ordered list of .txt filenames in book_dir
        self.book_ring = LineRing()

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

        # View stack
        self.stack = QStackedWidget()
        self.normal_view = NormalView(self)
        self.circular_view = None   # F2: CircularView over doc ring
        self.book_view = None       # F3: CircularView over book_ring (filenames)
        self.vault_view = None      # F4: Oracle from I/
        self.transform_view = None  # F5: Transform — editable O/ line → I/
        self.o_reader_view = None   # F6: Reader — circular view of O/ book
        self.o_browser_view = None  # F7: Book browser for O/
        self.oracle_o_view = None   # F8: Oracle from O/
        self.stack.addWidget(self.normal_view)

        # File setup — active file is configurable (defaults to book_dir/0.txt)
        self.current_file_path = active_file
        self.void_file_path = os.path.join(self.void_dir, '0.txt')  # fallback for file commands
        os.makedirs(self.book_dir, exist_ok=True)
        if not os.path.exists(self.current_file_path):
            open(self.current_file_path, 'w', encoding='utf-8').close()

        self.scan_txt_files()
        setup_file_handling(self)
        setup_controls(self)

        self.load_doc_lines()
        self.load_vault_lines()
        self._load_book_order()

        # Void key connection
        self._print_void_mode_status()
        self._void_enter_connection = None
        self._void_space_connection = None
        self._connect_void_key()

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
        self.void_file_path = os.path.join(self.void_dir, '0.txt')
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
        try:
            with open(doc_path, 'r', encoding='utf-8') as f:
                for raw in f:
                    s = raw.strip()
                    if s:
                        lines.append(s)
        except Exception as e:
            print(f"⚠️ Error reading {os.path.basename(doc_path)}: {e}")
        # Ensure a leading dot so the last paragraph and first paragraph
        # are always separated when wrapping around the ring.
        if lines and lines[0] != '.':
            lines.insert(0, '.')
        self.line_ring = LineRing(lines or ["."])
        self._restore_last_line()
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
        void_line(self)
        # Reload doc ring and position near the just-written line
        self.load_doc_lines()
        if hasattr(self, 'last_inserted_index') and self.last_inserted_index is not None:
            self.line_ring.index = min(self.last_inserted_index, len(self.line_ring.lines) - 1)

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
        # F3 → F2: activate the highlighted file (same as pressing Enter)
        if self.current_view == 2 and view_index == 1:
            if not self._book_try_rename():
                return
            if self.book_ring.current() != '.':
                fidx = self._book_file_idx()
                if fidx < len(self.book_files):
                    self._set_active_file(os.path.join(self.book_dir, self.book_files[fidx]))
        # Save last line when leaving F2
        if self.current_view == 1:
            self._save_last_line()
        # Cancel staged vault line if user navigates away without voiding
        if view_index == 3:
            self._pending_vault_remove = False
        old_view = self.current_view
        self.current_view = view_index
        print(f"📍 F{old_view+1} → F{view_index+1} | Index: {self.line_ring.index} | Line: '{self.line_ring.current()}'")

        if view_index == 0:  # F1 — write/navigate active file
            if self.circular_view:
                self.circular_view.edit_mode = False
                self.circular_view.editor.hide()
            if self.book_view:
                self.book_view.edit_mode = False
                self.book_view.editor.hide()
            self.stack.setCurrentWidget(self.normal_view)
            self.entry.show()
            self.entry.raise_()
            # Anchor F1 to the line currently selected in F2
            if old_view == 1 and self.line_ring.current() != '.':
                self.current_active_line_index = self.line_ring.index
                self.last_inserted_index = self.line_ring.index
            self.entry.setText(self.line_ring.current())
            self.entry.setCursorPosition(len(self.entry.text()))
            self.entry.setFocus()

        elif view_index == 1:  # F2 — circular doc view
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
                self.stack.addWidget(self.circular_view)
            else:
                self.circular_view.ring = self.line_ring
                self.circular_view._offset = 0.0

            self.stack.setCurrentWidget(self.circular_view)
            self.entry.hide()
            self.circular_view.update()
            self._doc_show_editor()

        elif view_index == 2:  # F3 — book browser
            self._load_book_order()
            if not self.book_view:
                self.book_view = CircularView(self.book_ring, self)
                self.book_view.zero_marker = True
                self.book_view.setFont(self._app_font)
                self.book_view.editor.returnPressed.disconnect()
                self.book_view.editor.returnPressed.connect(self._book_confirm_edit)
                self.book_view.editor.splitAtCursor.connect(lambda pos: self._book_confirm_edit())
                self.book_view.editor.upPressed.connect(lambda: self._book_navigate(-1))
                self.book_view.editor.downPressed.connect(lambda: self._book_navigate(1))
                self.stack.addWidget(self.book_view)
            else:
                self.book_view.ring = self.book_ring
                self.book_view._offset = 0.0
            # Sync cursor to active file (ring layout: ['.', name0, '.', name1, ...])
            active_fname = os.path.basename(self.current_file_path)
            if active_fname in self.book_files:
                self.book_ring.index = self.book_files.index(active_fname) * 2 + 1
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

        elif view_index == 4:  # F5 — transform: editable O/ line → append to I/
            if not self.transform_view:
                self.transform_view = CircularView(self.o_reader_ring, self)
                self.transform_view.setFont(self._app_font)
                self.transform_view.editor.returnPressed.disconnect()
                self.transform_view.editor.returnPressed.connect(self._transform_confirm)
                self.transform_view.editor.upPressed.connect(lambda: self._transform_navigate(-1))
                self.transform_view.editor.downPressed.connect(lambda: self._transform_navigate(1))
                self.stack.addWidget(self.transform_view)
            else:
                self.transform_view.ring = self.o_reader_ring
                self.transform_view._offset = 0.0
            self.stack.setCurrentWidget(self.transform_view)
            self.entry.hide()
            self.transform_view.update()
            self._transform_show_editor()

        elif view_index == 5:  # F6 — reader: circular view of O/ book (read-only)
            if not self.o_reader_view:
                self.o_reader_view = CircularView(self.o_reader_ring, self)
                self.o_reader_view.setFont(self._app_font)
                self.o_reader_view.editor.returnPressed.disconnect()
                self.o_reader_view.editor.returnPressed.connect(self._reader_fork_to_transform)
                self.o_reader_view.editor.upPressed.connect(lambda: self._reader_navigate(-1))
                self.o_reader_view.editor.downPressed.connect(lambda: self._reader_navigate(1))
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
            if not self.o_browser_view:
                self.o_browser_view = CircularView(self.o_browser_ring, self)
                self.o_browser_view.setFont(self._app_font)
                self.o_browser_view.editor.returnPressed.disconnect()
                self.o_browser_view.editor.returnPressed.connect(self._o_browser_open)
                self.o_browser_view.editor.upPressed.connect(lambda: self._o_browser_navigate(-1))
                self.o_browser_view.editor.downPressed.connect(lambda: self._o_browser_navigate(1))
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

    def auto_save_circular(self):
        """Save doc ring state to active file (atomic write)."""
        import tempfile
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

    # ── Reformat ─────────────────────────────────────────────────────────────

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
            try:
                with open(doc_path, 'w', encoding='utf-8') as f:
                    for line in result:
                        f.write(line + '\n')
            except Exception as e:
                print(f"❌ Reformat write error: {e}")
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

        try:
            with open(doc_path, 'w', encoding='utf-8') as f:
                for line in result_lines:
                    f.write(line + '\n')
            print(f"✅ Reformatted: {len(result_lines)} lines → {doc_path}")
        except Exception as e:
            print(f"❌ Reformat write error: {e}")
            return

        # Reload into ring
        self.load_doc_lines()
        self._doc_show_editor()

    # ── Book order ────────────────────────────────────────────────────────────

    def _load_book_order(self):
        """Load ordered file list from _book_order.json, appending any unlisted files."""
        order_path = os.path.join(self.book_dir, '_book_order.json')
        try:
            actual = sorted(
                os.path.relpath(os.path.join(root, f), self.book_dir)
                for root, _, files in os.walk(self.book_dir)
                for f in files
                if f.lower().endswith('.txt') and f not in ('_book_order.json',)
            )
        except Exception:
            actual = []
        actual_set = set(actual)
        if os.path.exists(order_path):
            try:
                with open(order_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                ordered = [f for f in saved if f in actual_set]
                remaining = [f for f in actual if f not in set(ordered)]
                self.book_files = ordered + remaining
            except Exception:
                self.book_files = actual
        else:
            self.book_files = actual
        self._rebuild_book_ring()
        print(f"📚 Book: {len(self.book_files)} files in {os.path.basename(self.book_dir)}")

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

    def _save_book_order(self):
        order_path = os.path.join(self.book_dir, '_book_order.json')
        try:
            with open(order_path, 'w', encoding='utf-8') as f:
                json.dump(self.book_files, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Error saving book order: {e}")

    def _rebuild_book_ring(self):
        """Build book ring as: ['.', name1, '.', name2, ...] — dots are decorative."""
        display = [os.path.splitext(f)[0] for f in self.book_files]
        if not display:
            self.book_ring = LineRing(['.', '(empty)'])
        else:
            lines = []
            for name in display:
                lines.append('.')
                lines.append(name)
            self.book_ring = LineRing(lines)
            self.book_ring.index = 1  # start on first filename, not the dot
        if self.book_view:
            self.book_view.ring = self.book_ring
            self.book_view._offset = 0.0

    def _set_active_file(self, path):
        """Change active file (and book_dir if it changed), reload doc ring."""
        self.current_file_path = path
        new_book_dir = os.path.dirname(os.path.abspath(path))
        if new_book_dir != self.book_dir:
            self.book_dir = new_book_dir
            self.config['book_dir'] = new_book_dir
            self._load_book_order()
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
        self._set_active_file(path)
        self.switch_to_view(self.current_view)

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
        self._load_book_order()
        # If active file is outside the new book_dir, switch to first book file
        norm_path = os.path.normpath(path)
        norm_active = os.path.normpath(os.path.dirname(self.current_file_path))
        if norm_active != norm_path:
            if self.book_files:
                self._set_active_file(os.path.join(self.book_dir, self.book_files[0]))
            else:
                new_active = os.path.join(self.book_dir, '0.txt')
                open(new_active, 'a', encoding='utf-8').close()
                self._set_active_file(new_active)
                self._load_book_order()
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
        view.editor.setText(self.line_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.setReadOnly(self.line_ring.current() == '.')
        is_zero_dot = view.zero_marker and self.line_ring.index == 0
        self._apply_editor_style(view.editor, red=is_zero_dot)
        view.editor.show()
        view.editor.setFocus()
        view.update()

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
        self.circular_view.editor.setText(self.line_ring.current())
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
        """Enter in F2: focus mode on dot, go to F1 anchored on text line."""
        if self.line_ring.current() == '.' and not self._para_focus:
            self._enter_para_focus()
        else:
            # Switch to F1 empty, anchor insertions below current line
            idx = self.line_ring.index
            self._exit_para_focus() if self._para_focus else None
            self.current_active_line_index = None
            self.last_inserted_index = idx
            self.switch_to_view(0)
            self.entry.clear()

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

    # ── Book browser (F3) ─────────────────────────────────────────────────────

    def _book_show_editor(self):
        """Show F3 editor with current filename (no extension), cursor at start."""
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
        view.editor.setText(self.book_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.setReadOnly(False)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _book_file_idx(self):
        """Return the book_files index for the current book_ring position."""
        # Ring layout: ['.', name0, '.', name1, ...] — names are at odd indices
        return self.book_ring.index // 2

    def _book_navigate(self, delta):
        """Circular navigation through book files, skipping dots.
        Auto-saves title edits before moving. Enter activates the file."""
        self._book_try_rename()
        n = len(self.book_ring.lines)
        if n < 2:
            return
        new_idx = self.book_ring.index + delta * 2
        # Wrap circularly (ring layout: ['.', name0, '.', name1, ...] — names at odd indices)
        last_name_idx = n - 1 if n % 2 == 0 else n - 2
        if new_idx < 1:
            new_idx = last_name_idx
        elif new_idx > last_name_idx:
            new_idx = 1
        self.book_ring.index = new_idx
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_try_rename(self):
        """Rename the current book file if the editor text has changed.
        Returns False if the name is invalid (caller should abort navigation)."""
        if self.book_ring.current() == '.':
            return True
        fidx = self._book_file_idx()
        if fidx >= len(self.book_files):
            return True
        new_name = self.book_view.editor.text().strip()
        if not new_name or new_name.startswith('.'):
            # Restore original name so the ring stays consistent
            self.book_view.editor.setText(self.book_ring.current())
            return True  # invalid but non-fatal: just keep original
        old_fname = self.book_files[fidx]
        new_fname = new_name + '.txt'
        if new_fname != old_fname:
            old_path = os.path.join(self.book_dir, old_fname)
            new_path = os.path.join(self.book_dir, new_fname)
            try:
                os.rename(old_path, new_path)
                if self.current_file_path == old_path:
                    self.current_file_path = new_path
                    self.config['active_file'] = new_path
                    _save_config(self.config)
                self.book_files[fidx] = new_fname
                self.book_ring.lines[self.book_ring.index] = new_name
                self._save_book_order()
                print(f"📝 Renamed: {old_fname} → {new_fname}")
            except Exception as e:
                print(f"⚠️ Rename failed: {e}")
                return False
        return True

    def _book_confirm_edit(self):
        """Enter in F3: rename file if name changed, activate it, show content (F2)."""
        if not self._book_try_rename():
            return
        if self.book_ring.current() == '.':
            return
        fidx = self._book_file_idx()
        if fidx >= len(self.book_files):
            return
        self._set_active_file(os.path.join(self.book_dir, self.book_files[fidx]))
        self.switch_to_view(1)

    def _book_swap_up(self):
        """Alt+Up in F3: move current file one position earlier."""
        fidx = self._book_file_idx()
        if fidx <= 0:
            return
        # Swap in book_files
        self.book_files[fidx], self.book_files[fidx-1] = self.book_files[fidx-1], self.book_files[fidx]
        # Swap the name entries in the ring (odd positions: fidx*2+1)
        ri = self.book_ring.index          # current name position
        ri_prev = ri - 2                   # previous name position
        self.book_ring.lines[ri], self.book_ring.lines[ri_prev] = \
            self.book_ring.lines[ri_prev], self.book_ring.lines[ri]
        self.book_ring.index = ri_prev
        self._save_book_order()
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_swap_down(self):
        """Alt+Down in F3: move current file one position later."""
        fidx = self._book_file_idx()
        if fidx >= len(self.book_files) - 1:
            return
        self.book_files[fidx], self.book_files[fidx+1] = self.book_files[fidx+1], self.book_files[fidx]
        ri = self.book_ring.index
        ri_next = ri + 2
        self.book_ring.lines[ri], self.book_ring.lines[ri_next] = \
            self.book_ring.lines[ri_next], self.book_ring.lines[ri]
        self.book_ring.index = ri_next
        self._save_book_order()
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()

    def _book_rebase(self):
        """Ctrl+0 in F3: rotate book_files so selected file becomes first."""
        fidx = self._book_file_idx()
        if fidx == 0:
            return
        self.book_files = self.book_files[fidx:] + self.book_files[:fidx]
        self._rebuild_book_ring()
        self._save_book_order()
        self.book_view._offset = 0.0
        self.book_view.editor.setText(self.book_ring.current())
        self.book_view.editor.setCursorPosition(0)
        self.book_view.update()
        print(f"📚 Rebase: '{self.book_files[0]}' is now first")

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
        printable = [f for f in self.book_files if f != '0.txt']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = os.path.join(self.book_dir, fname)
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
        """Ctrl+S in F3: save all chapters as PDF, pre-named after the book folder."""
        book_name = os.path.basename(os.path.normpath(self.book_dir))
        default_path = os.path.join(self.book_dir, book_name + '.pdf')
        printer = self._printer_from_save_dialog(default_path)
        if printer is None:
            return
        printable = [f for f in self.book_files if f != '0.txt']
        html_parts = []
        for i, fname in enumerate(printable):
            fpath = os.path.join(self.book_dir, fname)
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
        view.editor.setCursorPosition(0)
        view.editor.show()
        view.editor.setFocus()
        view.update()

    def _oracle_o_navigate(self, delta):
        self._refresh_oracle_o()
        self.oracle_o_view._offset = 0.0
        self.oracle_o_view.editor.setText(self.oracle_o_ring.current())
        self.oracle_o_view.editor.setCursorPosition(0)
        self.oracle_o_view.update()

    def _oracle_o_confirm(self):
        view = self.oracle_o_view
        new_text = view.editor.text().strip()
        if not new_text:
            return
        insert_pos = self.line_ring.index + 1
        self.line_ring.lines.insert(insert_pos, new_text)
        self.line_ring.index = insert_pos
        self.auto_save_circular()
        self._refresh_oracle_o()
        view._offset = 0.0
        view.update()
        view.editor.setText(self.oracle_o_ring.current())
        view.editor.setCursorPosition(0)
        view.editor.setFocus()
        print(f"✅ OracleO→Doc[{insert_pos}]: '{new_text}'")

    # ── F7: O/ book browser ───────────────────────────────────────────────────

    def _load_o_browser(self):
        """Scan O/ recursively for .txt files and build browser ring."""
        files = []
        for root, _, fnames in os.walk(self.o_dir):
            for f in sorted(fnames):
                if f.lower().endswith('.txt') and f.lower() != '0.txt':
                    rel = os.path.relpath(os.path.join(root, f), self.o_dir)
                    files.append(rel)
        self.o_browser_files = sorted(files)
        entries = []
        for rel in self.o_browser_files:
            entries.extend(['.', rel])
        self.o_browser_ring = LineRing(entries or ['.'])
        self.o_browser_ring.index = 1 if len(self.o_browser_ring.lines) > 1 else 0
        if self.o_browser_view:
            self.o_browser_view.ring = self.o_browser_ring
            self.o_browser_view._offset = 0.0

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

    def _o_browser_open(self):
        """Open selected O/ file in F6 reader."""
        cur = self.o_browser_ring.current()
        if not cur or cur == '.':
            return
        fpath = os.path.join(self.o_dir, cur)
        if not os.path.exists(fpath):
            return
        self._load_o_reader(fpath)
        self.switch_to_view(5)

    # ── F6: O/ reader ─────────────────────────────────────────────────────────

    def _load_o_reader(self, fpath):
        """Load an O/ book into the reader ring."""
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                lines = [l.rstrip('\n') for l in f]
        except Exception as e:
            print(f"⚠️ Cannot open {fpath}: {e}")
            return
        if not lines or lines[0] != '.':
            lines.insert(0, '.')
        self.o_reader_ring = LineRing(lines)
        self.o_reader_file = fpath
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

    def _reader_navigate(self, delta):
        self.o_reader_ring.move(delta)
        while self.o_reader_ring.current() == '.':
            self.o_reader_ring.move(delta)
        self.o_reader_view._offset = 0.0
        cur = self.o_reader_ring.current()
        self.o_reader_view.editor.setText(cur)
        self.o_reader_view.editor.setCursorPosition(0)
        self.o_reader_view.update()

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
        os.startfile(screenshots_dir)

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
        """Ctrl+Delete / Ctrl+Backspace in F2: remove current line and append to 0.txt."""
        if os.path.basename(self.current_file_path).lower() == '0.txt':
            return
        lines = self.line_ring.lines
        n = len(lines)
        cur = self.line_ring.index
        if n <= 1:
            return
        line = lines[cur]
        new_lines = [l for i, l in enumerate(lines) if i != cur]
        new_index = min(cur, len(new_lines) - 1)

        zero_path = os.path.join(self.book_dir, '0.txt')
        try:
            os.makedirs(self.book_dir, exist_ok=True)
            with open(zero_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception as e:
            print(f"❌ Delete to 0.txt error: {e}")
            return

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

    def _reposition_entry(self):
        w = self.width()
        h = self.height()
        if w == 0 or h == 0:
            return
        entry_width = min(w, h) - 90
        entry_height = self.entry.sizeHint().height()
        self.entry.setFixedWidth(entry_width)
        self.entry.move(w // 2 - entry_width // 2, h // 2 - entry_height // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_entry()

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
            self.entry.setFocus()
        elif self.current_view == 1 and self.circular_view:
            self.circular_view.editor.setFocus()
        elif self.current_view == 2 and self.book_view:
            self.book_view.editor.setFocus()
        elif self.current_view == 3 and self.vault_view:
            self.vault_view.editor.setFocus()

    # ── Key routing ───────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        # Global: view switching
        if self._matches(key, mods, 'view_f1'):
            self.switch_to_view(0); event.accept(); return
        if self._matches(key, mods, 'view_f2'):
            self.switch_to_view(1); event.accept(); return
        if self._matches(key, mods, 'view_f3'):
            self.switch_to_view(2); event.accept(); return
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

        # View-specific
        if self.current_view == 0:
            self._handle_f1_keys(key, mods)
        elif self.current_view == 1:
            self._handle_f2_keys(key, mods, event)
        elif self.current_view == 2:
            self._handle_f3_keys(key, mods, event)
        elif self.current_view == 3:
            self._handle_f4_keys(key, mods, event)
        elif self.current_view in (4, 5, 6, 7):
            if key == Qt.Key.Key_Escape:
                self.switch_to_view(0); event.accept()
            elif self._matches(key, mods, 'quit'):
                self.close(); event.accept()

    def _handle_f1_keys(self, key, mods):
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
            self.reformat_active_file()
            event.accept()
        elif (mods & Qt.KeyboardModifier.ControlModifier) and key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            editor = self.circular_view.editor
            at_start = editor.cursorPosition() == 0
            at_end = editor.cursorPosition() == len(editor.text())
            if (key == Qt.Key.Key_Delete and at_start) or (key == Qt.Key.Key_Backspace and at_end):
                self._delete_line_to_zero()
                event.accept()
        elif key == Qt.Key.Key_Escape:
            if self._para_focus:
                self._exit_para_focus()
            else:
                self.switch_to_view(0)

    def _handle_f3_keys(self, key, mods, event):
        # Up/Down/Enter handled by book_view.editor signals.
        if key == Qt.Key.Key_Escape:
            self.switch_to_view(0)
        elif self._matches(key, mods, 'swap_up'):
            self._book_swap_up(); event.accept()
        elif self._matches(key, mods, 'swap_down'):
            self._book_swap_down(); event.accept()
        elif self._matches(key, mods, 'rebase'):
            self._book_rebase(); event.accept()
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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FullscreenCircleApp()
    sys.exit(app.exec())
