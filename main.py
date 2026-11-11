#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tataloo Code - Android code editor (Kivy).

Theme: Tataloo Midnight (black / charcoal / deep crimson).
Runs on desktop (python main.py) and on Android (buildozer, see buildozer.spec).
"""
import codecs
import ctypes
import datetime
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.parse
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup, get_color_from_hex, platform

APP_NAME = 'Tataloo Code'
PORT = 8765
CODE_FONT = 'RobotoMono-Regular'      # ships with Kivy; monospace
MAX_FILE_BYTES = 2 * 1024 * 1024      # editor limit (Kivy TextInput gets slow above this)
MAX_VIEW_LINE = 160                   # colour view: longer lines are cut (texture size limit)
SEARCH_MAX_FILES = 300
SEARCH_MAX_HITS = 150
SEARCH_SKIP_DIRS = {'node_modules', '__pycache__', 'build', 'dist', '.git', '.gradle', '.buildozer', 'bin'}
SEARCH_EXTS = ('.py', '.html', '.htm', '.css', '.js', '.ts', '.json', '.xml', '.txt', '.md', '.sql', '.sh',
               '.csv', '.kt', '.kts', '.java', '.gradle', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.c', '.h',
               '.cpp', '.php', '.rb', '.go', '.rs', '.spec')

# ---- Tataloo Midnight palette
TOP = '#1A1A20'
TAB_BG = '#15151A'
TAB_ACTIVE = '#8E1F36'
SIDE = '#131317'
STATUS = '#8E1F36'
EDITOR = '#101014'
EDIT_LINE = '#1E1E25'
BTN = '#24242C'
ACCENT = '#B3243F'
CONSOLE_BG = '#0B0B0E'
WHITE = '#FFFFFF'
TEXT = '#D4D4DC'
CURSOR = '#E0566A'
SEL = '#5A1A2B'
MUTED = '#8A8A96'
OK = '#98C379'

# ---- syntax palette
C_KW = 'C678DD'
C_BUILTIN = '56B6C2'
C_STR = '98C379'
C_COMMENT = '7F848E'
C_NUM = 'D19A66'
C_FUNC = '61AFEF'
C_CLASS = 'E5C07B'
C_DEC = 'E06C75'
C_LINENO = '5C5C68'

PY_KW = set('False None True and as assert async await break class continue def del elif else except finally '
            'for from global if import in is lambda nonlocal not or pass raise return try while with yield'.split())
PY_BUILTIN = set('print len range str int float list dict set tuple bool open input type isinstance super self cls '
                 'enumerate zip map filter sorted sum min max abs round exec eval'.split())
JS_KW = set('var let const function return if else for while do switch case break continue new this class extends '
            'import export default async await try catch finally throw typeof instanceof of in null undefined '
            'true false'.split())
C_LIKE_KW = set('abstract break case catch class const continue default do else enum extends final finally for fun '
                'if implements import in interface internal is new null object override package private protected '
                'public return static super switch this throw try val var void when while true false int long '
                'float double boolean char string'.split())
HTML_KW = set('html head body div span p a img ul ol li table tr td th script style link meta title h1 h2 h3 h4 h5 '
              'h6 input button form nav header footer section article main label select option textarea'.split())
SQL_KW = set('select from where insert into values update set delete create table drop alter join left right inner '
             'outer on and or not null primary key foreign references order by group having limit as distinct '
             'index view'.split())

_STR = r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\''
_TAIL = r'|(@[A-Za-z_][\w.]*)|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_][\w]*\b)'


def _token_re(comment, strings=_STR):
    return re.compile('(%s)|(%s)%s' % (comment, strings, _TAIL))


# language -> (regex, keywords, builtins, capitalised-names-are-classes)
LANGS = {
    'python': (_token_re(r'#[^\n]*', r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|' + _STR), PY_KW, PY_BUILTIN, True),
    'shell': (_token_re(r'#[^\n]*'), set('if then else elif fi for in do done while case esac function return '
                                         'export echo exit local'.split()), set(), False),
    'javascript': (_token_re(r'//[^\n]*|/\*[\s\S]*?\*/', _STR + r'|`[^`]*`'), JS_KW, set(), True),
    'clike': (_token_re(r'//[^\n]*|/\*[\s\S]*?\*/'), C_LIKE_KW, set(), True),
    'css': (_token_re(r'/\*[\s\S]*?\*/'), set(), set(), False),
    'html': (_token_re(r'<!--[\s\S]*?-->'), HTML_KW, set(), False),
    'sql': (_token_re(r'--[^\n]*|/\*[\s\S]*?\*/'), SQL_KW, set(), False),
    'json': (_token_re(r'(?!x)x'), {'true', 'false', 'null'}, set(), False),
    'plain': (None, set(), set(), False),
}
EXT_LANG = {
    '.py': 'python', '.pyw': 'python', '.sh': 'shell', '.yml': 'shell', '.yaml': 'shell', '.toml': 'shell',
    '.ini': 'shell', '.cfg': 'shell', '.spec': 'shell', '.js': 'javascript', '.ts': 'javascript',
    '.kt': 'clike', '.kts': 'clike', '.java': 'clike', '.c': 'clike', '.h': 'clike', '.cpp': 'clike',
    '.gradle': 'clike', '.go': 'clike', '.rs': 'clike', '.php': 'clike', '.css': 'css',
    '.html': 'html', '.htm': 'html', '.xml': 'html', '.svg': 'html', '.sql': 'sql', '.json': 'json',
}
LANG_LABEL = {'python': 'Python', 'shell': 'Shell / config', 'javascript': 'JavaScript', 'clike': 'C-like',
              'css': 'CSS', 'html': 'HTML / XML', 'sql': 'SQL', 'json': 'JSON', 'plain': 'Plain text'}


def lang_for(path):
    return EXT_LANG.get(Path(path).suffix.lower(), 'plain') if path else 'plain'


def rgba(value, alpha=1.0):
    return tuple(get_color_from_hex(value)[:3]) + (alpha,)


def _wrap_lines(open_tag, close_tag, tok):
    """Wrap a (possibly multi-line) token so every line carries its own markup tags."""
    return '\n'.join(open_tag + escape_markup(part) + close_tag if part else '' for part in tok.split('\n'))


def hilite(text, lang):
    """Return Kivy markup for text. Tags never span a newline, so the result can be split per line."""
    regex, kw, builtins_, classes = LANGS.get(lang, LANGS['plain'])
    if regex is None:
        return escape_markup(text)
    lower_kw = lang == 'sql'
    out = []
    pos = 0
    for m in regex.finditer(text):
        if m.start() > pos:
            out.append(escape_markup(text[pos:m.start()]))
        pos = m.end()
        tok = m.group(0)
        if m.group(1):
            out.append(_wrap_lines('[color=%s][i]' % C_COMMENT, '[/i][/color]', tok))
        elif m.group(2):
            out.append(_wrap_lines('[color=%s]' % C_STR, '[/color]', tok))
        elif m.group(3):
            out.append('[color=%s]%s[/color]' % (C_DEC, escape_markup(tok)))
        elif m.group(4):
            out.append('[color=%s]%s[/color]' % (C_NUM, tok))
        else:
            key = tok.lower() if lower_kw else tok
            if key in kw:
                out.append('[color=%s][b]%s[/b][/color]' % (C_KW, tok))
            elif tok in builtins_:
                out.append('[color=%s]%s[/color]' % (C_BUILTIN, tok))
            elif classes and tok[:1].isupper():
                out.append('[color=%s]%s[/color]' % (C_CLASS, tok))
            elif text[m.end():m.end() + 1] == '(':
                out.append('[color=%s]%s[/color]' % (C_FUNC, tok))
            else:
                out.append(tok)
    out.append(escape_markup(text[pos:]))
    return ''.join(out)


def hilite_lines(text, lang, tab_width=4):
    """List of markup strings, one per source line, each prefixed with a line number."""
    src = []
    for line in text.split('\n'):
        line = line.replace('\t', ' ' * tab_width)
        if len(line) > MAX_VIEW_LINE:
            line = line[:MAX_VIEW_LINE - 4] + ' ...'
        src.append(line)
    marked = hilite('\n'.join(src), lang).split('\n')
    digits = max(3, len(str(len(marked))))
    return ['[color=%s]%*d[/color]  %s' % (C_LINENO, digits, i, m) for i, m in enumerate(marked, 1)]


# ---------------------------------------------------------------- file helpers
class FileProblem(Exception):
    pass


def read_text_file(path):
    """Return (text, encoding, newline). Text always uses '\\n' internally."""
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise FileProblem('File is larger than the %d MB editor limit.' % (MAX_FILE_BYTES // (1024 * 1024)))
    with open(path, 'rb') as f:
        raw = f.read()
    if b'\x00' in raw[:8192]:
        raise FileProblem('This looks like a binary file and cannot be edited.')
    if raw.startswith(codecs.BOM_UTF8):
        text, enc = raw[len(codecs.BOM_UTF8):].decode('utf-8', errors='strict'), 'utf-8-sig'
    else:
        try:
            text, enc = raw.decode('utf-8'), 'utf-8'
        except UnicodeDecodeError:
            # latin-1 maps every byte, so saving writes back exactly the same bytes
            text, enc = raw.decode('latin-1'), 'latin-1'
    newline = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text, enc, newline


def write_text_file(path, text, encoding='utf-8', newline='\n'):
    """Atomic save (temp file + replace). Returns the encoding actually used."""
    if newline != '\n':
        text = text.replace('\n', newline)
    try:
        data = text.encode(encoding)
    except UnicodeEncodeError:
        encoding = 'utf-8'
        data = text.encode(encoding)
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, '.%s.tmp~' % os.path.basename(path))
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except OSError:
        # some Android storage providers refuse rename-over; fall back to a direct write
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        with open(path, 'wb') as f:
            f.write(data)
    return encoding


def name_error(name):
    """Return an error message for an invalid file/folder name, or None."""
    if not name or name in ('.', '..'):
        return 'Name is empty or invalid.'
    if '/' in name or '\\' in name or '\x00' in name:
        return 'Name must not contain / or \\.'
    return None


def save_crash(text, extra_dir=None):
    for base in (extra_dir, '/storage/emulated/0/Download', '/sdcard/Download', tempfile.gettempdir()):
        if not base:
            continue
        try:
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, 'tataloo_crash.txt'), 'w', encoding='utf-8') as f:
                f.write(text)
            return base
        except Exception:
            continue
    return None


def shared_storage():
    """Shared storage root if it is really usable, else None."""
    for p in ('/storage/emulated/0', '/sdcard'):
        try:
            if os.path.isdir(p) and os.access(p, os.R_OK | os.W_OK):
                os.listdir(p)
                return p
        except Exception:
            pass
    return None


def dt_now():
    return datetime.datetime.now().strftime('%H:%M:%S')


# ---------------------------------------------------------------- widgets
class Panel(BoxLayout):
    def __init__(self, color=TOP, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._c = Color(*rgba(color))
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


class Btn(Button):
    def __init__(self, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', rgba(BTN))
        kw.setdefault('color', rgba(WHITE))
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(42))
        kw.setdefault('font_size', sp(13))
        super().__init__(**kw)


class FlatBtn(Btn):
    def __init__(self, **kw):
        kw.setdefault('background_color', rgba(ACCENT))
        super().__init__(**kw)


class IconBtn(Button):
    """Top-bar icon drawn on the canvas: 'menu' (3 bars), 'dots' (3 dots), 'edit' (pencil)."""

    def __init__(self, icon='menu', **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', (0, 0, 0, 0))
        kw.setdefault('text', '')
        kw.setdefault('size_hint_x', None)
        kw.setdefault('width', dp(48))
        super().__init__(**kw)
        self.icon = icon
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *a):
        self.canvas.after.clear()
        cx, cy = self.center_x, self.center_y
        s = dp(7)
        with self.canvas.after:
            Color(1, 1, 1, 1)
            if self.icon == 'menu':
                for i in (-1, 0, 1):
                    y = cy + i * s
                    Line(points=[cx - dp(9), y, cx + dp(9), y], width=dp(1.8))
            elif self.icon == 'dots':
                for i in (-1, 0, 1):
                    y = cy + i * s
                    Ellipse(pos=(cx - dp(2), y - dp(2)), size=(dp(4), dp(4)))
            elif self.icon == 'edit':
                Line(points=[cx - dp(8), cy - dp(8), cx + dp(7), cy + dp(7)], width=dp(2))
                Line(points=[cx - dp(10), cy - dp(10), cx - dp(8), cy - dp(5)], width=dp(2))


class KeyBtn(Btn):
    def __init__(self, **kw):
        kw.setdefault('size_hint_x', None)
        kw.setdefault('width', dp(44))
        kw.setdefault('height', dp(36))
        kw.setdefault('color', rgba(TEXT))
        kw.setdefault('font_size', sp(15))
        super().__init__(**kw)


class ColorLine(Label):
    """One source line in the read-only colour view (used by RecycleView)."""

    def __init__(self, **kw):
        kw.setdefault('markup', True)
        kw.setdefault('font_name', CODE_FONT)
        kw.setdefault('color', rgba(TEXT))
        kw.setdefault('halign', 'left')
        kw.setdefault('valign', 'middle')
        super().__init__(**kw)
        self.bind(size=self._sync)

    def _sync(self, *_):
        self.text_size = (self.width, None)


class CodeEditor(TextInput):
    app_ref = None

    def insert_text(self, substring, from_undo=False):
        app = self.app_ref
        if app is not None and not from_undo:
            width = app.tab_width()
            if substring == '\t':
                col = self.cursor_col
                return super().insert_text(' ' * (width - col % width), from_undo=from_undo)
            if substring == '\n' and app.settings.get('auto_indent', True):
                idx = self.cursor_index()
                text = self.text
                ls = text.rfind('\n', 0, idx) + 1
                line = text[ls:idx]
                indent = re.match(r'[ \t]*', line).group(0)
                if line.rstrip().endswith((':', '{', '[', '(')):
                    indent += ' ' * width
                return super().insert_text('\n' + indent, from_undo=from_undo)
        return super().insert_text(substring, from_undo=from_undo)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        app = self.app_ref
        if app is not None and ('ctrl' in modifiers or 'meta' in modifiers) and 'alt' not in modifiers:
            action = {'s': app.save, 'f': app.find_popup, 'h': app.replace_popup, 'g': app.goto_popup,
                      'n': app.new_untitled, 'w': app.close_current}.get(keycode[1])
            if action is not None:
                action()
                return True
        return super().keyboard_on_key_down(window, keycode, text, modifiers)


class Tab:
    def __init__(self, path=None, text=''):
        self.path = path
        self.text = text
        self.cursor = 0
        self.modified = False
        self.pinned = False
        self.hint = 'untitled'
        self.encoding = 'utf-8'
        self.newline = '\n'

    @property
    def name(self):
        return Path(self.path).name if self.path else self.hint


class _ThreadStream:
    """stdout/stderr proxy: output of the script thread goes to the console, the rest passes through."""

    def __init__(self, original, sink):
        self._original = original
        self._sink = sink
        self.thread_id = None

    def write(self, s):
        if threading.get_ident() == self.thread_id:
            self._sink(s)
            return len(s)
        if self._original is not None:
            return self._original.write(s)
        return len(s)

    def flush(self):
        if self._original is not None and threading.get_ident() != self.thread_id:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def __getattr__(self, item):
        return getattr(self._original, item)


class TatalooCodeApp(App):
    title = APP_NAME

    # ================= lifecycle =================
    def build(self):
        try:
            return self._build()
        except Exception:
            err = traceback.format_exc()
            save_crash(err, getattr(self, 'user_data_dir', None))
            box = BoxLayout(orientation='vertical', padding=dp(8))
            sv = ScrollView()
            lab = Label(text='CRASH REPORT\n\n' + err, color=rgba('#FF3355'), font_size='11sp',
                        size_hint_y=None, halign='left', valign='top')
            lab.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
            lab.bind(texture_size=lambda w, v: setattr(w, 'height', v[1]))
            sv.add_widget(lab)
            box.add_widget(sv)
            return box

    def _load_settings(self):
        self.settings = {'font_size': 14, 'wrap': False, 'auto_indent': True, 'tab_width': 4, 'recent': [],
                         'asked_all_files': False}
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self.settings.update(data)
        except Exception:
            pass
        # never trust the file: a broken value must not crash the app at start-up
        s = self.settings
        try:
            s['font_size'] = max(9, min(30, int(s['font_size'])))
        except (TypeError, ValueError):
            s['font_size'] = 14
        try:
            s['tab_width'] = int(s['tab_width'])
        except (TypeError, ValueError):
            s['tab_width'] = 4
        if s['tab_width'] not in (2, 4, 8):
            s['tab_width'] = 4
        s['wrap'] = bool(s.get('wrap'))
        s['auto_indent'] = bool(s.get('auto_indent', True))
        if not isinstance(s.get('recent'), list):
            s['recent'] = []
        s['recent'] = [p for p in s['recent'] if isinstance(p, str)][:15]

    def tab_width(self):
        return int(self.settings.get('tab_width', 4))

    def _build(self):
        Window.clearcolor = rgba(EDITOR)
        # 'resize' keeps the symbol bar and status line visible above the soft keyboard
        Window.softinput_mode = 'resize'
        self.home = Path(self.user_data_dir)
        self.home.mkdir(parents=True, exist_ok=True)
        self.projects_dir = self.home / 'projects'
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.home / 'settings.json'
        self.session_path = self.home / 'session.json'
        self._load_settings()
        self.tabs = []
        self.cur = -1
        self.loading = False
        self.edit_mode = True
        self.modals = []
        self.explorer_fc = None
        self.sidebar = None
        self.server = None
        self.untitled_seq = 0
        self.run_thread = None
        self.run_buf = []
        self.run_lock = threading.Lock()
        self.run_poll = None
        self.search_token = None
        self._streams = None

        root = Panel(EDITOR, orientation='vertical')

        # ---- top bar
        top = Panel(TOP, size_hint_y=None, height=dp(52), spacing=dp(2))
        top.add_widget(IconBtn('menu', on_release=lambda *_: self.show_sidebar()))
        title_box = BoxLayout(orientation='vertical', padding=[dp(4), dp(4)])
        self.title_label = Label(text=APP_NAME, color=rgba(WHITE), bold=True, font_size=sp(16),
                                 halign='left', valign='bottom', size_hint_y=0.6, shorten=True,
                                 shorten_from='left')
        self.subtitle = Label(text='', color=rgba(MUTED), font_size=sp(11), halign='left', valign='top',
                              size_hint_y=0.4)
        for lab in (self.title_label, self.subtitle):
            lab.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], s[1])))
        title_box.add_widget(self.title_label)
        title_box.add_widget(self.subtitle)
        top.add_widget(title_box)
        top.add_widget(IconBtn('edit', on_release=lambda *_: self.file_properties()))
        top.add_widget(IconBtn('dots', on_release=lambda *_: self.main_menu()))
        root.add_widget(top)

        # ---- tab bar
        tabbar = Panel(TAB_BG, size_hint_y=None, height=dp(40), spacing=dp(2))
        self.tab_scroll = ScrollView(do_scroll_y=False, bar_width=0)
        self.tab_row = BoxLayout(size_hint_x=None, spacing=dp(2))
        self.tab_row.bind(minimum_width=self.tab_row.setter('width'))
        self.tab_scroll.add_widget(self.tab_row)
        tabbar.add_widget(self.tab_scroll)
        tabbar.add_widget(Btn(text='+', size_hint_x=None, width=dp(40), height=dp(40), font_size=sp(18),
                              background_color=rgba(TAB_BG), on_release=lambda *_: self.new_untitled()))
        tabbar.add_widget(IconBtn('dots', width=dp(40), on_release=lambda *_: self.tab_more_menu()))
        root.add_widget(tabbar)

        # ---- editor host
        self.editor_host = BoxLayout()
        root.add_widget(self.editor_host)

        self.editor = CodeEditor(multiline=True, write_tab=True, font_size=sp(self.settings['font_size']),
                                 font_name=CODE_FONT, background_color=rgba(EDITOR),
                                 foreground_color=rgba(TEXT), cursor_color=rgba(CURSOR),
                                 selection_color=rgba(SEL, 0.9), padding=[dp(10), dp(8)],
                                 background_normal='', background_active='')
        self.editor.app_ref = self
        self.editor.bind(text=self._on_text, cursor=self._on_cursor)
        if hasattr(self.editor, 'do_wrap'):
            self.editor.do_wrap = self.settings['wrap']

        # ---- read-only colour view: one recycled Label per line (small textures, any file length)
        self.color_rv = RecycleView(size_hint_x=None, bar_width=dp(4), scroll_type=['bars', 'content'])
        self.color_rv.viewclass = ColorLine
        self.color_layout = RecycleBoxLayout(orientation='vertical', size_hint_y=None, default_size_hint=(1, None),
                                             default_size=(None, dp(20)), padding=[dp(8), dp(6)])
        self.color_layout.bind(minimum_height=self.color_layout.setter('height'))
        self.color_rv.add_widget(self.color_layout)
        self.color_sv = ScrollView(do_scroll_y=False, bar_width=dp(3))
        self.color_sv.add_widget(self.color_rv)
        self.color_sv.bind(width=lambda *_: self._size_color_view())
        self._color_chars = 0

        # ---- extra keys bar
        keys_sv = ScrollView(size_hint_y=None, height=dp(42), do_scroll_y=False, bar_width=0)
        keys = BoxLayout(size_hint_x=None, spacing=dp(3), padding=[dp(3), dp(3)])
        keys.bind(minimum_width=keys.setter('width'))
        for s in ['Tab', '<Tab', 'Undo', 'Redo', '(', ')', '[', ']', '{', '}', '<', '>', '=', ':', '"', "'", '.',
                  ',', '_', '-', '+', '*', '/', '\\', '#', '&', '|', '!', '?', '@', '$', '%', ';']:
            keys.add_widget(KeyBtn(text=s, width=dp(58) if len(s) > 1 else dp(44),
                                   on_release=lambda _b, a=s: self.sym_key(a)))
        keys_sv.add_widget(keys)
        root.add_widget(keys_sv)

        # ---- status bar
        status = Panel(STATUS, size_hint_y=None, height=dp(24), padding=[dp(8), 0])
        self.status = Label(text='', color=rgba(WHITE), font_size=sp(11), halign='left', valign='middle',
                            shorten=True, shorten_from='left')
        self.status.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], s[1])))
        status.add_widget(self.status)
        root.add_widget(status)

        # ---- console (popup, opened from menu)
        self.console_out = TextInput(readonly=True, multiline=True, font_size=sp(11), font_name=CODE_FONT,
                                     background_color=rgba(CONSOLE_BG), foreground_color=rgba(OK),
                                     padding=[dp(8), dp(6)], background_normal='', background_active='')
        self.console_pop = None

        self._rebuild_editor_view()
        self.new_untitled()
        self.console_write('%s ready.' % APP_NAME, 'system')
        Clock.schedule_once(self._restore_session, 0.2)
        Clock.schedule_once(self._ask_permissions, 1.0)
        Window.bind(on_keyboard=self._on_key)
        return root

    def on_pause(self):
        self.save_session()
        return True

    def on_resume(self):
        pass

    def on_stop(self):
        self.save_session()
        self.stop_server(quiet=True)

    # ================= settings / session =================
    def save_settings(self):
        try:
            write_text_file(str(self.settings_path), json.dumps(self.settings, ensure_ascii=False, indent=2))
        except Exception as exc:
            self.console_write('Settings save error: %s' % exc, 'stderr')

    def save_session(self):
        """Stores open tabs. Unsaved text is stored too, so nothing is lost if Android kills the app."""
        try:
            self._stash()
            tabs = []
            for t in self.tabs:
                if not t.path and not t.text:
                    continue
                item = {'path': t.path, 'cursor': t.cursor, 'pinned': t.pinned, 'hint': t.hint,
                        'encoding': t.encoding, 'newline': t.newline}
                if t.modified or not t.path:
                    item['text'] = t.text
                tabs.append(item)
            cur_tab = self.tabs[self.cur] if 0 <= self.cur < len(self.tabs) else None
            active = None
            if cur_tab is not None:
                kept = [t for t in self.tabs if t.path or t.text]
                active = kept.index(cur_tab) if cur_tab in kept else None
            data = {'version': 2, 'tabs': tabs, 'active': active}
            write_text_file(str(self.session_path), json.dumps(data, ensure_ascii=False))
            self.save_settings()
        except Exception as exc:
            save_crash('save_session failed:\n' + traceback.format_exc(), str(getattr(self, 'home', '')))
            print('save_session failed: %s' % exc)

    def _restore_session(self, *_):
        try:
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        items = data.get('tabs')
        if not isinstance(items, list):          # session written by the first version of the app
            items = [{'path': p} for p in data.get('paths', []) if isinstance(p, str)]
            old_active = data.get('active')
            data['active'] = next((i for i, it in enumerate(items) if it['path'] == old_active), None)
        restored = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get('path') if isinstance(item.get('path'), str) else None
            text = item.get('text') if isinstance(item.get('text'), str) else None
            tab = None
            if text is not None:                  # unsaved work: bring it back exactly
                tab = Tab(path, text)
                tab.modified = True
                tab.encoding = item.get('encoding') if item.get('encoding') in ('utf-8', 'utf-8-sig', 'latin-1') \
                    else 'utf-8'
                tab.newline = '\r\n' if item.get('newline') == '\r\n' else '\n'
                if not path:
                    self.untitled_seq += 1
                    tab.hint = str(item.get('hint') or 'untitled-%d' % self.untitled_seq)
            elif path and os.path.isfile(path):
                try:
                    content, enc, nl = read_text_file(path)
                except Exception as exc:
                    self.console_write('Could not reopen %s: %s' % (path, exc), 'stderr')
                    restored.append(None)
                    continue
                tab = Tab(path, content)
                tab.encoding, tab.newline = enc, nl
            if tab is None:
                restored.append(None)
                continue
            try:
                tab.cursor = max(0, int(item.get('cursor', 0)))
            except (TypeError, ValueError):
                tab.cursor = 0
            tab.pinned = bool(item.get('pinned'))
            restored.append(tab)
        real = [t for t in restored if t is not None]
        if not real:
            return
        self._drop_blank_untitled()
        self._stash()
        self.tabs.extend(real)
        active = data.get('active')
        target = restored[active] if isinstance(active, int) and 0 <= active < len(restored) else None
        self.switch(self.tabs.index(target) if target in self.tabs else len(self.tabs) - 1)

    def _ask_permissions(self, *_, force=False):
        if platform != 'android':
            if force:
                self.info('Storage', 'Only needed on Android.')
            return
        try:
            from jnius import autoclass
            sdk = autoclass('android.os.Build$VERSION').SDK_INT
        except Exception:
            sdk = 0
        if sdk < 30:
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except Exception as exc:
                self.console_write('Permission request failed: %s' % exc, 'stderr')
            return
        try:
            from jnius import autoclass
            env = autoclass('android.os.Environment')
            if env.isExternalStorageManager():
                if force:
                    self.info('Storage', 'All-files access is already granted.')
                return
            # ask only once automatically; later only from the menu
            if self.settings.get('asked_all_files') and not force:
                return
            self.settings['asked_all_files'] = True
            self.save_settings()

            def go(yes):
                if not yes:
                    return
                try:
                    intent_cls = autoclass('android.content.Intent')
                    settings_cls = autoclass('android.provider.Settings')
                    uri = autoclass('android.net.Uri')
                    act = autoclass('org.kivy.android.PythonActivity').mActivity
                    act.startActivity(intent_cls(settings_cls.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                                                 uri.parse('package:' + act.getPackageName())))
                except Exception as exc:
                    self.info('Storage', 'Could not open the permission screen:\n%s' % exc)
            self.confirm('Storage access',
                         'To open files outside the app folder, Android needs "All files access".\n'
                         'Open the permission screen now?\n\n'
                         'Without it you can still work in the App folder.', go)
        except Exception as exc:
            self.console_write('Permission check failed: %s' % exc, 'stderr')

    def start_dir(self):
        return shared_storage() or str(self.projects_dir)

    # ================= popup helpers =================
    def open_modal(self, widget):
        if widget in self.modals:
            return widget
        self.modals.append(widget)

        def gone(*_):
            if widget in self.modals:
                self.modals.remove(widget)
            widget.unbind(on_dismiss=gone)
        widget.bind(on_dismiss=gone)
        widget.open()
        return widget

    def _popup(self, title, content, **kw):
        return Popup(title=title, content=content, title_color=rgba(WHITE), separator_color=rgba(ACCENT),
                     background='', background_color=rgba(TOP), **kw)

    def info(self, title, text):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        sv = ScrollView()
        lab = Label(text=str(text), color=rgba(TEXT), font_size=sp(13), size_hint_y=None, halign='left',
                    valign='top')
        lab.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        lab.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(10)))
        sv.add_widget(lab)
        box.add_widget(sv)
        ok = FlatBtn(text='OK')
        box.add_widget(ok)
        p = self._popup(title, box, size_hint=(0.92, 0.6))
        ok.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def ask_text(self, title, prompt, callback, initial=''):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        lab = Label(text=prompt, color=rgba(TEXT), size_hint_y=None, height=dp(36), font_size=sp(12),
                    halign='left', valign='middle')
        lab.bind(size=lambda w, s: setattr(w, 'text_size', s))
        box.add_widget(lab)
        ti = TextInput(text=initial, multiline=False, size_hint_y=None, height=dp(44), write_tab=False,
                       background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR),
                       background_normal='', background_active='')
        box.add_widget(ti)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        ok, cancel = FlatBtn(text='OK'), Btn(text='Cancel')
        row.add_widget(ok)
        row.add_widget(cancel)
        box.add_widget(row)
        box.add_widget(BoxLayout())
        # near the top of the screen so the soft keyboard does not cover it; no accidental dismiss
        p = self._popup(title, box, size_hint=(0.92, None), height=dp(240), pos_hint={'top': 0.97},
                        auto_dismiss=False)

        def done(*_):
            value = ti.text.strip()
            p.dismiss()
            if value:
                callback(value)
        ok.bind(on_release=done)
        ti.bind(on_text_validate=done)
        cancel.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)
        Clock.schedule_once(lambda d: setattr(ti, 'focus', True), 0.15)

    def choice(self, title, text, buttons):
        """buttons: list of (label, callback or None). The first one is the highlighted default."""
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        lab = Label(text=text, color=rgba(TEXT), font_size=sp(13), halign='center', valign='middle')
        lab.bind(size=lambda w, s: setattr(w, 'text_size', s))
        box.add_widget(lab)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        p = self._popup(title, box, size_hint=(0.9, None), height=dp(230), auto_dismiss=False)
        for i, (label, fn) in enumerate(buttons):
            b = (FlatBtn if i == 0 else Btn)(text=label)

            def hit(_b, f=fn):
                p.dismiss()
                if f is not None:
                    f()
            b.bind(on_release=hit)
            row.add_widget(b)
        box.add_widget(row)
        self.open_modal(p)

    def confirm(self, title, text, callback):
        self.choice(title, text, [('Yes', lambda: callback(True)), ('No', lambda: callback(False))])

    def list_menu(self, title, items):
        """items: list of (label, callback); callback None shows a disabled heading."""
        mv = ModalView(size_hint=(0.82, None), height=dp(56) + dp(46) * min(len(items), 12) + dp(8),
                       background='', background_color=rgba(TOP))
        sv = ScrollView(bar_width=dp(3))
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2), padding=dp(6))
        box.bind(minimum_height=box.setter('height'))
        head = Label(text=title, color=rgba(CURSOR), bold=True, size_hint_y=None, height=dp(34), font_size=sp(14),
                     halign='left', valign='middle', shorten=True)
        head.bind(size=lambda w, s: setattr(w, 'text_size', (s[0] - dp(8), s[1])))
        box.add_widget(head)
        for label, fn in items:
            b = Btn(text=label, height=dp(44), halign='left', valign='middle', shorten=True, shorten_from='center')
            b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(14), s[1])))
            if fn is None:
                b.disabled = True
                b.background_color = rgba(TOP)
                b.color = rgba(MUTED)
            else:
                b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), Clock.schedule_once(lambda d: f(), 0.05)))
            box.add_widget(b)
        sv.add_widget(box)
        mv.add_widget(sv)
        self.open_modal(mv)

    # ================= menus =================
    def main_menu(self):
        items = [
            ('New file', self.new_untitled), ('Open (Files)', self.show_files),
            ('Open recent', self.open_recent), ('Save', self.save), ('Save as', self.save_as),
            ('Save all', self.save_all), ('Close file', self.close_current),
            ('Find', self.find_popup), ('Find & Replace', self.replace_popup), ('Go to line', self.goto_popup),
            ('Colour view: %s' % ('off' if self.edit_mode else 'on'), self.toggle_read_only),
            ('Run Python', self.run_python),
        ]
        if self.run_thread is not None:
            items.append(('Stop script', self.stop_python))
        items.append(('Preview HTML', self.preview_html))
        if self.server is not None:
            items.append(('Stop preview server', self.stop_server))
        items += [('Console', self.show_console), ('Terminal command', self.terminal_popup),
                  ('Settings', self.show_settings)]
        if platform == 'android':
            items.append(('Storage permission', lambda: self._ask_permissions(force=True)))
        items += [('Help', self.show_help), ('Exit', self.exit_app)]
        self.list_menu(APP_NAME, items)

    def _cur_tab(self):
        return self.tabs[self.cur] if 0 <= self.cur < len(self.tabs) else None

    def file_properties(self):
        t = self._cur_tab()
        if t is None:
            return
        self.list_menu('File properties', [
            ('Rename', self.rename_current),
            ('Syntax: %s (from file extension)' % LANG_LABEL[lang_for(t.path)], None),
            ('Encoding: %s' % t.encoding, None),
            ('Line endings: %s (tap to switch)' % ('CRLF' if t.newline == '\r\n' else 'LF'), self.toggle_newline),
            ('Read only / colour view: %s' % ('off' if self.edit_mode else 'on'), self.toggle_read_only),
            ('Format (trim spaces / pretty JSON)', self.format_doc),
            ('Copy path', lambda: self._copy(t.path or t.name)),
            ('File info', self.file_info),
        ])

    def tab_more_menu(self):
        t = self._cur_tab()
        if t is None:
            return
        self.list_menu(t.name, [
            ('Unpin tab' if t.pinned else 'Pin tab', lambda: self._toggle_pin(t)),
            ('Close tab', lambda: self.close_tab(t)),
            ('Close tabs to the right', lambda: self.close_side(t, 'right')),
            ('Close tabs to the left', lambda: self.close_side(t, 'left')),
            ('Close other tabs', lambda: self.close_others(t)),
            ('Find', self.find_popup),
            ('Go to line', self.goto_popup),
            ('Select all', self.select_all),
            ('Copy path', lambda: self._copy(t.path or t.name)),
        ])

    def toggle_newline(self):
        t = self._cur_tab()
        if t is None:
            return
        t.newline = '\n' if t.newline == '\r\n' else '\r\n'
        t.modified = True
        self.refresh_tabs()

    def toggle_read_only(self):
        self.edit_mode = not self.edit_mode
        self._rebuild_editor_view()
        self.update_status()

    def _ensure_edit(self):
        if not self.edit_mode:
            self.toggle_read_only()

    def file_info(self):
        t = self._cur_tab()
        if t is None:
            return
        self._stash()
        on_disk = os.path.getsize(t.path) if t.path and os.path.isfile(t.path) else None
        self.info('File info', 'Name: %s\nPath: %s\nSize on disk: %s\nSize in editor: %s bytes\nLines: %s\n'
                               'Encoding: %s\nLine endings: %s' % (
                                   t.name, t.path or '(not saved)',
                                   '%s bytes' % format(on_disk, ',') if on_disk is not None else '-',
                                   format(len(t.text.encode('utf-8', errors='replace')), ','),
                                   t.text.count('\n') + 1, t.encoding, 'CRLF' if t.newline == '\r\n' else 'LF'))

    def _rename_path(self, old, name):
        """Rename on disk and update every open tab / recent entry. Returns new path; raises on problems."""
        problem = name_error(name)
        if problem:
            raise FileProblem(problem)
        new = os.path.join(os.path.dirname(old), name)
        if new == old:
            return old
        same_file = os.path.exists(new) and os.path.exists(old) and os.path.samefile(old, new)
        if os.path.lexists(new) and not same_file:      # os.rename would silently overwrite it
            raise FileProblem('"%s" already exists.' % name)
        os.rename(old, new)
        prefix = old.rstrip(os.sep) + os.sep
        for t in self.tabs:
            if t.path == old:
                t.path = new
            elif t.path and t.path.startswith(prefix):   # file inside a renamed folder
                t.path = os.path.join(new, t.path[len(prefix):])
        self.settings['recent'] = [new if p == old else p for p in self.settings.get('recent', [])]
        self.save_settings()
        self.refresh_tabs()
        return new

    def rename_current(self):
        t = self._cur_tab()
        if t is None:
            return
        if not t.path:
            self.save_as()
            return

        def got(name):
            try:
                self._rename_path(t.path, name)
            except Exception as exc:
                self.info('Rename failed', str(exc))
        self.ask_text('Rename', 'New name:', got, initial=Path(t.path).name)

    def _toggle_pin(self, tab):
        tab.pinned = not tab.pinned
        self.refresh_tabs()

    def _copy(self, text):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            self.console_write('Copied to clipboard (%d chars).' % len(text), 'system')
        except Exception as exc:
            self.console_write('Copy failed: %s' % exc, 'stderr')

    # ================= tabs =================
    def refresh_tabs(self):
        self.tab_row.clear_widgets()
        for i, t in enumerate(self.tabs):
            active = i == self.cur
            label = ('* ' if t.modified else '') + ('[P] ' if t.pinned else '') + t.name
            tab_bg = rgba(TAB_ACTIVE) if active else rgba(BTN)
            b = Btn(text=label, size_hint_x=None, width=dp(140), height=dp(40), background_color=tab_bg,
                    font_size=sp(12), halign='center', valign='middle', shorten=True, shorten_from='left')
            b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(6), s[1])))
            b.bind(on_release=lambda _b, tab=t: self.switch_to(tab))
            x = Btn(text='x', size_hint_x=None, width=dp(34), height=dp(40), background_color=tab_bg)
            x.bind(on_release=lambda _b, tab=t: self.close_tab(tab))
            self.tab_row.add_widget(b)
            self.tab_row.add_widget(x)
            if active:
                Clock.schedule_once(lambda d, w=b: self._reveal_tab(w), 0)
        t = self._cur_tab()
        self.title_label.text = t.name if t else APP_NAME
        self.update_status()

    def _reveal_tab(self, widget):
        try:
            if widget.parent is self.tab_row and self.tab_row.width > self.tab_scroll.width:
                self.tab_scroll.scroll_to(widget, padding=dp(40), animate=False)
        except Exception:
            pass

    def _stash(self):
        t = self._cur_tab()
        if t is not None:
            t.text = self.editor.text
            t.cursor = self.editor.cursor_index()

    def switch_to(self, tab):
        if tab in self.tabs:
            self.switch(self.tabs.index(tab))

    def switch(self, idx):
        if not (0 <= idx < len(self.tabs)):
            return
        self._stash()
        self.cur = idx
        t = self.tabs[idx]
        self.loading = True
        try:
            self.editor.text = t.text
            self.editor.cancel_selection()
            # the undo stack belongs to the previous tab's text; replaying it here would corrupt this file
            self.editor.reset_undo()
        finally:
            self.loading = False
        self._rebuild_editor_view()
        self.refresh_tabs()
        Clock.schedule_once(lambda d: self._set_cursor(t.cursor) if self._cur_tab() is t else None, 0.05)

    def _set_cursor(self, idx):
        try:
            idx = max(0, min(int(idx), len(self.editor.text)))
            self.editor.cursor = self.editor.get_cursor_from_index(idx)
        except Exception:
            pass

    def _on_text(self, *_):
        if self.loading:
            return
        t = self._cur_tab()
        if t is not None and not t.modified:
            t.modified = True
            self.refresh_tabs()

    def _on_cursor(self, *_):
        self.update_status()

    def _drop_blank_untitled(self):
        """Remove the automatic empty 'untitled' tab when real files are opened."""
        if len(self.tabs) == 1 and self.cur == 0:
            t = self.tabs[0]
            if not t.path and not t.modified and not self.editor.text:
                self.tabs.pop()
                self.cur = -1

    def new_untitled(self):
        self._ensure_edit()
        self._stash()
        t = Tab(None, '')
        self.untitled_seq += 1
        t.hint = 'untitled-%d' % self.untitled_seq
        self.tabs.append(t)
        self.switch(len(self.tabs) - 1)

    def _remove_tab(self, tab):
        if tab not in self.tabs:
            return
        idx = self.tabs.index(tab)
        was_current = idx == self.cur
        self.tabs.pop(idx)
        if not self.tabs:
            self.cur = -1
            self.new_untitled()
            return
        if was_current:
            self.cur = -1
            self.switch(min(idx, len(self.tabs) - 1))
        else:
            if self.cur > idx:
                self.cur -= 1
            self.refresh_tabs()

    def close_tab(self, tab):
        if tab not in self.tabs:
            return
        if not tab.modified:
            self._remove_tab(tab)
            return

        def save_then_close():
            if tab not in self.tabs:
                return
            if tab.path:
                if self.save_tab(tab):
                    self._remove_tab(tab)
            else:
                self.save_as(tab, after=lambda: self._remove_tab(tab))
        self.choice('Unsaved changes', 'Save changes to %s before closing?' % tab.name,
                    [('Save', save_then_close), ('Discard', lambda: self._remove_tab(tab)), ('Cancel', None)])

    def close_index(self, idx):
        if 0 <= idx < len(self.tabs):
            self.close_tab(self.tabs[idx])

    def close_current(self):
        self.close_index(self.cur)

    def _close_many(self, victims, keep):
        """Close a group of tabs. Pinned and unsaved tabs are never closed silently."""
        self._stash()
        skipped = [t for t in victims if t.modified and not t.pinned]
        doomed = [t for t in victims if not t.modified and not t.pinned]
        if not doomed and not skipped:
            return
        current = self._cur_tab()
        self.tabs = [t for t in self.tabs if t not in doomed]
        if current in self.tabs:
            self.cur = self.tabs.index(current)
            self.refresh_tabs()
        else:
            self.cur = -1
            self.switch(self.tabs.index(keep))
        if skipped:
            self.info('Tabs kept', '%d tab(s) with unsaved changes were kept open:\n%s' % (
                len(skipped), '\n'.join(t.name for t in skipped)))

    def close_others(self, keep):
        if keep in self.tabs:
            self._close_many([t for t in self.tabs if t is not keep], keep)

    def close_side(self, keep, side):
        if keep not in self.tabs:
            return
        idx = self.tabs.index(keep)
        self._close_many(self.tabs[:idx] if side == 'left' else self.tabs[idx + 1:], keep)

    # ================= editor view =================
    def _rebuild_editor_view(self):
        self.editor_host.clear_widgets()
        self.editor.readonly = not self.edit_mode
        if self.edit_mode:
            self.editor_host.add_widget(self.editor)
        else:
            self.editor.focus = False
            self._refresh_color()
            self.editor_host.add_widget(self.color_sv)

    def _char_width(self, font_px):
        try:
            lab = CoreLabel(text='M' * 20, font_name=CODE_FONT, font_size=font_px)
            lab.refresh()
            return lab.texture.size[0] / 20.0
        except Exception:
            return font_px * 0.6

    def _size_color_view(self):
        font_px = sp(self.settings['font_size'])
        need = (self._color_chars + 2) * self._char_width(font_px) + dp(24)
        self.color_rv.width = max(self.color_sv.width, need)

    def _refresh_color(self):
        t = self._cur_tab()
        font_px = sp(self.settings['font_size'])
        if t is None:
            self.color_rv.data = []
            return
        lines = hilite_lines(self.editor.text, lang_for(t.path) if t.path else 'python', self.tab_width())
        raw_longest = max((len(l) for l in self.editor.text.split('\n')), default=0)
        self._color_chars = min(raw_longest, MAX_VIEW_LINE) + len(str(len(lines))) + 4
        self.color_layout.default_size = (None, int(font_px * 1.45))
        self.color_rv.data = [{'text': m, 'font_size': font_px} for m in lines]
        self._size_color_view()
        self.color_rv.scroll_y = 1
        self.color_sv.scroll_x = 0

    def _replace_range(self, start, end, new):
        """Replace text[start:end] through the editor's own API so undo/redo keep working."""
        ed = self.editor
        ed.cancel_selection()
        if end > start:
            ed.select_text(start, end)
            ed.delete_selection()
        ed.cursor = ed.get_cursor_from_index(start)
        if new:
            TextInput.insert_text(ed, new)

    def _set_whole_text(self, text, cursor=None):
        """Replace the whole document (undo history cannot survive this)."""
        if cursor is None:
            cursor = self.editor.cursor_index()
        self.editor.cancel_selection()
        self.editor.text = text
        self.editor.reset_undo()
        self._set_cursor(cursor)

    def sym_key(self, s):
        self._ensure_edit()
        ed = self.editor
        if s == 'Undo':
            self.undo()
        elif s == 'Redo':
            self.redo()
        elif s == 'Tab':
            ed.insert_text('\t')            # CodeEditor turns it into spaces up to the next tab stop
        elif s == '<Tab':
            idx = ed.cursor_index()
            text = ed.text
            ls = text.rfind('\n', 0, idx) + 1
            n = 0
            while n < self.tab_width() and text[ls + n:ls + n + 1] == ' ':
                n += 1
            if n:
                self._replace_range(ls, ls + n, '')
                self._set_cursor(max(ls, idx - n))
        else:
            ed.insert_text(s)
        ed.focus = True

    def select_all(self):
        self._ensure_edit()
        self.editor.focus = True
        self.editor.select_all()

    def undo(self):
        try:
            self.editor.do_undo()
        except Exception as exc:
            self.console_write('Undo: %s' % exc, 'warning')

    def redo(self):
        try:
            self.editor.do_redo()
        except Exception as exc:
            self.console_write('Redo: %s' % exc, 'warning')

    def format_doc(self):
        t = self._cur_tab()
        if t is None:
            return
        self._ensure_edit()
        text = self.editor.text
        if (t.path or '').lower().endswith('.json'):
            try:
                new = json.dumps(json.loads(text), ensure_ascii=False, indent=2) + '\n'
            except Exception as exc:
                self.info('Format', 'This is not valid JSON:\n%s' % exc)
                return
        else:
            new = '\n'.join(line.rstrip() for line in text.split('\n'))
        if new == text:
            self.console_write('Nothing to format.', 'system')
            return
        self._set_whole_text(new)
        self.console_write('Formatted.', 'system')

    # ================= find / replace / goto =================
    def find_popup(self):
        self._find_dialog(False)

    def replace_popup(self):
        self._find_dialog(True)

    def _find_dialog(self, with_replace):
        self._ensure_edit()
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        style = dict(multiline=False, size_hint_y=None, height=dp(44), write_tab=False,
                     background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR),
                     background_normal='', background_active='')
        find_in = TextInput(hint_text='Find', text=self.editor.selection_text.split('\n')[0][:80], **style)
        box.add_widget(find_in)
        rep_in = TextInput(hint_text='Replace with', **style)
        if with_replace:
            box.add_widget(rep_in)
        info = Label(text='', color=rgba(TEXT), size_hint_y=None, height=dp(20), font_size=sp(12))
        box.add_widget(info)
        row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        case_b = Btn(text='Aa: off', size_hint_x=0.7)
        prv, nxt = Btn(text='Prev'), FlatBtn(text='Next')
        for w in (case_b, prv, nxt):
            row.add_widget(w)
        box.add_widget(row)
        if with_replace:
            row2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            rep, rep_all = Btn(text='Replace'), Btn(text='Replace all')
            row2.add_widget(rep)
            row2.add_widget(rep_all)
            box.add_widget(row2)
        close = Btn(text='Close')
        box.add_widget(close)
        box.add_widget(BoxLayout())
        # docked at the top, see-through backdrop: the match stays visible in the editor below
        p = self._popup('Find & Replace' if with_replace else 'Find', box, size_hint=(1, None),
                        height=dp(340) if with_replace else dp(250), pos_hint={'top': 1},
                        overlay_color=(0, 0, 0, 0), auto_dismiss=False)
        state = {'case': False}

        def pattern():
            return re.compile(re.escape(find_in.text), 0 if state['case'] else re.IGNORECASE)

        def flip_case(*_):
            state['case'] = not state['case']
            case_b.text = 'Aa: on' if state['case'] else 'Aa: off'

        def go(forward):
            if not find_in.text:
                return
            total = len(pattern().findall(self.editor.text))
            found = self.find_in_editor(find_in.text, forward, state['case'])
            info.text = ('%d match(es)' % total) if found else 'not found'

        def replace_one(*_):
            if not find_in.text:
                return
            ed = self.editor
            pat = pattern()
            start, end = sorted((ed.selection_from, ed.selection_to)) if ed.selection_text else (None, None)
            if start is None or not pat.fullmatch(ed.text[start:end]):
                go(True)                     # first tap selects the next match, second tap replaces it
                return
            self._replace_range(start, end, rep_in.text)
            self._set_cursor(start + len(rep_in.text))
            if not self.find_in_editor(find_in.text, True, state['case']):
                info.text = 'replaced; no more matches'
            else:
                info.text = 'replaced'

        def replace_all(*_):
            if not find_in.text:
                return
            new, count = pattern().subn(lambda m: rep_in.text, self.editor.text)
            if count:
                self._set_whole_text(new)
            info.text = '%d replaced' % count

        case_b.bind(on_release=flip_case)
        nxt.bind(on_release=lambda *_: go(True))
        prv.bind(on_release=lambda *_: go(False))
        find_in.bind(on_text_validate=lambda *_: go(True))
        if with_replace:
            rep.bind(on_release=replace_one)
            rep_all.bind(on_release=replace_all)
        close.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def find_in_editor(self, needle, forward=True, case=False):
        if not needle:
            return False
        ed = self.editor
        text = ed.text
        pat = re.compile(re.escape(needle), 0 if case else re.IGNORECASE)
        if ed.selection_text:
            sel_a, sel_b = sorted((ed.selection_from, ed.selection_to))
        else:
            sel_a = sel_b = ed.cursor_index()
        if forward:
            m = pat.search(text, sel_b) or pat.search(text)
        else:
            m = None
            for cand in pat.finditer(text):
                if cand.start() >= sel_a and m is not None:
                    break
                m = cand
                if cand.start() >= sel_a:
                    m = None
                    break
            if m is None:                    # wrap around to the last match in the file
                for cand in pat.finditer(text):
                    m = cand
        if m is None:
            return False
        self._ensure_edit()
        ed.cancel_selection()
        self._set_cursor(m.end())
        try:
            ed.select_text(m.start(), m.end())
        except Exception:
            pass
        return True

    def _line_start(self, n):
        text = self.editor.text
        pos = 0
        for _ in range(max(0, n - 1)):
            nxt = text.find('\n', pos)
            if nxt < 0:
                break
            pos = nxt + 1
        return pos

    def goto_popup(self):
        def go(value):
            try:
                n = max(1, int(value))
            except ValueError:
                self.info('Go to line', 'Please enter a number.')
                return
            self._goto_line_num(n)
        self.ask_text('Go to line', 'Line number (1 - %d):' % (self.editor.text.count('\n') + 1), go)

    def _goto_line_num(self, n):
        self._ensure_edit()
        self._set_cursor(self._line_start(n))
        self.editor.focus = True

    # ================= files =================
    def open_path(self, path, quiet=False):
        """Open a file in a new tab (or focus its tab). Returns True on success."""
        path = os.path.abspath(path)
        for i, t in enumerate(self.tabs):
            if t.path == path:
                self.switch(i)
                return True
        try:
            text, enc, newline = read_text_file(path)
        except Exception as exc:
            if not quiet:
                self.info('Open failed', '%s\n\n%s' % (path, exc))
            self.console_write('Open failed: %s (%s)' % (path, exc), 'stderr')
            return False
        self._drop_blank_untitled()
        self._stash()
        tab = Tab(path, text)
        tab.encoding, tab.newline = enc, newline
        self.tabs.append(tab)
        self._add_recent(path)
        self.switch(len(self.tabs) - 1)
        self.console_write('Opened %s' % path, 'system')
        if enc == 'latin-1':
            self.console_write('%s is not UTF-8; it was opened byte-for-byte as Latin-1.' % tab.name, 'warning')
        return True

    def _add_recent(self, path):
        rec = [path] + [p for p in self.settings.get('recent', []) if p != path]
        self.settings['recent'] = rec[:15]
        self.save_settings()

    def open_recent(self):
        items = [(os.path.basename(p) + '   ' + os.path.dirname(p), (lambda pp=p: self.open_path(pp)))
                 for p in self.settings.get('recent', []) if os.path.isfile(p)]
        if not items:
            self.info('Open recent', 'No recent files yet.')
            return
        self.list_menu('Open recent', items[:12])

    def save(self):
        t = self._cur_tab()
        if t is None:
            return
        if t.path is None:
            self.save_as(t)
        else:
            self.save_tab(t)

    def save_all(self):
        saved = 0
        unnamed = 0
        for t in list(self.tabs):
            if not t.modified:
                continue
            if t.path:
                saved += 1 if self.save_tab(t) else 0
            else:
                unnamed += 1
        msg = '%d file(s) saved.' % saved
        if unnamed:
            msg += ' %d untitled tab(s) need "Save as".' % unnamed
        self.console_write(msg, 'system')
        self.status.text = msg

    def save_tab(self, tab):
        """Write a tab that already has a path. Returns True on success."""
        if isinstance(tab, int):
            if not (0 <= tab < len(self.tabs)):
                return False
            tab = self.tabs[tab]
        if tab is self._cur_tab():
            self._stash()
        if not tab.path:
            self.save_as(tab)
            return False
        try:
            used = write_text_file(tab.path, tab.text, tab.encoding, tab.newline)
        except Exception as exc:
            self.info('Save failed', '%s\n\n%s' % (tab.path, exc))
            return False
        if used != tab.encoding:
            self.console_write('%s now contains characters outside %s; saved as UTF-8.' % (tab.name, tab.encoding),
                               'warning')
            tab.encoding = used
        tab.modified = False
        self.refresh_tabs()
        self._add_recent(tab.path)
        self.console_write('Saved %s' % tab.path, 'system')
        return True

    def save_as(self, tab=None, after=None):
        if tab is None:
            tab = self._cur_tab()
        elif isinstance(tab, int):
            tab = self.tabs[tab] if 0 <= tab < len(self.tabs) else None
        if tab is None or tab not in self.tabs:
            return
        default = tab.path or os.path.join(self.start_dir(), tab.hint + '.py')

        def write(path):
            old = tab.path
            tab.path = path
            if self.save_tab(tab):
                if after is not None:
                    after()
            else:
                tab.path = old              # a failed save must not leave the tab pointing at a wrong file
                self.refresh_tabs()

        def got(value):
            path = os.path.expanduser(value)
            if not os.path.isabs(path):
                path = os.path.join(os.path.dirname(default), path)
            path = os.path.abspath(path)
            if os.path.isdir(path):
                self.info('Save as', 'That path is a folder:\n%s' % path)
                return
            if any(o is not tab and o.path == path for o in self.tabs):
                self.info('Save as', 'That file is open in another tab. Close it first.')
                return
            if os.path.exists(path) and path != tab.path:
                self.choice('Overwrite?', '%s already exists.\nReplace it?' % os.path.basename(path),
                            [('Cancel', None), ('Replace', lambda: write(path))])
            else:
                write(path)
        self.ask_text('Save as', 'Full path, or just a file name to save in\n%s' % os.path.dirname(default), got,
                      initial=default)

    # ================= sidebar =================
    def show_sidebar(self):
        mv = ModalView(size_hint=(0.88, 1), pos_hint={'x': 0}, background='', background_color=rgba(SIDE))
        col = BoxLayout(orientation='vertical', spacing=dp(4), padding=[dp(6), dp(6)])
        nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        body = BoxLayout(orientation='vertical', spacing=dp(4))
        col.add_widget(nav)
        col.add_widget(body)
        mv.add_widget(col)
        buttons = {}

        def show(view):
            self.search_token = None           # stops a running search
            body.clear_widgets()
            for name, b in buttons.items():
                b.background_color = rgba(ACCENT if name == view else BTN)
            if view == 'files':
                self._files_view(body)
            else:
                self._search_view(body)

        for text, view in (('Files', 'files'), ('Search in files', 'search')):
            buttons[view] = Btn(text=text, font_size=sp(12), on_release=lambda _b, v=view: show(v))
            nav.add_widget(buttons[view])
        nav.add_widget(Btn(text='Close', font_size=sp(12), size_hint_x=0.5, on_release=lambda *_: mv.dismiss()))

        def closed(*_):
            self.search_token = None
            self.explorer_fc = None
            self.sidebar = None
        mv.bind(on_dismiss=closed)
        self.sidebar = mv
        show('files')
        self.open_modal(mv)

    def show_files(self):
        self.show_sidebar()

    def _close_sidebar(self):
        if self.sidebar is not None:
            self.sidebar.dismiss()

    def _files_view(self, parent):
        start = self.start_dir()
        t = self._cur_tab()
        if t is not None and t.path and os.path.isdir(os.path.dirname(t.path)):
            start = os.path.dirname(t.path)
        # no extension filter: every file is listed; binary files are refused when opened.
        # dirselect lets a folder be selected for Rename / Delete (double tap or "Open" enters it).
        fc = FileChooserListView(path=start, dirselect=True)
        self.explorer_fc = fc
        where = Label(text=start, color=rgba(MUTED), font_size=sp(11), size_hint_y=None, height=dp(20),
                      halign='left', valign='middle', shorten=True, shorten_from='left')
        where.bind(size=lambda w, s: setattr(w, 'text_size', s))
        fc.bind(path=lambda _w, v: setattr(where, 'text', v))
        fc.bind(on_submit=lambda _w, sel, _touch: self._fc_open())
        quick = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        places = [('Up', 'up'), ('App folder', str(self.projects_dir))]
        if shared_storage():
            places.insert(1, ('Storage', shared_storage()))
        for text, target in places:
            quick.add_widget(Btn(text=text, font_size=sp(12), on_release=lambda _b, tg=target: self._fc_go(tg)))
        parent.add_widget(quick)
        parent.add_widget(where)
        parent.add_widget(fc)
        acts = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        acts.add_widget(FlatBtn(text='Open', font_size=sp(12), on_release=lambda *_: self._fc_open()))
        acts.add_widget(Btn(text='New', font_size=sp(12), on_release=lambda *_: self._fc_new_file()))
        acts.add_widget(Btn(text='Folder', font_size=sp(12), on_release=lambda *_: self._fc_new_folder()))
        acts.add_widget(Btn(text='Rename', font_size=sp(12), on_release=lambda *_: self._fc_rename()))
        acts.add_widget(Btn(text='Delete', font_size=sp(12), on_release=lambda *_: self._fc_delete()))
        parent.add_widget(acts)

    def _fc_go(self, target):
        if self.explorer_fc is None:
            return
        if target == 'up':
            target = os.path.dirname(self.explorer_fc.path.rstrip('/')) or '/'
        if not (target and os.path.isdir(target)):
            return
        try:
            os.listdir(target)
        except OSError:
            self.info('Files', 'Android does not allow this app to read:\n%s' % target)
            return
        self.explorer_fc.selection = []
        self.explorer_fc.path = target

    def _fc_dir(self):
        return self.explorer_fc.path if self.explorer_fc else self.start_dir()

    def _fc_sel(self):
        if self.explorer_fc and self.explorer_fc.selection:
            return self.explorer_fc.selection[0]
        return None

    def _fc_refresh(self):
        fc = self.explorer_fc
        if fc is None:
            return
        fc.selection = []
        try:
            fc._update_files()
        except Exception:
            path = fc.path                     # public fallback: leave and re-enter the folder
            fc.path = os.path.dirname(path) or '/'
            fc.path = path

    def _fc_open(self):
        sel = self._fc_sel()
        if sel and os.path.isfile(sel):
            if self.open_path(sel):
                self._close_sidebar()
        elif sel and os.path.isdir(sel):
            self._fc_go(sel)
        else:
            self.info('Open', 'Select a file first.')

    def _fc_new_file(self):
        folder = self._fc_dir()

        def got(name):
            try:
                problem = name_error(name)
                if problem:
                    raise FileProblem(problem)
                path = os.path.join(folder, name)
                if os.path.lexists(path):
                    raise FileProblem('"%s" already exists.' % name)
                with open(path, 'x', encoding='utf-8'):
                    pass
                self._fc_refresh()
                if self.open_path(path):
                    self._close_sidebar()
            except Exception as exc:
                self.info('New file failed', str(exc))
        self.ask_text('New file', 'File name (e.g. main.py):', got)

    def _fc_new_folder(self):
        folder = self._fc_dir()

        def got(name):
            try:
                problem = name_error(name)
                if problem:
                    raise FileProblem(problem)
                os.mkdir(os.path.join(folder, name))
                self._fc_refresh()
            except FileExistsError:
                self.info('New folder failed', '"%s" already exists.' % name)
            except Exception as exc:
                self.info('New folder failed', str(exc))
        self.ask_text('New folder', 'Folder name:', got)

    def _fc_rename(self):
        sel = self._fc_sel()
        if not sel:
            self.info('Rename', 'Select a file or folder first.')
            return

        def got(name):
            try:
                self._rename_path(sel, name)
                self._fc_refresh()
            except Exception as exc:
                self.info('Rename failed', str(exc))
        self.ask_text('Rename', 'New name:', got, initial=os.path.basename(sel))

    def _fc_delete(self):
        sel = self._fc_sel()
        if not sel:
            self.info('Delete', 'Select a file or folder first.')
            return
        protected = {os.path.abspath(p) for p in ('/', '/sdcard', '/storage', '/storage/emulated',
                                                  '/storage/emulated/0', os.path.expanduser('~'),
                                                  str(self.home), str(self.projects_dir))}
        if os.path.abspath(sel) in protected:
            self.info('Delete', 'This folder is protected and cannot be deleted from here.')
            return
        is_dir = os.path.isdir(sel) and not os.path.islink(sel)
        prefix = sel.rstrip(os.sep) + os.sep
        affected = [t for t in self.tabs if t.path and (t.path == sel or t.path.startswith(prefix))]
        text = 'Delete %s permanently?' % os.path.basename(sel)
        if is_dir:
            try:
                count = sum(len(files) + len(dirs) for _r, dirs, files in os.walk(sel))
            except Exception:
                count = 0
            text = 'Delete the FOLDER %s and the %d item(s) inside it permanently?' % (os.path.basename(sel), count)
        if affected:
            text += '\n%d open tab(s) will keep their text as unsaved.' % len(affected)

        def go():
            try:
                if is_dir:
                    shutil.rmtree(sel)
                else:
                    os.remove(sel)
            except Exception as exc:
                self.info('Delete failed', str(exc))
            # open tabs keep their text but are detached, so "Save" can never silently re-create the file
            for t in affected:
                if not os.path.exists(t.path):
                    t.hint = Path(t.path).name
                    t.path = None
                    t.modified = True
            self.settings['recent'] = [p for p in self.settings.get('recent', []) if os.path.exists(p)]
            self.save_settings()
            self._fc_refresh()
            self.refresh_tabs()
        self.choice('Delete', text, [('Cancel', None), ('Delete', go)])

    # ---- search in project (background thread)
    def _search_view(self, parent):
        t = self._cur_tab()
        root = os.path.dirname(t.path) if t is not None and t.path else self._fc_dir()
        q = TextInput(hint_text='Search in files, then press Enter', multiline=False, size_hint_y=None,
                      height=dp(44), write_tab=False, background_color=rgba(EDIT_LINE),
                      foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR), background_normal='',
                      background_active='')
        go_b = FlatBtn(text='Search', size_hint_x=None, width=dp(80), height=dp(44))
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        top.add_widget(q)
        top.add_widget(go_b)
        status = Label(text='Folder: %s' % root, color=rgba(MUTED), size_hint_y=None, height=dp(24),
                       font_size=sp(11), halign='left', valign='middle', shorten=True, shorten_from='left')
        status.bind(size=lambda w, s: setattr(w, 'text_size', s))
        sv = ScrollView(bar_width=dp(3))
        results = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
        results.bind(minimum_height=results.setter('height'))
        sv.add_widget(results)
        parent.add_widget(top)
        parent.add_widget(status)
        parent.add_widget(sv)

        def show_hits(token, hits, files_seen, finished, capped):
            if self.search_token is not token:
                return                         # sidebar closed or a newer search started
            for path, ln, line in hits:
                b = Btn(text='%s:%d  %s' % (os.path.basename(path), ln, line), height=dp(40), font_size=sp(11),
                        halign='left', valign='middle', shorten=True, shorten_from='right')
                b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(8), s[1])))
                b.bind(on_release=lambda _b, p=path, l=ln: self._open_at_line(p, l))
                results.add_widget(b)
            if finished:
                status.text = '%d result(s) in %d file(s)%s' % (len(results.children), files_seen,
                                                                ' - limit reached' if capped else '')
            else:
                status.text = 'Searching... %d file(s)' % files_seen

        def worker(token, needle):
            hits, total, files_seen, capped = [], 0, 0, False
            try:
                for folder, dirs, files in os.walk(root):
                    dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in SEARCH_SKIP_DIRS)
                    for fn in sorted(files):
                        if self.search_token is not token:
                            return
                        if not fn.lower().endswith(SEARCH_EXTS):
                            continue
                        path = os.path.join(folder, fn)
                        try:
                            if os.path.getsize(path) > MAX_FILE_BYTES:
                                continue
                            files_seen += 1
                            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                                for ln, line in enumerate(f, 1):
                                    if needle in line.lower():
                                        hits.append((path, ln, line.strip()[:80]))
                                        total += 1
                                        if total >= SEARCH_MAX_HITS:
                                            break
                        except OSError:
                            continue
                        if len(hits) >= 20:
                            batch, hits = hits, []
                            Clock.schedule_once(lambda d, b=batch, n=files_seen: show_hits(token, b, n, False,
                                                                                           False), 0)
                        if total >= SEARCH_MAX_HITS or files_seen >= SEARCH_MAX_FILES:
                            capped = True
                            break
                    if capped:
                        break
            finally:
                if self.search_token is token:
                    Clock.schedule_once(lambda d: show_hits(token, hits, files_seen, True, capped), 0)

        def run(*_):
            needle = q.text.strip().lower()
            results.clear_widgets()
            if not needle:
                return
            token = object()
            self.search_token = token
            status.text = 'Searching...'
            threading.Thread(target=worker, args=(token, needle), daemon=True).start()
        q.bind(on_text_validate=run)
        go_b.bind(on_release=run)

    def _open_at_line(self, path, line):
        if self.open_path(path):
            self._close_sidebar()
            Clock.schedule_once(lambda d: self._goto_line_num(line), 0.2)

    # ================= run / preview / terminal =================
    def _run_sink(self, s):
        with self.run_lock:
            self.run_buf.append(s)
            if len(self.run_buf) > 5000:       # a runaway print loop must not eat all memory
                del self.run_buf[:2500]

    def _drain_run(self, *_):
        with self.run_lock:
            chunk, self.run_buf[:] = ''.join(self.run_buf), []
        if chunk:
            self.console_raw(chunk[-20000:])
        if self.run_thread is not None and not self.run_thread.is_alive():
            self._run_finished()

    def _run_finished(self):
        if self.run_poll is not None:
            self.run_poll.cancel()
            self.run_poll = None
        self.run_thread = None
        if self._streams is not None:
            out, err, old_out, old_err = self._streams
            if sys.stdout is out:
                sys.stdout = old_out
            if sys.stderr is err:
                sys.stderr = old_err
            self._streams = None
        with self.run_lock:
            chunk, self.run_buf[:] = ''.join(self.run_buf), []
        if chunk:
            self.console_raw(chunk[-20000:])
        self.console_write('--- done ---', 'system')

    def run_python(self):
        """Run the current tab as a Python script in a background thread (the UI stays responsive)."""
        t = self._cur_tab()
        if t is None:
            return
        if self.run_thread is not None:
            self.info('Run Python', 'A script is still running. Use "Stop script" in the menu first.')
            return
        self._stash()
        self.show_console()
        self.console_write('--- run %s ---' % t.name, 'system')
        code_text = t.text
        label = t.path or t.name
        folder = os.path.dirname(t.path) if t.path else None

        def no_input(prompt=''):
            raise RuntimeError('input() is not available in the Tataloo Code console.')

        out = _ThreadStream(sys.stdout, self._run_sink)
        err = _ThreadStream(sys.stderr, self._run_sink)
        self._streams = (out, err, sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = out, err

        def worker():
            tid = threading.get_ident()
            out.thread_id = err.thread_id = tid
            g = {'__name__': '__main__', '__file__': label, '__builtins__': __builtins__, 'input': no_input}
            added = False
            try:
                if folder and folder not in sys.path:
                    sys.path.insert(0, folder)
                    added = True
                exec(compile(code_text, label, 'exec'), g)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    self._run_sink('(exit code %s)\n' % (exc.code,))
            except KeyboardInterrupt:
                self._run_sink('(stopped)\n')
            except BaseException:
                self._run_sink(traceback.format_exc())
            finally:
                if added:
                    try:
                        sys.path.remove(folder)
                    except ValueError:
                        pass

        self.run_thread = threading.Thread(target=worker, daemon=True, name='tataloo-run')
        self.run_thread.start()
        self.run_poll = Clock.schedule_interval(self._drain_run, 0.1)

    def stop_python(self):
        th = self.run_thread
        if th is None or not th.is_alive():
            return
        # raises KeyboardInterrupt inside the script thread at its next Python instruction
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(th.ident), ctypes.py_object(KeyboardInterrupt))
        self.console_write('Stop requested...', 'warning')

    def preview_html(self):
        t = self._cur_tab()
        if t is None:
            return
        if not t.path:
            self.info('Preview', 'Save the file first (Save as).')
            return
        if t.modified and not self.save_tab(t):
            return
        folder = os.path.dirname(t.path)
        name = os.path.basename(t.path)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        self.stop_server(quiet=True)
        handler = functools.partial(Quiet, directory=folder)
        server = None
        for port in (PORT, 0):                 # 0 = let the system pick a free port
            try:
                server = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
                break
            except OSError as exc:
                last = exc
        if server is None:
            self.info('Preview failed', 'Could not start the local server:\n%s\n\n'
                                        'On Android the app needs the INTERNET permission (see buildozer.spec).'
                      % last)
            return
        server.daemon_threads = True
        self.server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:%d/%s' % (server.server_address[1], urllib.parse.quote(name))
        self.console_write('Preview: %s' % url, 'system')
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as exc:
            self.info('Preview', 'Server is running, open this address in a browser:\n%s\n\n(%s)' % (url, exc))

    def stop_server(self, quiet=False):
        server, self.server = self.server, None
        if server is None:
            return

        def shut():
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
        threading.Thread(target=shut, daemon=True).start()   # shutdown() blocks, keep it off the UI thread
        if not quiet:
            self.console_write('Preview server stopped.', 'warning')

    def terminal_popup(self):
        t = self._cur_tab()
        cwd = os.path.dirname(t.path) if t is not None and t.path and os.path.isdir(os.path.dirname(t.path)) \
            else str(self.projects_dir)

        def go(cmd):
            self.show_console()
            self.console_write('%s $ %s' % (cwd, cmd), 'system')

            def worker():
                try:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='replace',
                                         timeout=60, cwd=cwd, stdin=subprocess.DEVNULL)
                    text = (res.stdout + res.stderr)[-20000:]
                    if res.returncode != 0 or not text:
                        text += '(exit %s)\n' % res.returncode
                except subprocess.TimeoutExpired:
                    text = 'Stopped: the command ran longer than 60 seconds.\n'
                except Exception as exc:
                    text = 'Error: %s\n' % exc
                Clock.schedule_once(lambda d: self.console_raw(text), 0)
            threading.Thread(target=worker, daemon=True).start()
        self.ask_text('Terminal command', 'One command, max 60 s, not interactive (e.g. ls -la)', go)

    # ================= console =================
    def show_console(self):
        if self.console_pop is None:
            box = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(6))
            bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            clear_b = Btn(text='Clear', font_size=sp(12))
            copy_b = Btn(text='Copy', font_size=sp(12))
            stop_b = Btn(text='Stop script', font_size=sp(12))
            close_b = FlatBtn(text='Close', font_size=sp(12))
            for w in (clear_b, copy_b, stop_b, close_b):
                bar.add_widget(w)
            box.add_widget(bar)
            box.add_widget(self.console_out)
            p = self._popup('Console', box, size_hint=(0.98, 0.6))
            clear_b.bind(on_release=lambda *_: setattr(self.console_out, 'text', ''))
            copy_b.bind(on_release=lambda *_: self._copy(self.console_out.text))
            stop_b.bind(on_release=lambda *_: self.stop_python())
            close_b.bind(on_release=lambda *_: p.dismiss())
            self.console_pop = p
        self.open_modal(self.console_pop)

    def console_raw(self, text):
        """Append text as-is (main thread only). Keeps roughly the last 2000 lines."""
        if not text:
            return
        if not text.endswith('\n'):
            text += '\n'
        full = self.console_out.text + text
        if full.count('\n') > 3000:
            full = '\n'.join(full.split('\n')[-2000:])
        self.console_out.text = full
        self.console_out.cursor = self.console_out.get_cursor_from_index(len(full))

    def console_write(self, text, tag='stdout'):
        prefix = {'stderr': '[ERR] ', 'warning': '[WARN] ', 'system': '[SYS] '}.get(tag, '')
        self.console_raw('[%s] %s%s' % (dt_now(), prefix, text))

    # ================= settings / help / exit =================
    def _apply_font(self):
        size = sp(self.settings['font_size'])
        self.editor.font_size = size
        if not self.edit_mode:
            self._refresh_color()

    def show_settings(self):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        size_lbl = Label(text='Font size: %s' % self.settings['font_size'], color=rgba(WHITE),
                         size_hint_y=None, height=dp(30))
        box.add_widget(size_lbl)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        minus, plus = Btn(text='Smaller'), Btn(text='Bigger')
        row.add_widget(minus)
        row.add_widget(plus)
        box.add_widget(row)

        def change(delta):
            self.settings['font_size'] = max(9, min(30, int(self.settings['font_size']) + delta))
            size_lbl.text = 'Font size: %s' % self.settings['font_size']
            self._apply_font()
            self.save_settings()
        minus.bind(on_release=lambda *_: change(-1))
        plus.bind(on_release=lambda *_: change(1))

        def toggle(key, label):
            b = Btn(text='%s: %s' % (label, 'on' if self.settings.get(key) else 'off'))

            def flip(*_):
                self.settings[key] = not self.settings.get(key)
                b.text = '%s: %s' % (label, 'on' if self.settings.get(key) else 'off')
                if key == 'wrap' and hasattr(self.editor, 'do_wrap'):
                    self.editor.do_wrap = bool(self.settings['wrap'])
                self.save_settings()
            b.bind(on_release=flip)
            return b
        if hasattr(self.editor, 'do_wrap'):
            box.add_widget(toggle('wrap', 'Word wrap'))
        box.add_widget(toggle('auto_indent', 'Auto indent'))

        tw = Btn(text='Tab width: %s (tap to change)' % self.settings['tab_width'])

        def tw_change(*_):
            self.settings['tab_width'] = {2: 4, 4: 8}.get(self.tab_width(), 2)
            tw.text = 'Tab width: %s (tap to change)' % self.settings['tab_width']
            self.save_settings()
        tw.bind(on_release=tw_change)
        box.add_widget(tw)

        close = FlatBtn(text='Close')
        box.add_widget(close)
        p = self._popup('Settings', box, size_hint=(0.92, None), height=dp(420))
        close.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def show_help(self):
        self.info('Help', (
            '%s\n\n'
            'Top bar\n'
            '  three lines: files and search in files\n'
            '  pencil: file properties (rename, line endings, colour view, format)\n'
            '  three dots: main menu (save, find, run, console, settings)\n\n'
            'Tabs: tap to switch, x to close, + for a new file, dots for more.\n'
            'A star (*) marks unsaved changes.\n\n'
            'Colour view shows the file read-only with syntax colours and line numbers.\n'
            'The key row above the status line types symbols, Undo and Redo.\n\n'
            'With a keyboard: Ctrl+S save, Ctrl+F find, Ctrl+H replace, Ctrl+G go to line,\n'
            'Ctrl+N new, Ctrl+W close, Ctrl+Z / Ctrl+R undo / redo.\n\n'
            'Unsaved text is kept when the app is closed and restored next time.\n\n'
            'Limits: files up to 2 MB; undo history is per visit of a tab;\n'
            'Run Python uses the Python inside this app (no pip, no input()).' % APP_NAME))

    def exit_app(self):
        unsaved = [t for t in self.tabs if t.modified]
        if not unsaved:
            self.stop()
            return
        self.choice('Exit', '%d tab(s) have unsaved changes.\nThey will be restored next time.' % len(unsaved),
                    [('Cancel', None), ('Exit', self.stop)])

    def _on_key(self, window, key, *args):
        if key != 27:
            return False
        if self.modals:
            self.modals[-1].dismiss()
            return True
        if not self.edit_mode:
            self.toggle_read_only()
            return True
        self.exit_app()
        return True

    # ================= status =================
    def update_status(self):
        try:
            t = self._cur_tab()
            if t is None:
                return
            ed = self.editor
            if getattr(ed, 'do_wrap', False):
                # with wrapping on, cursor_row counts screen rows, so count real lines instead
                idx = ed.cursor_index()
                text = ed.text
                line = text.count('\n', 0, idx) + 1
                col = idx - (text.rfind('\n', 0, idx) + 1) + 1
            else:
                line, col = ed.cursor_row + 1, ed.cursor_col + 1
            self.status.text = '%s   Ln %d, Col %d   %s   %s' % (
                'EDIT' if self.edit_mode else 'VIEW', line, col, 'CRLF' if t.newline == '\r\n' else 'LF',
                t.path or 'not saved yet')
            self.subtitle.text = ('Modified' if t.modified else 'Saved' if t.path else 'New file') + (
                '' if self.edit_mode else '  -  read only')
        except Exception:
            pass


if __name__ == '__main__':
    try:
        TatalooCodeApp().run()
    except Exception:
        save_crash(traceback.format_exc())
        raise
