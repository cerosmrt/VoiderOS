# new_interface.py - App principal con sistema de 2 vistas + vault (F3)
import os
import subprocess
import sys

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QFileDialog, QLineEdit, QTextBrowser
from PyQt6.QtGui import QFont, QCursor, QShortcut, QKeySequence, QColor
from PyQt6.QtCore import Qt, QTimer, QEvent

import app_config as _app_config
from app_config import (
    CONFIG_PATH, DEFAULT_CONFIG, _KEY_MAP, _MOD_MAP,
    _parse_keybinding, _clean_book_title, _qt_msg_handler,
    _load_config_from, _save_config_to,
)


# Thin wrappers over the shared implementation, bound to new_interface.CONFIG_PATH
# so tests can patch this module's path (see tests/conftest.py). The committed
# config and the git-ignored runtime state (state.json) split lives in app_config.
def _load_config():
    return _load_config_from(CONFIG_PATH)


def _save_config(config):
    _save_config_to(CONFIG_PATH, config)
from io_mixin import IoMixin
from f1_mixin import F1Mixin
from f2_mixin import F2Mixin
from f3_mixin import F3Mixin
from f4_mixin import F4Mixin
from f5678_mixin import F5678Mixin
from tts_mixin import TtsMixin
from key_router_mixin import KeyRouterMixin
from f5_reorder_mixin import F5ReorderMixin

from files import setup_file_handling, void_line
from ipc import VoiderIPC
from controls import setup_controls
from line_ring import LineRing
from circular_view import CircularView
from widgets import CustomLineEdit
from views import NormalView, EdgeFade
from metronome_view import MetronomeView
from fx_panel import FxPanel
from help_overlay import HelpOverlay
from settings_panel import SettingsPanel
from lock_screen import LockScreen
from reorder_view import ReorderView


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



class FullscreenCircleApp(QMainWindow, IoMixin, F1Mixin, F2Mixin, F3Mixin,
                          F4Mixin, F5ReorderMixin, F5678Mixin, TtsMixin, KeyRouterMixin):
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

        # Resolve void_dir: config → auto-create next to config.json (no
        # forced dialog — a compiled .exe should be double-click and go). The
        # manual picker (Ctrl+F4 / change_void_directory) is still there for
        # changing it later; it's just not forced on first run any more.
        void_dir = self.config.get('void_dir', '')
        if not void_dir or not os.path.isdir(void_dir):
            void_dir = os.path.join(
                os.path.dirname(os.path.abspath(CONFIG_PATH)), 'void')
            os.makedirs(void_dir, exist_ok=True)
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

        # Los dos ejes de transparencia. Arrancan SIEMPRE opacos: la
        # transparencia es de la sesion, no del archivo. Antes se guardaban y
        # volvian como los dejaste, lo que ademas hacia que un 0 sobreviviera al
        # reinicio y Voider arrancara invisible.
        # Se aplican al final del __init__, cuando los widgets ya existen: el
        # alpha se pinta, no se le pide a la ventana, asi que hay que tener algo
        # que pintar.
        self.opacity = 1.0
        self.ink_opacity = 1.0
        self._setup_opacity_shortcuts()
        self.txt_files = []
        self.current_file_index = 0
        self.current_view = 0  # 0=F1, 1=F2, 2=F3(book), 3=F4(vault)
        self.use_spacebar_for_void = self.config.get('void_key', 'enter') == 'space'
        self._pending_vault_remove = False  # True when staging a vault line in F1
        self._para_focus = False            # True when in paragraph focus mode
        self._doc_picker_open = False       # el catalogo de capitulos en F2
        self._doc_picker_side = 'right'
        self._pick_include_self = False  # el panel de F2 lista el capitulo activo
        self._para_focus_content = []       # Ordered list of absolute ring indices for focused paragraph

        # Font / color from config
        _font_family = self.config.get('font_family', 'Consolas')
        _font_size = int(self.config.get('font_size', 11))
        _text_color = self.config.get('text_color', '#ffffff')
        self._app_font = QFont(_font_family, _font_size)

        # Window setup
        self.setWindowTitle("Voider")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        # Translucida de verdad: pide un visual con canal alfa. Sin esto el
        # rgba() que pintamos abajo se aplasta contra negro opaco y bajar la
        # opacidad del fondo no se ve.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: black; color: white;")

        # Entry (F1)
        self.entry = CustomLineEdit(self)
        # La capa que apaga el texto hacia el borde del circulo (F1 typewriter).
        # Se crea aca, al lado del entry, porque va justo encima de el.
        self._edge_fade = EdgeFade(self)
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
        # Typewriter mode (toggle, Ctrl+Shift+W; off by default → classic centred).
        # When on, right-alignment pins the caret at the entry's right edge, which
        # _reposition_entry places on the screen centre; text flows left.
        self._typewriter_mode = bool(self.config.get('typewriter_mode', False))
        self.entry.setAlignment(Qt.AlignmentFlag.AlignRight if self._typewriter_mode
                                else Qt.AlignmentFlag.AlignCenter)
        self.entry.setFocus()
        # Shift+Tab en F1: reciclar del working set, espejo del Tab que recicla
        # de I/. En F2 esto ya existia; en F1 nunca se habia implementado.
        self.entry.shiftTabPressed.connect(self._f1_recycle_ws_line)

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
        self._scratch_return = None   # backtick round-trip: {'path','view'} or None
        self._show_view_title = bool(self.config.get('show_view_title', False))
        self.book_view = None       # F3: CircularView over book_ring (filenames)
        self.book_concat_view = None          # view 9: read-only concatenated group
        self.book_concat_ring = LineRing(['.'])
        self._book_concat_header_indices = set()
        self._book_pending_new = False        # True while user names a new F3 entry
        self._book_pending_merge = False      # True while user names a book to merge
        # Remembered F3 cursor (for re-entry + reopen). None → resolve to the active
        # chapter, never the top. Seeded from config so it survives a restart.
        self._book_last_index = self.config.get('last_book_index')
        self._book_last_entry = self.config.get('last_book_entry')
        # Search state — display rings are separate from real rings (never mutated)
        # Undo / redo of text content (Ctrl+Z / Ctrl+Shift+Z in F1/F2/F5)
        from undo_manager import UndoManager
        self._undo = UndoManager()
        self._undo_last = {}        # path -> last written line list
        self._undo_applying = False
        self._undo_txn = None
        # Cursor position -> _last_lines.json every couple of seconds when it moved,
        # so a killed window (SIGHUP, no closeEvent) still remembers where you were.
        self._pos_saved = None
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self._position_autosave_tick)
        self._pos_timer.start(2000)
        QApplication.instance().installEventFilter(self)
        # Auto-hide the mouse pointer while typing; show it (as a transparent white
        # ring, so you can see what's behind) on any mouse activity.
        from cursor_autohide import CursorAutohide, make_ring_cursor
        self._cursor_autohide = CursorAutohide(
            QApplication.instance(), visible_cursor=make_ring_cursor(), hidden=True)
        self._f2_search_active = False
        self._f2_search_saved = None   # saved cursor index before search
        self._f2_display_ring = None   # temp ring shown during search
        self._f3_search_active = False
        self._f3_search_saved = None   # saved cursor index before search
        self._f3_display_ring = None   # temp ring shown during search
        self.reading_view = None    # F4: Reading render of current document
        self._f4_carousel_view = False   # F4: book (A5) vs carousel-ratio preview
        self.vault_view = None      # (Oracle, no longer on F4)
        self.settings_view = None   # F10: Settings panel
        self.transform_view = None  # F5: Transform — editable O/ line → I/
        self.reorder_view = None    # F5: linear paragraph reorder view
        self._f5_para_idx = 0       # F5 current-paragraph cursor
        self._f5_picker_open = False  # True while the in-view chapter picker is open
        self._f5_pick_filter = ''     # type-to-filter text in the picker
        self._f5_pick_match_idx = 0   # highlighted match in the picker
        self.o_reader_view = None   # F6: Reader — circular view of O/ book
        self.o_browser_view = None  # F7: Book browser for O/
        self.oracle_o_view = None   # F8: Oracle from O/
        self.metronome_view = None  # F9: Metronome/tempo (retired)
        self.editor_view = None     # F9: normal prose editor (QPlainTextEdit)
        self._help_overlay = None   # F11: Help/instructions
        self._lock_screen = None    # Esc: lock screen overlay
        self.stack.addWidget(self.normal_view)

        # File setup — F1 is always 0.txt; F2 follows F3 selection
        self.f1_file = os.path.join(self.void_dir, 'I', '0.txt')
        self._trash_file = os.path.join(self.void_dir, 'I', 'trash.txt')
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

        self._ipc = VoiderIPC(self)
        self._ipc.file_saved_by_other.connect(self._on_file_saved_by_other)

        self.init_ui()
        self._restore_startup_view()
        self.entry.clear()
        # Recien aca: la transparencia se pinta, asi que necesita las vistas
        # armadas. Ademas le dice a Hyprland que no vuelva a atenuar por su lado.
        self._apply_opacity(self.opacity)

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
        self._trash_file = os.path.join(new_dir, 'I', 'trash.txt')
        self.void_file_path = self.f1_file
        self.config['void_dir'] = new_dir
        _save_config(self.config)
        os.makedirs(self.void_dir, exist_ok=True)

        self.scan_txt_files()
        self.load_vault_lines()
        self.switch_to_view(self.current_view)
        print(f"📁 Void dir changed to: {new_dir}")

    def _on_file_saved_by_other(self, path: str):
        ap = os.path.abspath(path)
        if ap == os.path.abspath(self.current_file_path):
            self.load_doc_lines()
            if self.circular_view:
                self.circular_view.update()
            return
        # Another instance rewrote the library index (reorder/rename/delete/merge/
        # split). Reload it so this instance's F3 doesn't clobber those changes.
        if ap == os.path.abspath(self._library_path()):
            self._reload_library_from_other()

    def _reload_library_from_other(self):
        """Re-read I.txt after another instance changed it, preserving the current
        selection by name. Deferred while this instance is mid-edit in F3 (naming a
        new entry / merge, or a dirty rename) so we don't stomp unsaved intent."""
        if getattr(self, '_book_pending_new', False) or getattr(self, '_book_pending_merge', False):
            return
        if self.current_view == 2 and self._f3_mid_edit():
            return
        sel = None
        if self._library_lines and 0 <= self.book_ring.index < len(self._library_lines):
            sel = self._library_lines[self.book_ring.index]
        self._load_library()
        if sel is not None:
            try:
                self.book_ring.index = self._library_lines.index(sel)
            except ValueError:
                self.book_ring.index = min(self.book_ring.index,
                                           len(self.book_ring.lines) - 1)
        if self.current_view == 2 and self.book_view:
            self.book_view.ring = self.book_ring
            self.book_view._offset = 0.0
            self.book_view.update()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _apply_settings(self, settings):
        """Apply settings from F10 panel: update config, font, and repaint all views."""
        self.config.update(settings)
        _save_config(self.config)
        fam = settings['font_family']
        sz = int(settings['font_size'])
        self._app_font = QFont(fam, sz)
        for view in [self.circular_view, self.book_view, self.o_reader_view,
                     self.o_browser_view, self.oracle_o_view, self.metronome_view,
                     self.book_concat_view, self.scratch_view]:
            if view:
                view.setFont(self._app_font)
                # The inline editor is a child QLineEdit with its own font; it does
                # not inherit, so update it explicitly or the line you're on keeps
                # the old size.
                editor = getattr(view, 'editor', None)
                if editor is not None:
                    editor.setFont(self._app_font)
        if self.entry:
            self.entry.setFont(self._app_font)
        self.switch_to_view(self._prev_view if hasattr(self, '_prev_view') else 0)

    def _apply_editor_style(self, editor, red=False):
        """La hoja de estilo del editor del CircularView: blanca, o roja sobre el
        marcador ø.

        El fondo va TRANSPARENTE. Antes era negro opaco y era el unico rectangulo
        que no se transparentaba cuando bajabas el fondo — un cuadrado negro
        justo en el medio. El fondo lo pinta la ventana, una sola vez.

        Y el color sale del eje TINTA, para que Ctrl+Shift+± atenue tambien lo
        que estas escribiendo. El rojo del ø tambien es tinta: es un marcador,
        no decoracion, asi que se atenua con el resto.
        """
        # Se acota aca en vez de llamar a _clamp_ink para no atarse a la clase:
        # esto tiene que andar sobre cualquier cosa que tenga ink_opacity.
        ink = max(0.0, min(1.0, getattr(self, 'ink_opacity', 1.0)))
        a = f"{ink:.3f}"
        rgb = "255, 40, 40" if red else "255, 255, 255"
        # Se recuerda para poder re-aplicarla cuando cambia la tinta sin tener
        # que recalcular aca si estamos sobre el marcador.
        editor._voider_red = red
        editor.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: rgba({rgb}, {a});
                border: none;
                qproperty-alignment: AlignCenter;
                selection-background-color: rgba({rgb}, {a});
                selection-color: rgba(0, 0, 0, {a});
            }}
        """)

    # ── Views ─────────────────────────────────────────────────────────────────

    def _restore_startup_view(self):
        """Resume where the user left off: the last restorable view (F1–F4), the
        active file, and its saved line position. Views outside F1–F4 (F5, O/
        readers, settings) fall back to F1."""
        view = self.config.get('last_view', 0)
        if view not in (0, 1, 2, 3):
            view = 0
        # F1/F2/F4 all follow the active file — point at it and restore its line
        # (load_doc_lines calls _restore_last_line). F3 syncs to it on its own.
        if view in (0, 1, 3) and self.f2_file and os.path.isfile(self.f2_file):
            self.current_file_path = self.f2_file
            self.load_doc_lines()
        self.switch_to_view(view)

    def switch_to_view(self, view_index):
        # La capa del circulo de F1 se esconde SIEMPRE al cambiar de vista. Es de
        # F1 y de nadie mas: si queda visible, recorta F2/F3/F4 a un circulo y se
        # come el texto. La muestra de nuevo _reposition_entry al entrar a F1.
        fade = getattr(self, "_edge_fade", None)
        if fade is not None and view_index != 0:
            fade.hide()
        # Close search bars when leaving their view
        if self._f2_search_active and view_index != 1:
            self._close_f2_search(restore=True)
        if self._f3_search_active and view_index != 2:
            self._close_f3_search(restore=True)
        # Leaving F3 saves a new entry that has a title (drops it only if empty).
        if (self.current_view == 2 and view_index != 2
                and getattr(self, '_book_pending_new', False)):
            self._book_settle_pending()
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
        # Leaving the F9 prose editor: commit the edit back to the active file.
        if old_view == 8 and view_index != 8:
            self._editor_save()
        # Remember which F3 entry we were on, so re-entering F3 returns to the same
        # one (e.g. a specific '0' portal) instead of snapping to the first match.
        if old_view == 2 and self.book_ring.lines:
            # Leaving F3 marks the highlighted chapter as the active file (once,
            # on exit — not per highlight), so F4/F2/F1 and re-entry all agree.
            self._book_activate_current()
            idx = self.book_ring.index
            self._book_last_index = idx
            self._book_last_entry = (self._library_lines[idx]
                                     if 0 <= idx < len(self._library_lines) else None)
            # Persist the F3 cursor so it survives a restart (like last_view).
            self.config['last_book_index'] = self._book_last_index
            self.config['last_book_entry'] = self._book_last_entry
            _save_config(self.config)
        self.current_view = view_index
        # Remember the last restorable view (F1–F4) so startup resumes here.
        if view_index in (0, 1, 2, 3) and self.config.get('last_view') != view_index:
            self.config['last_view'] = view_index
            _save_config(self.config)
        print(f"📍 F{old_view+1} → F{view_index+1} | Index: {self.line_ring.index} | Line: '{self.line_ring.current()}'")

        if view_index == 0:  # F1 — focus writing on the ACTIVE file
            # Fork only from F6 (O/ reader) — F2 entry is handled by _doc_confirm_edit
            fork_line = None
            if old_view == 5:
                cur = self.o_reader_ring.current()
                if cur and cur != '.':
                    fork_line = cur
            # F1 follows whatever file is active (no longer forced to 0.txt).
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
            self._reposition_entry()   # y la capa del degradado encima
            if fork_line:
                # Forked O/ line: pre-fill so you can edit and commit it
                self.entry.setText(fork_line)
                self.entry.selectAll()
            else:
                # Mirror the current line of the active file (blank for a '.')
                self._f1_show_current()
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
                # Alt+flecha no va derecho a mover la palabra: _doc_alt_arrow
                # decide segun donde este el cursor (punto → catalogo de
                # capitulos; linea → la palabra, como siempre).
                self.circular_view.editor.wordSwapLeft.connect(lambda: self._doc_alt_arrow(-1))
                self.circular_view.editor.wordSwapRight.connect(lambda: self._doc_alt_arrow(1))
                self.circular_view.editor.sendLeft.connect(lambda: self._doc_open_picker('left'))
                self.circular_view.editor.sendRight.connect(lambda: self._doc_open_picker('right'))
                self.circular_view.editor.deleteLine.connect(self._delete_line_to_trash)
                self.circular_view.editor.deleteAtEnd.connect(self._doc_join_next)
                self.circular_view.editor.tabPressed.connect(self._doc_tab)
                self.circular_view.editor.altTabPressed.connect(self._doc_insert_ws_line)
                self.circular_view.editor.copyContext.connect(self._smart_copy)
                self.circular_view.editor.home_end_doc = True
                self.circular_view.editor.homePressed.connect(self._doc_jump_start)
                self.circular_view.editor.endPressed.connect(self._doc_jump_end)
                self.stack.addWidget(self.circular_view)
            else:
                self.circular_view.ring = self.line_ring
                self.circular_view._offset = 0.0

            # Pinned title (toggle, Ctrl+Shift+T) — F2 shows the active file name.
            self.circular_view.show_title = self._show_view_title
            self.circular_view.title_text = self._active_file_title()
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
                self.book_view.editor.splitAtCursor.connect(lambda pos: self._book_enter_at_end())
                self.book_view.editor.upPressed.connect(lambda: self._book_navigate(-1))
                self.book_view.editor.downPressed.connect(lambda: self._book_navigate(1))
                self.book_view.editor.dotPressed.connect(self._book_insert_separator)
                self.book_view.editor.shiftReturnPressed.connect(self._book_new_entry)
                # Ctrl+Enter crea tambien, sin mirar el cursor — asi funciona
                # parado en el portal 0, donde el renglon es de solo lectura.
                self.book_view.editor.ctrlReturnPressed.connect(self._book_new_entry)
                self.book_view.editor.ctrlDeletePressed.connect(self._book_send_to_zero)
                self.book_view.editor.copyContext.connect(self._smart_copy)
                self.book_view.editor.tabPressed.connect(self._book_tab)
                self.book_view.editor.intercept_period = True
                self.book_view.editor.home_end_doc = True
                self.book_view.editor.homePressed.connect(self._book_jump_start)
                self.book_view.editor.endPressed.connect(self._book_jump_end)
                self.stack.addWidget(self.book_view)
            else:
                self.book_view.ring = self.book_ring
                self.book_view._offset = 0.0
            # Sync cursor to the active F2 file (including 0.txt). If the entry we
            # last sat on still points at that same file (e.g. the specific '0'
            # portal we used), return to it instead of snapping to the first match —
            # so multiple '0' portals are each individually reachable.
            # Return to the remembered entry (by exact index, then by name so it
            # survives reordering), else the active file's row, else the top — never
            # snapping to index 0 on reopen. See _resolve_f3_index.
            active_fname = os.path.basename(self.f2_file)
            self.book_ring.index = min(self._resolve_f3_index(active_fname),
                                       len(self.book_ring.lines) - 1)
            self.stack.setCurrentWidget(self.book_view)
            self.entry.hide()
            self.book_view.update()
            self._book_show_editor()

        elif view_index == 3:  # F4 — paginated reading view (book pages)
            if not self.reading_view:
                from reading_page import ReadingPageView
                self.reading_view = ReadingPageView(self)
                self.stack.addWidget(self.reading_view)
            self._reading_refresh()
            self.stack.setCurrentWidget(self.reading_view)
            self.entry.hide()
            self.reading_view.setFocus()

        elif view_index == 4:  # F5 — linear paragraph reorder over the active file
            if not self.reorder_view:
                self.reorder_view = ReorderView(self)
                self.reorder_view.setFont(self._app_font)
                self.stack.addWidget(self.reorder_view)
            # Follow the same active file as F2 (usually a merged doc).
            if self.current_file_path != self.f2_file:
                self.current_file_path = self.f2_file
                self.load_doc_lines()
            self.stack.setCurrentWidget(self.reorder_view)
            self.reorder_view.setGeometry(self.stack.rect())
            self.reorder_view.setFocus()
            self.entry.hide()
            self._f5_enter()

        elif view_index == 5:  # F6 — reader: circular view of O/ book (read-only)
            if not self.o_reader_view:
                self.o_reader_view = CircularView(self.o_reader_ring, self)
                self.o_reader_view.setFont(self._app_font)
                self.o_reader_view.editor.returnPressed.disconnect()
                # Enter parte la linea, siempre. Para salir del lector esta F1,
                # como se sale de cualquier otra vista.
                self.o_reader_view.editor.returnPressed.connect(
                    lambda: self._reader_split_line(0))
                self.o_reader_view.editor.splitAtCursor.connect(self._reader_split_line)
                self.o_reader_view.editor.backspaceAtStart.connect(self._reader_join_prev)
                self.o_reader_view.editor.deleteAtEnd.connect(self._reader_join_next)
                self.o_reader_view.editor.copyContext.connect(self._reader_smart_copy)
                self.o_reader_view.editor.wordSwapLeft.connect(
                    lambda: self._swap_words(-1, editor=self.o_reader_view.editor,
                                             ring=self.o_reader_ring,
                                             save=self._reader_save))
                self.o_reader_view.editor.wordSwapRight.connect(
                    lambda: self._swap_words(1, editor=self.o_reader_view.editor,
                                             ring=self.o_reader_ring,
                                             save=self._reader_save))
                self.o_reader_view.editor.upPressed.connect(lambda: self._reader_navigate(-1))
                self.o_reader_view.editor.downPressed.connect(lambda: self._reader_navigate(1))
                self.o_reader_view.editor.tabPressed.connect(self._reader_random_line)
                # Los libros de O/ se editan: cada tecla va al libro, y
                # Ctrl+Delete saca la linea y la deja en 0.txt.
                self.o_reader_view.editor.textEdited.connect(self._reader_live_save)
                self.o_reader_view.editor.deleteLine.connect(self._reader_harvest_line)
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

        elif view_index == 8:  # F9 — normal prose editor of the active file
            from PyQt6.QtWidgets import QPlainTextEdit
            from reading_page import lines_to_paragraphs
            if not self.editor_view:
                self.editor_view = QPlainTextEdit(self)
                self.editor_view.setStyleSheet(
                    "QPlainTextEdit { background:#000000; color:#dddddd; "
                    "border:none; selection-background-color:#444444; }")
                from widgets import hide_scrollbars
                hide_scrollbars(self.editor_view)   # no visible scroll bar in F9
                self.stack.addWidget(self.editor_view)
            # Match the rest of the shell: same app font as F1/F2/F3, with
            # comfortable margins that scale with the window width.
            self.editor_view.setFont(self._app_font)
            hmarg = max(60, int(self.width() * 0.12))
            self.editor_view.setViewportMargins(hmarg, 44, hmarg, 44)
            lines = self._reading_file_lines(self.current_file_path)
            self.editor_view.setPlainText('\n\n'.join(lines_to_paragraphs(lines)))
            self.editor_view.document().setModified(False)
            # Land on the same paragraph F1/F2/F5 were on, not always the top.
            from PyQt6.QtGui import QTextCursor
            cursor = self.editor_view.textCursor()
            cursor.setPosition(self._f9_entry_offset(lines, self.line_ring.index))
            self.editor_view.setTextCursor(cursor)
            self.editor_view.ensureCursorVisible()
            self.stack.setCurrentWidget(self.editor_view)
            self.entry.hide()
            self.editor_view.setFocus()

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

        elif view_index == 10:  # F10 — settings panel
            if not self.settings_view:
                self.settings_view = SettingsPanel(self)
                self.settings_view.applied.connect(self._apply_settings)
                self.stack.addWidget(self.settings_view)
            self.settings_view.load(self.config)
            self.stack.setCurrentWidget(self.settings_view)
            self.entry.hide()

        self._tts_on_view(view_index)

    # ── UI init ───────────────────────────────────────────────────────────────

    def init_ui(self):
        self.showFullScreen()
        self.setCentralWidget(self.stack)
        self._reposition_entry()

        # FxPanel: in-app tuner for Hyprland visual effects (CRT/grain/B&W).
        # Self-contained — writes <tmp>/voider-fx and runs `voider-fx-update`.
        # Opened by a Hyprland keybind that drops a request file we poll for.
        self._fx_panel = FxPanel(self)
        self._fx_panel.setGeometry(self.rect())
        self._panel_poll = QTimer(self)
        self._panel_poll.timeout.connect(self._poll_fx_panel)
        self._panel_poll.start(100)

    def _poll_fx_panel(self):
        from platform_paths import tmp_file
        path = tmp_file('voider-fx-panel')
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

    @staticmethod
    def _entry_geometry(w, h, entry_h, typewriter):
        """(x, y, width) for the F1 entry. Typewriter mode: it spans from the
        circle's left edge to the screen centre, so the right-aligned caret sits on
        the centre and text flows left, clipped at the circle (nothing shows
        outside it). Classic mode: a wide, centred entry."""
        y = h // 2 - entry_h // 2
        if typewriter:
            radius = min(w, h) // 2 - 35        # same circle as NormalView
            width = max(1, radius)
            return w // 2 - width, y, width
        width = max(1, min(w, h) - 90)
        return w // 2 - width // 2, y, width

    def _clip_entry_to_circle(self, x, y, ew, eh, w, h):
        """Recortar el renglon de F1 al circulo, de verdad.

        Antes esto lo hacia EdgeFade pintando negro opaco por fuera del circulo:
        tapaba lo que sobresalia. Funcionaba mientras el fondo fuera negro solido
        — con el fondo transparente ese negro deja de tapar, y la letra grande
        vuelve a desparramarse. Una mascara si recorta: lo que queda afuera del
        circulo directamente no se dibuja, con cualquier opacidad.

        En F2/F3/F4 no hay circulo, asi que la mascara se saca.
        """
        from PyQt6.QtGui import QRegion
        if self.current_view != 0:
            self.entry.clearMask()
            return
        r = min(w, h) // 2 - EdgeFade.CIRCLE_INSET
        if r <= 0 or ew <= 0 or eh <= 0:
            self.entry.clearMask()
            return
        # El circulo, pasado a coordenadas del entry.
        cx, cy = w // 2 - x, h // 2 - y
        self.entry.setMask(QRegion(cx - r, cy - r, r * 2, r * 2,
                                   QRegion.RegionType.Ellipse))

    def _reposition_entry(self):
        w = self.width()
        h = self.height()
        if w == 0 or h == 0:
            return
        entry_height = self.entry.sizeHint().height()
        x, y, entry_width = self._entry_geometry(
            w, h, entry_height, getattr(self, '_typewriter_mode', False))
        self.entry.setFixedWidth(entry_width)
        self.entry.move(x, y)
        self._clip_entry_to_circle(x, y, entry_width, entry_height, w, h)
        # La capa del degradado se calza EXACTAMENTE sobre el renglon, y solo
        # tiene sentido en typewriter: en modo clasico el texto va centrado y no
        # corre hacia el borde, asi que no hay nada que apagar.
        fade = getattr(self, "_edge_fade", None)
        if fade is not None:
            typewriter = getattr(self, "_typewriter_mode", False)
            if self.current_view == 0:
                # La capa va SIEMPRE en F1, no solo en typewriter: ademas del
                # degradado es la que recorta el texto al circulo y redibuja el
                # trazo encima. Sin ella, en modo clasico la letra grande se
                # desparrama por toda la pantalla y el circulo desaparece detras.
                fade.setGeometry(0, 0, w, h)
                # El degradado direccional solo tiene sentido en typewriter: ahi
                # el caret esta fijo y la linea corre hacia el borde. En clasico
                # el texto va centrado, asi que se recorta pero no se apaga.
                if typewriter:
                    # Solo el tramo horizontal: el alto lo pone la capa, que
                    # cubre el circulo entero. Asi el tamano de fuente deja de
                    # importar — antes se pasaba el alto del renglon y los
                    # glifos altos se salian de esa caja sin apagarse.
                    fade.set_fade_span(x, entry_width)
                else:
                    fade.clear_fade()
                fade.show()
                fade.raise_()   # despues del entry, o quedaria debajo
            else:
                fade.hide()
        # Search bars sit near the bottom
        bar_width = min(w - 100, 800)
        bar_x = (w - bar_width) // 2
        bar_y = h - entry_height - 24
        self._f2_search_bar.setFixedWidth(bar_width)
        self._f2_search_bar.move(bar_x, bar_y)
        self._f3_search_bar.setFixedWidth(bar_width)
        self._f3_search_bar.move(bar_x, bar_y)

    def closeEvent(self, event):
        self._save_last_line()
        self._ws_save_position()
        self._save_working_set()
        super().closeEvent(event)

    def _position_autosave_tick(self):
        """Save the cursor position if (file, index) changed since the last save."""
        ring = getattr(self, 'line_ring', None)
        if ring is None or not getattr(self, 'current_file_path', None):
            return
        state = (self.current_file_path, ring.index)
        if state == getattr(self, '_pos_saved', None):
            return
        self._save_last_line()
        self._pos_saved = state

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_entry()
        if self._help_overlay:
            self._help_overlay.setGeometry(self.rect())
        if self._lock_screen:
            self._lock_screen.setGeometry(self.rect())
        if hasattr(self, '_fx_panel'):
            self._fx_panel.setGeometry(self.rect())
        if self.reorder_view:
            self.reorder_view.setGeometry(self.stack.rect())

    def leaveEvent(self, event):
        """Restore focus to the active editor when the mouse leaves the window."""
        super().leaveEvent(event)
        self._refocus_active_editor()

    # Los dos ejes bajan hasta 0: transparente del todo.
    #
    # Yo les habia puesto piso (25% el fondo, 20% la tinta) por miedo a que se
    # perdiera la ventana. Federico lo pidio sacar dos veces y tiene razon: es su
    # pantalla, y la ventana no se pierde. La transparencia no toca el foco — la
    # ventana sigue enfocada y recibiendo teclas aunque no se vea —, asi que
    # Ctrl++ y Ctrl+Shift++ la traen de vuelta a ciegas.
    #
    # Se persisten en config, o sea que un 0 sobrevive al reinicio: Voider puede
    # arrancar invisible. Sigue siendo recuperable con las mismas teclas, y si
    # alguna vez hace falta el valor esta escrito en texto plano en config.json.
    OPACITY_MIN = 0.0
    INK_MIN = 0.0

    @staticmethod
    def _bg_color(alpha):
        """El negro del fondo, con el alpha del eje FONDO."""
        return QColor(0, 0, 0, int(round(max(0.0, min(1.0, alpha)) * 255)))

    @staticmethod
    def _ink_color(alpha):
        """El blanco del circulo y las letras, con el alpha del eje TINTA."""
        return QColor(255, 255, 255, int(round(max(0.0, min(1.0, alpha)) * 255)))

    def _setup_opacity_shortcuts(self):
        # FONDO — Ctrl y '+' se escriben distinto segun el teclado: en layouts
        # donde '+' es Shift+'=', apretar Ctrl y + manda Ctrl+Shift+=, que
        # "Ctrl++" no matchea. Por eso se registran las tres formas: es el motivo
        # tipico de que subir la opacidad "no haga nada" mientras bajarla si.
        for seq in ("Ctrl++", "Ctrl+=", "Ctrl+Shift+="):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._change_opacity(0.1))
        for seq in ("Ctrl+-", "Ctrl+_"):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda: self._change_opacity(-0.1))

        # TINTA — se arma la combinacion a mano en vez de parsear "Ctrl+Shift++",
        # que el parser de Qt lee mal. Key_Plus/Key_Minus son las del numerico,
        # que es donde no hay ambiguedad de Shift.
        mods = (Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier)
        for key, delta in ((Qt.Key.Key_Plus, 0.1), (Qt.Key.Key_Minus, -0.1)):
            sc = QShortcut(QKeySequence(mods | key), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(lambda d=delta: self._change_ink(d))

    @staticmethod
    def _step_value(value, delta, clamp):
        """Un paso de opacidad que cae en una decima redonda.

        Sumar 0.1 en flotante no da decimas: 0.7 + 0.1 = 0.7999999999999999. Ese
        ruido se acumula paso a paso, se guarda asi en config.json, y al
        imprimirlo truncado sale 89% en vez de 90%. Redondear cada paso corta el
        problema en la raiz en vez de maquillarlo solo al mostrarlo.
        """
        return clamp(round(value + delta, 2))

    @staticmethod
    def _as_pct(value):
        """El porcentaje que se muestra. round y no int: int TRUNCA, y con
        0.8999999 mostraba 89."""
        return int(round(value * 100))

    def _change_opacity(self, delta):
        # No se persiste: cada arranque empieza opaco. Ademas config.json esta
        # committeado, y guardar cada paso lo llenaria de ruido en git.
        self.opacity = self._step_value(self.opacity, delta, self._clamp_opacity)
        self._apply_opacity(self.opacity)
        print(f"◐ Fondo {self._as_pct(self.opacity)}%")

    def _change_ink(self, delta):
        """Ctrl+Shift+± : el circulo y las letras, sin tocar el fondo."""
        self.ink_opacity = self._step_value(self.ink_opacity, delta, self._clamp_ink)
        self._repaint_surfaces()
        print(f"◑ Tinta {self._as_pct(self.ink_opacity)}%")

    def _repaint_surfaces(self):
        """Volver a pintar todo lo que depende de los dos alphas.

        El fondo es el negro que pintamos nosotros (hoja de estilo de la ventana
        y los fillRect de las vistas); la tinta es el blanco del circulo y del
        texto. Los dos viven en pintura propia, no en la opacidad de ventana:
        por eso se pueden mover por separado.
        """
        bg, ink = self._bg_color(self.opacity), self._ink_color(self.ink_opacity)
        self.setStyleSheet(
            f"background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});"
            f" color: rgba({ink.red()},{ink.green()},{ink.blue()},{ink.alpha()});"
        )
        # Defensivo a proposito: esto se llama tambien desde el __init__, cuando
        # varias de estas vistas todavia no existen.
        for name in ('normal_view', '_edge_fade', 'circular_view', 'book_view',
                     'scratch_view', 'o_reader_view', 'o_browser_view'):
            w = getattr(self, name, None)
            if w is None:
                continue
            ed = getattr(w, 'editor', None)
            if ed is not None:
                # Con el rojo que ya tenia: el ø tiene que seguir siendo el ø.
                self._apply_editor_style(ed, red=getattr(ed, '_voider_red', False))
            w.update()
        # El entry de F1 tiene hoja propia (no pasa por _apply_editor_style).
        entry = getattr(self, 'entry', None)
        if entry is not None:
            entry.setStyleSheet(f"""
                QLineEdit {{
                    background: transparent;
                    color: rgba(255, 255, 255, {ink.alphaF():.3f});
                    border: none;
                    selection-background-color: rgba(255, 255, 255, {ink.alphaF():.3f});
                    selection-color: rgba(0, 0, 0, {ink.alphaF():.3f});
                }}
            """)
        self.update()

    def _apply_opacity(self, value):
        """Aplicar la transparencia del FONDO.

        Antes esto le pedia a Hyprland que bajara el alpha de toda la ventana, y
        por eso al atenuar el fondo se atenuaba tambien el texto: el compositor
        no distingue el negro del blanco, ve una sola superficie.

        Ahora el alpha lo pintamos nosotros, pixel por pixel — el fondo sale
        rgba(0,0,0,a) y el blanco sale entero. Para que eso llegue a la pantalla
        hacen falta dos cosas: la ventana translucida de verdad (el
        WA_TranslucentBackground del __init__, que pide un visual con canal alfa)
        y que el compositor NO vuelva a multiplicar por su propia regla. Eso
        ultimo es lo que se le dice aca: alphaoverride 1 y alpha 1, o sea "no
        toques nada, ya esta pintado".

        Y noblur, que es la contra de haber hecho la ventana translucida.
        Hyprland trae el blur prendido de fabrica (decoration:blur:enabled = 1,
        no lo configura nadie en nix/) y solo actua donde una ventana deja pasar
        lo de atras. Mientras la superficie era opaca no tenia nada que blurear;
        al volverla translucida le dimos justo lo que su regla esperaba, y el
        fondo se veia borroso. La gracia de la transparencia es ver lo de atras
        nitido, asi que se le dice que a esta ventana no la toque.

        setWindowOpacity(1.0) por la misma razon: en X11 si funciona, y ahi
        atenuaria la ventana entera, que es justo lo que dejamos de querer.
        """
        self.setWindowOpacity(1.0)
        self._repaint_surfaces()
        try:
            # alphafullscreen* son los mismos dos props pero para cuando la
            # ventana esta en fullscreen: Hyprland maneja ese caso por un camino
            # separado, y sin esto la opacidad andaba flotando y no en pantalla
            # completa. Verificado contra una ventana real que los dos existen
            # (un nombre inventado devuelve "Prop not found").
            for prop, val in (('alphaoverride', '1'), ('alpha', '1'),
                              ('alphafullscreenoverride', '1'),
                              ('alphafullscreen', '1'),
                              ('noblur', '1')):
                subprocess.run(
                    ['hyprctl', 'dispatch', 'setprop', 'title:^(Voider)$', prop, val],
                    capture_output=True, timeout=2,
                )
        except (OSError, subprocess.SubprocessError):
            pass   # sin Hyprland (otro escritorio, o una VM): no es un error

    @classmethod
    def _clamp_opacity(cls, value):
        return max(cls.OPACITY_MIN, min(1.0, value))

    @classmethod
    def _clamp_ink(cls, value):
        return max(cls.INK_MIN, min(1.0, value))

    # ── Void key ─────────────────────────────────────────────────────────────

    def _print_void_mode_status(self):
        print("VOID MODE:", "Spacebar" if self.use_spacebar_for_void else "Enter")

    def _connect_void_key(self):
        self._disconnect_void_key()
        # Spacebar voids in dedicated spacebar-mode OR (scriptio continua) whenever
        # Caps Lock is on — the entry only emits spacePressed in those cases, so
        # this connection is harmless otherwise. Enter voids too, except in
        # dedicated spacebar-mode.
        self._void_space_connection = self.entry.spacePressed.connect(self._handle_void_line)
        if not self.use_spacebar_for_void:
            self._void_enter_connection = self.entry.returnPressed.connect(self._handle_void_line)

    def _editor_save(self):
        """F9: convert the edited prose back to the dot-model and write the active
        file — only when the text was actually changed (viewing leaves it alone)."""
        ev = getattr(self, 'editor_view', None)
        if ev is None or not ev.document().isModified():
            return
        prose = ev.toPlainText()
        self._undo_begin()
        # Write the prose verbatim, then reformat it into the dot-model in place
        # (paragraphs -> dot groups, sentence-split lines). Grouped as one undo.
        self._atomic_write_lines(self.current_file_path, prose.split('\n'))
        self.reformat_active_file()
        self._undo_commit(key=('editor', self.current_file_path))
        ev.document().setModified(False)
        print("📝 F9 prose → saved + reformatted into the active file")

    def _f3_mid_edit(self):
        """True when the F3 title field is being actively typed into (pending new
        entry / merge name, or a dirty rename) — Ctrl+Z should undo the typing then,
        not the last library op."""
        if getattr(self, '_book_pending_new', False) or getattr(self, '_book_pending_merge', False):
            return True
        bv = getattr(self, 'book_view', None)
        if bv and self.book_ring.lines:
            cur = self.book_ring.current()
            if cur not in ('.', None) and bv.editor.text().strip() != (cur or '').strip():
                return True
        return False

    def eventFilter(self, obj, event):
        # Mouse pointer follows typing vs. mouse activity (never consumes events).
        ah = getattr(self, '_cursor_autohide', None)
        if ah is not None:
            ah.handle_event_type(event.type())
        # Backtick is a bare (no-modifier) key, so a focused text field would type
        # it instead of letting the router see it. Intercept it here so the scratch
        # round-trip works from F1/F2 too, not only F5.
        if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat() \
                and self._matches(event.key(), event.modifiers(), 'scratch_toggle'):
            self._goto_scratch_toggle()
            return True
        # Intercept Ctrl+Z / Ctrl+Shift+Z before the focused editor's own field
        # undo, but only in the editing views (F1/F2/F5) and F3 (library ops,
        # unless a title is mid-edit — then let the field's own undo run).
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Z \
                and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            v = self.current_view
            if v in (0, 1, 4) or (v == 2 and not self._f3_mid_edit()):
                redo = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._undo_apply(redo=redo)
                return True
        return super().eventFilter(obj, event)

    def _active_file_title(self):
        """F2's pinned title: the active file's name (no extension)."""
        base = os.path.basename(self.current_file_path or '')
        return os.path.splitext(base)[0]

    def _toggle_view_title(self):
        """Ctrl+Shift+T: show/hide the pinned top title in F2 and F5. Persisted."""
        self._show_view_title = not self._show_view_title
        self.config['show_view_title'] = self._show_view_title
        _save_config(self.config)
        self._apply_view_title()

    def _apply_view_title(self):
        """Push title-visibility to whichever of F2/F5 is currently showing."""
        if self.current_view == 4 and getattr(self, 'reorder_view', None):
            self._f5_refresh()
        elif self.current_view == 1 and getattr(self, 'circular_view', None):
            self.circular_view.show_title = self._show_view_title
            self.circular_view.title_text = self._active_file_title()
            self.circular_view.update()

    def _toggle_typewriter(self):
        """Ctrl+Shift+W: toggle F1 typewriter mode (caret fixed at the centre, text
        flows left, clipped at the circle) vs the classic centred entry. Persisted."""
        self._typewriter_mode = not self._typewriter_mode
        self.config['typewriter_mode'] = self._typewriter_mode
        _save_config(self.config)
        self._apply_entry_mode()
        print(f"⌨ Typewriter mode {'ON' if self._typewriter_mode else 'OFF'}")

    def _apply_entry_mode(self):
        """Apply the current typewriter/classic mode to the F1 entry."""
        self.entry.setAlignment(Qt.AlignmentFlag.AlignRight if self._typewriter_mode
                                else Qt.AlignmentFlag.AlignCenter)
        self._reposition_entry()
        self.entry.update()

    def _handle_void_line(self):
        if self.current_view == 4:
            self._f5_fork()
            return
        # Enter on an empty entry: jump to a fresh blank line at the end of the
        # active file, ready to keep writing (works on any active file).
        if not self.entry.text().strip():
            self._f1_goto_end()
            return
        # /0 is the one command: jump to the scratch (moving its portal above the
        # current chapter). Everything else is normal focus writing: commit the
        # line into the active file and open a blank line below to keep going.
        if self.entry.text().strip() == '/0':
            self._f1_scratch_jump()
            self.entry.clear()
            return
        self._f1_commit_line(self.entry.text())
        self.entry.clear()
        self.entry.setCursorPosition(0)

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

    def _toggle_help(self):
        if not self._help_overlay:
            self._help_overlay = HelpOverlay(self)
            self._help_overlay.setGeometry(self.rect())
        self._help_overlay.toggle()

    def _show_lock_screen(self):
        if not self._lock_screen:
            self._lock_screen = LockScreen(self)
            self._lock_screen.setGeometry(self.rect())
        self._lock_screen.show_lock()


def main():
    app = QApplication(sys.argv)
    window = FullscreenCircleApp()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
