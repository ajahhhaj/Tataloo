#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tataloo Code - Android editor (Kivy). Layout and colours modelled on Acode."""
import contextlib
import functools
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import traceback
import urllib.parse
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup, get_color_from_hex, platform

APP_NAME = 'tataloo Code'
PORT = 8765
TEXT_EXTS = ('*.py', '*.html', '*.htm', '*.css', '*.js', '*.json', '*.xml', '*.txt', '*.md', '*.sql', '*.sh', '*.csv')
MAX_HILITE = 120000

# ---- Acode-like palette
TOP = '#8D8DF2'
TOP_DARK = '#6E6EDB'
TAB_BG = '#7F7FE6'
TAB_ACTIVE = '#A9A9FF'
SIDE = '#7A7ADB'
STATUS = '#6A6AD4'
EDITOR = '#282C34'
EDIT_LINE = '#2C313C'
KEYBAR = '#21252B'
CONSOLE_BG = '#1B1E24'
WHITE = '#FFFFFF'
TEXT = '#ABB2BF'
CURSOR = '#528BFF'
SEL = '#3E4451'
MUTED = '#9A9AD8'
ERR = '#E06C75'
OK = '#98C379'

# ---- syntax palette (One-Dark style)
C_KW = 'C678DD'
C_BUILTIN = '56B6C2'
C_STR = '98C379'
C_COMMENT = '7F848E'
C_NUM = 'D19A66'
C_FUNC = '61AFEF'
C_CLASS = 'E5C07B'
C_DEC = 'E06C75'
C_TAG = 'E06C75'
C_ATTR = 'D19A66'

PY_KW = set('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'.split())
PY_BUILTIN = set('print len range str int float list dict set tuple bool open input type isinstance super self cls enumerate zip map filter sorted sum min max abs round exec eval'.split())
JS_KW = set('var let const function return if else for while do switch case break continue new this class extends import export async await try catch throw null undefined true false'.split())
HTML_KW = set('html head body div span p a img ul ol li table tr td th script style link meta title h1 h2 h3 h4 h5 h6 input button form'.split())

TOKEN_RE = re.compile(
    r'(#[^\n]*|//[^\n]*)'
    r'|("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`[^`]*`)'
    r'|(@[A-Za-z_][\w.]*)'
    r'|(\b\d+(?:\.\d+)?\b)'
    r'|(\b[A-Za-z_]\w*\b)'
)


def hexonly(h):
    return h.lstrip('#')


def rgba(value, alpha=1.0):
    return tuple(get_color_from_hex(value)[:3]) + (alpha,)


def hilite(text, ext):
    if len(text) > MAX_HILITE:
        return escape_markup(text)
    if ext in ('.html', '.htm'):
        kw = HTML_KW
    elif ext == '.js':
        kw = JS_KW
    else:
        kw = PY_KW
    out = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append(escape_markup(text[pos:m.start()]))
        pos = m.end()
        tok = m.group(0)
        esc = escape_markup(tok)
        if m.group(1):
            out.append('[color=%s][i]%s[/i][/color]' % (C_COMMENT, esc))
        elif m.group(2):
            out.append('[color=%s]%s[/color]' % (C_STR, esc))
        elif m.group(3):
            out.append('[color=%s]%s[/color]' % (C_DEC, esc))
        elif m.group(4):
            out.append('[color=%s]%s[/color]' % (C_NUM, esc))
        else:
            after = text[m.end():m.end() + 1]
            if tok in kw:
                out.append('[color=%s][b]%s[/b][/color]' % (C_KW, esc))
            elif tok in PY_BUILTIN:
                out.append('[color=%s]%s[/color]' % (C_BUILTIN, esc))
            elif ext == '.py' and tok[:1].isupper():
                out.append('[color=%s]%s[/color]' % (C_CLASS, esc))
            elif after == '(':
                out.append('[color=%s]%s[/color]' % (C_FUNC, esc))
            else:
                out.append(esc)
    out.append(escape_markup(text[pos:]))
    return ''.join(out)


def save_crash(text):
    for base in ('/sdcard/Download', '/storage/emulated/0/Download', tempfile.gettempdir()):
        try:
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, 'tataloo_crash.txt'), 'w', encoding='utf-8') as f:
                f.write(text)
            return base
        except Exception:
            continue
    return None


def start_dir():
    for p in ('/storage/emulated/0', '/sdcard'):
        try:
            if os.path.isdir(p):
                return p
        except Exception:
            pass
    return os.path.expanduser('~')


class Panel(BoxLayout):
    def __init__(self, color=TOP, **kw):
        super().__init__(**kw)
        self._color = color
        with self.canvas.before:
            self._c = Color(*rgba(color))
            self._r = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def set_color(self, color):
        self._color = color
        self._c.rgba = rgba(color)

    def _upd(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


class Btn(Button):
    def __init__(self, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', rgba(TAB_BG))
        kw.setdefault('color', rgba(WHITE))
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(42))
        kw.setdefault('font_size', sp(13))
        super().__init__(**kw)


class FlatBtn(Btn):
    def __init__(self, **kw):
        kw.setdefault('background_color', rgba(TOP))
        super().__init__(**kw)


class IconBtn(Button):
    """Top-bar icon drawn with canvas: 'menu' (3 bars), 'dots' (3 dots), 'edit' (pencil)."""

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
        kw.setdefault('background_color', rgba('#2F343E'))
        kw.setdefault('color', rgba(TEXT))
        kw.setdefault('font_size', sp(15))
        super().__init__(**kw)


class CodeEditor(TextInput):
    app_ref = None

    def insert_text(self, substring, from_undo=False):
        if substring == '\n' and not from_undo and self.app_ref is not None and self.app_ref.settings.get('auto_indent', True):
            idx = self.cursor_index()
            text = self.text
            ls = text.rfind('\n', 0, idx) + 1
            line = text[ls:idx]
            indent = re.match(r'[ \t]*', line).group(0)
            if line.rstrip().endswith(':') or line.rstrip().endswith('{'):
                indent += ' ' * int(self.app_ref.settings.get('tab_width', 4))
            return super().insert_text('\n' + indent, from_undo=from_undo)
        return super().insert_text(substring, from_undo=from_undo)


class Tab:
    def __init__(self, path=None, text=''):
        self.path = path
        self.text = text
        self.cursor = 0
        self.modified = False
        self.pinned = False
        self.hint = 'untitled'

    @property
    def name(self):
        return Path(self.path).name if self.path else self.hint


class TataloCodeApp(App):
    title = APP_NAME

    # ================= lifecycle =================
    def build(self):
        try:
            return self._build()
        except Exception:
            err = traceback.format_exc()
            save_crash(err)
            box = BoxLayout(orientation='vertical', padding=dp(8))
            sv = ScrollView()
            lab = Label(text='CRASH REPORT\n\n' + err, color=rgba('#FF3355'), font_size='11sp',
                        size_hint_y=None, halign='left', valign='top')
            lab.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
            lab.bind(texture_size=lambda w, v: setattr(w, 'height', v[1]))
            sv.add_widget(lab)
            box.add_widget(sv)
            return box

    def _build(self):
        Window.clearcolor = rgba(EDITOR)
        Window.softinput_mode = 'below_target'
        self.home = Path(self.user_data_dir)
        self.home.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.home / 'settings.json'
        self.session_path = self.home / 'session.json'
        self.settings = {'font_size': 14, 'wrap': False, 'auto_indent': True, 'tab_width': 4, 'recent': []}
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self.settings.update(data)
        except Exception:
            pass
        self.tabs = []
        self.cur = -1
        self.loading = False
        self.edit_mode = True
        self.modals = []
        self.explorer_fc = None
        self.server = None
        self.find_state = {}

        root = Panel(EDITOR, orientation='vertical')
        self.root_widget = root

        # ---- top bar (Acode style)
        top = Panel(TOP, size_hint_y=None, height=dp(52), spacing=dp(2))
        top.add_widget(IconBtn('menu', on_release=lambda *_: self.show_sidebar()))
        title_box = BoxLayout(orientation='vertical', padding=[dp(4), dp(4)])
        self.title_label = Label(text=APP_NAME, color=rgba(WHITE), bold=True, font_size=sp(16),
                                 halign='left', valign='bottom', size_hint_y=0.6)
        self.subtitle = Label(text='', color=rgba(MUTED), font_size=sp(11), halign='left', valign='top', size_hint_y=0.4)
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
        tabbar.add_widget(IconBtn('dots', width=dp(40), on_release=lambda *_: self.tab_more_menu()))
        root.add_widget(tabbar)

        # ---- editor host
        self.editor_host = BoxLayout()
        root.add_widget(self.editor_host)

        self.editor = CodeEditor(multiline=True, write_tab=False, font_size=sp(self.settings['font_size']),
                                 font_name='Roboto', background_color=rgba(EDITOR),
                                 foreground_color=rgba(TEXT), cursor_color=rgba(CURSOR),
                                 selection_color=rgba(SEL, 0.9), padding=[dp(10), dp(8)])
        self.editor.app_ref = self
        self.editor.bind(text=self._on_text, cursor=self._on_cursor)
        if hasattr(self.editor, 'do_wrap'):
            self.editor.do_wrap = bool(self.settings.get('wrap'))

        self.color_label = Label(text='', markup=True, color=rgba(TEXT), font_size=sp(self.settings['font_size']),
                                 font_name='Roboto', size_hint_y=None, halign='left', valign='top')
        self.color_label.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        self.color_label.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(24)))
        self.color_sv = ScrollView(bar_width=dp(4))
        self.color_sv.add_widget(self.color_label)

        # ---- extra keys bar (Acode style)
        keys_sv = ScrollView(size_hint_y=None, height=dp(42), do_scroll_y=False, bar_width=0)
        keys = BoxLayout(size_hint_x=None, spacing=dp(3), padding=[dp(3), dp(3)])
        keys.bind(minimum_width=keys.setter('width'))
        for s in ['Tab', '<Tab', '(', ')', '[', ']', '{', '}', '<', '>', '=', ':', '"', "'", '.', ',', '_', '-', '+',
                  '*', '/', '\\', '#', '&', '|', '!', '?', '@', '$', '%', ';']:
            keys.add_widget(KeyBtn(text=s, width=dp(58) if len(s) > 1 else dp(44),
                                   on_release=lambda _b, a=s: self.sym_key(a)))
        keys_sv.add_widget(keys)
        root.add_widget(keys_sv)

        # ---- status bar
        status = Panel(STATUS, size_hint_y=None, height=dp(24), padding=[dp(8), 0])
        self.status = Label(text='', color=rgba(WHITE), font_size=sp(11), halign='left')
        self.status.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], s[1])))
        status.add_widget(self.status)
        root.add_widget(status)

        # ---- console (popup, opened from menu)
        self.console_out = TextInput(readonly=True, multiline=True, font_size=sp(11), font_name='Roboto',
                                     background_color=rgba(CONSOLE_BG), foreground_color=rgba(OK),
                                     padding=[dp(8), dp(6)])
        self.console_pop = None

        self._rebuild_editor_view()
        self.new_untitled()
        self.console_write('tataloo Code ready.')
        Clock.schedule_once(self._restore_session, 0.2)
        Clock.schedule_once(self._ask_permissions, 1.0)
        Clock.schedule_interval(lambda dt_: self.update_status(), 1.0)
        Window.bind(on_keyboard=self._on_key)
        return root

    def on_pause(self):
        self.save_session()
        return True

    def on_stop(self):
        self.save_session()

    # ================= settings / session =================
    def save_settings(self):
        try:
            self.settings_path.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            self.console_write('Settings save error: %s' % exc, 'stderr')

    def save_session(self):
        try:
            if self.cur >= 0:
                self._stash()
            active = self.tabs[self.cur].path if 0 <= self.cur < len(self.tabs) else None
            data = {'paths': [t.path for t in self.tabs if t.path], 'active': active}
            self.session_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            self.save_settings()
        except Exception:
            pass

    def _restore_session(self, *_):
        try:
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        for p in data.get('paths', []):
            if p and os.path.isfile(p):
                self.open_path(p, quiet=True)
        active = data.get('active')
        for i, t in enumerate(self.tabs):
            if t.path == active:
                self.switch(i)
                break

    def _ask_permissions(self, *_):
        if platform != 'android':
            return
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        except Exception:
            pass
        try:
            from jnius import autoclass
            Env = autoclass('android.os.Environment')
            Ver = autoclass('android.os.Build$VERSION')
            if Ver.SDK_INT >= 30 and not Env.isExternalStorageManager():
                Intent = autoclass('android.content.Intent')
                Settings = autoclass('android.provider.Settings')
                Uri = autoclass('android.net.Uri')
                act = autoclass('org.kivy.android.PythonActivity').mActivity
                act.startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                                         Uri.parse('package:' + act.getPackageName())))
        except Exception:
            pass

    # ================= popup helpers =================
    def open_modal(self, widget):
        self.modals.append(widget)
        widget.bind(on_dismiss=lambda *_: self.modals.remove(widget) if widget in self.modals else None)
        widget.open()
        return widget

    def info(self, title, text):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        sv = ScrollView()
        lab = Label(text=text, color=rgba(TEXT), font_size=sp(13), size_hint_y=None, halign='left', valign='top')
        lab.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        lab.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(10)))
        sv.add_widget(lab)
        box.add_widget(sv)
        ok = FlatBtn(text='OK')
        box.add_widget(ok)
        p = Popup(title=title, content=box, size_hint=(0.92, 0.7), title_color=rgba(WHITE),
                  separator_color=rgba(TOP), background_color=rgba(EDITOR))
        ok.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def ask_text(self, title, prompt, callback, initial=''):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        box.add_widget(Label(text=prompt, color=rgba(TEXT), size_hint_y=None, height=dp(24), font_size=sp(12)))
        ti = TextInput(text=initial, multiline=False, size_hint_y=None, height=dp(44),
                       background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR))
        box.add_widget(ti)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        ok, cancel = FlatBtn(text='OK'), Btn(text='Cancel')
        row.add_widget(ok)
        row.add_widget(cancel)
        box.add_widget(row)
        p = Popup(title=title, content=box, size_hint=(0.92, None), height=dp(230),
                  title_color=rgba(WHITE), separator_color=rgba(TOP), background_color=rgba(EDITOR))

        def done(*_):
            value = ti.text.strip()
            p.dismiss()
            if value:
                callback(value)
        ok.bind(on_release=done)
        ti.bind(on_text_validate=done)
        cancel.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def confirm(self, title, text, callback):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        box.add_widget(Label(text=text, color=rgba(TEXT), font_size=sp(13), halign='center'))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        yes, no = FlatBtn(text='Yes'), Btn(text='No')
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        p = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(210),
                  title_color=rgba(WHITE), separator_color=rgba(TOP), background_color=rgba(EDITOR))
        yes.bind(on_release=lambda *_: (p.dismiss(), callback(True)))
        no.bind(on_release=lambda *_: (p.dismiss(), callback(False)))
        self.open_modal(p)

    def list_menu(self, title, items):
        """items: list of (label, callback) or (None, None) for a separator/heading (label only)."""
        mv = ModalView(size_hint=(0.82, None), height=dp(56) + dp(44) * min(len(items), 14) + dp(8),
                       background='', background_color=rgba(EDITOR))
        sv = ScrollView()
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2), padding=dp(6))
        box.bind(minimum_height=box.setter('height'))
        head = Label(text=title, color=rgba(TOP), bold=True, size_hint_y=None, height=dp(34), font_size=sp(14),
                     halign='left')
        head.bind(size=lambda w, s: setattr(w, 'text_size', (s[0] - dp(8), s[1])))
        box.add_widget(head)
        for label, fn in items:
            b = Btn(text=label, height=dp(44), halign='left', background_color=rgba('#2F343E'))
            b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(14), s[1])))
            if fn is None:
                b.disabled = True
                b.background_color = rgba(EDITOR)
                b.color = rgba(MUTED)
            else:
                b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), Clock.schedule_once(lambda d: f(), 0.05)))
            box.add_widget(b)
        sv.add_widget(box)
        mv.add_widget(sv)
        self.open_modal(mv)

    # ================= menus =================
    def main_menu(self):
        self.list_menu('tataloo Code', [
            ('Save', self.save), ('Save as', self.save_as), ('Files', self.show_files),
            ('Close file', self.close_current), ('Open recent', self.open_recent),
            ('Find file', self.find_popup), ('Console', self.show_console),
            ('Terminal', self.terminal_popup), ('Running processes', self.show_processes),
            ('Run Python', self.run_python), ('Preview HTML', self.preview_html),
            ('Settings', self.show_settings), ('Help', self.show_help), ('Exit', self.exit_app),
        ])

    def file_properties(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        t = self.tabs[self.cur]
        ext = Path(t.path).suffix.lower() if t.path else '.txt'
        self.list_menu('File properties', [
            ('Rename', self.rename_current),
            ('Syntax highlighting: %s' % self._lang_name(ext), lambda: self.info('Syntax', 'Auto-detected from the file extension.')),
            ('Text encoding: UTF-8', lambda: self.info('Encoding', 'All files are read and saved as UTF-8.')),
            ('New line mode: unix', lambda: self.info('New line', 'LF (unix) line endings are used.')),
            ('Read only: %s' % ('no' if self.edit_mode else 'yes'), self.toggle_read_only),
            ('Format', self.format_doc),
            ('Share path', lambda: self._copy(t.path or t.name)),
            ('Open with', lambda: self.info('Open with', 'Use Files to open this file with another app.')),
            ('File info', self.file_info),
        ])

    def tab_more_menu(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        idx = self.cur
        t = self.tabs[idx]
        self.list_menu(t.name, [
            ('Pin tab / unpin', lambda: self._toggle_pin(idx)),
            ('Close tab', lambda: self.close_index(idx)),
            ('Close Right', lambda: self.close_side(idx, 'right')),
            ('Close Left', lambda: self.close_side(idx, 'left')),
            ('Close Others', lambda: self.close_others(idx)),
            ('Search', self.find_popup),
            ('Goto line', self.goto_popup),
            ('Select all', self.select_all),
            ('Copy path', lambda: self._copy(t.path or t.name)),
        ])

    def _lang_name(self, ext):
        return {'.py': 'python', '.html': 'html', '.htm': 'html', '.css': 'css', '.js': 'javascript',
                '.json': 'json', '.xml': 'xml', '.md': 'markdown', '.sql': 'sql', '.sh': 'shell'}.get(ext, 'plain text')

    def toggle_read_only(self):
        self.edit_mode = not self.edit_mode
        self.editor.readonly = not self.edit_mode
        self.update_status()

    def file_info(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        t = self.tabs[self.cur]
        size = os.path.getsize(t.path) if t.path and os.path.isfile(t.path) else len(t.text.encode('utf-8'))
        self.info('File info', 'Name: %s\nPath: %s\nSize: %s bytes\nLines: %s' % (
            t.name, t.path or '(not saved)', format(size, ','), t.text.count('\n') + 1))

    def rename_current(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        t = self.tabs[self.cur]
        if not t.path:
            self.save_as()
            return

        def got(name):
            new = os.path.join(os.path.dirname(t.path), name)
            try:
                os.rename(t.path, new)
                t.path = new
                self.refresh_tabs()
            except Exception as exc:
                self.info('Rename failed', str(exc))
        self.ask_text('Rename', 'New name:', got, initial=Path(t.path).name)

    def _toggle_pin(self, idx):
        self.tabs[idx].pinned = not self.tabs[idx].pinned
        self.refresh_tabs()

    def _copy(self, text):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            self.console_write('Copied: %s' % text, 'system')
        except Exception as exc:
            self.console_write('Copy failed: %s' % exc, 'stderr')

    # ================= tabs =================
    def refresh_tabs(self):
        self.tab_row.clear_widgets()
        for i, t in enumerate(self.tabs):
            active = i == self.cur
            label = ('* ' if t.modified else '') + t.name
            tab_bg = rgba(TAB_ACTIVE) if active else rgba(TAB_BG)
            b = Btn(text=label, size_hint_x=None, width=dp(140), height=dp(40), background_color=tab_bg,
                    color=rgba(WHITE), font_size=sp(12), halign='center')
            b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(6), s[1])))
            b.bind(on_release=lambda _b, idx=i: self.switch(idx))
            x = Btn(text='x', size_hint_x=None, width=dp(34), height=dp(40), background_color=tab_bg,
                    color=rgba(WHITE))
            x.bind(on_release=lambda _b, idx=i: self.close_index(idx))
            self.tab_row.add_widget(b)
            self.tab_row.add_widget(x)
        if 0 <= self.cur < len(self.tabs):
            self.title_label.text = self.tabs[self.cur].name
        else:
            self.title_label.text = APP_NAME
        self.update_status()

    def _stash(self):
        if 0 <= self.cur < len(self.tabs):
            t = self.tabs[self.cur]
            t.text = self.editor.text
            t.cursor = self.editor.cursor_index()

    def switch(self, idx):
        if not (0 <= idx < len(self.tabs)):
            return
        self._stash()
        self.cur = idx
        t = self.tabs[idx]
        self.loading = True
        self.editor.text = t.text
        self.loading = False
        self._rebuild_editor_view()
        self.refresh_tabs()
        Clock.schedule_once(lambda d: self._set_cursor(t.cursor), 0.05)

    def _set_cursor(self, idx):
        try:
            idx = max(0, min(idx, len(self.editor.text)))
            self.editor.cursor = self.editor.get_cursor_from_index(idx)
        except Exception:
            pass

    def _on_text(self, *_):
        if self.loading or not (0 <= self.cur < len(self.tabs)):
            return
        t = self.tabs[self.cur]
        if not t.modified:
            t.modified = True
            self.refresh_tabs()

    def _on_cursor(self, *_):
        self.update_status()

    def new_untitled(self):
        self._stash()
        t = Tab(None, '')
        t.hint = 'untitled-%d' % (sum(1 for x in self.tabs if not x.path) + 1)
        self.tabs.append(t)
        self.switch(len(self.tabs) - 1)

    def close_index(self, idx):
        if not (0 <= idx < len(self.tabs)):
            return
        t = self.tabs[idx]

        def do_close(save=False):
            if save:
                if idx == self.cur:
                    self._stash()
                if not self.save_tab(idx):
                    return
            self.tabs.pop(idx)
            if not self.tabs:
                self.cur = -1
                self.new_untitled()
                return
            if self.cur == idx:
                self.cur = -1
                self.switch(min(idx, len(self.tabs) - 1))
            else:
                if self.cur > idx:
                    self.cur -= 1
                self.refresh_tabs()
        if t.modified:
            self.confirm('Unsaved changes', 'Save changes to %s before closing?' % t.name, do_close)
        else:
            do_close(False)

    def close_current(self):
        self.close_index(self.cur)

    def close_others(self, keep):
        keep_tab = self.tabs[keep]
        self.tabs = [t for t in self.tabs if t is keep_tab or t.pinned]
        self.cur = self.tabs.index(keep_tab)
        self.refresh_tabs()

    def close_side(self, idx, side):
        keep_tab = self.tabs[idx]
        if side == 'left':
            self.tabs = [t for i, t in enumerate(self.tabs) if i >= idx or t.pinned]
        else:
            self.tabs = [t for i, t in enumerate(self.tabs) if i <= idx or t.pinned]
        self.cur = self.tabs.index(keep_tab)
        self.refresh_tabs()

    # ================= editor view =================
    def _rebuild_editor_view(self):
        self.editor_host.clear_widgets()
        if self.edit_mode:
            self.editor.readonly = False
            self.editor_host.add_widget(self.editor)
        else:
            self._refresh_color()
            self.editor_host.add_widget(self.color_sv)

    def _refresh_color(self):
        if not (0 <= self.cur < len(self.tabs)):
            self.color_label.text = ''
            return
        t = self.tabs[self.cur]
        ext = Path(t.path).suffix.lower() if t.path else '.py'
        self.color_label.text = hilite(self.editor.text if self.editor.parent is not None else t.text, ext)

    def sym_key(self, s):
        if not self.edit_mode:
            self.toggle_read_only()
        if s == 'Tab':
            self.editor.insert_text(' ' * int(self.settings.get('tab_width', 4)))
        elif s == '<Tab':
            ls = self.editor.text.rfind('\n', 0, self.editor.cursor_index()) + 1
            text = self.editor.text
            n = 0
            while n < int(self.settings.get('tab_width', 4)) and text[ls:ls + 1] == ' ':
                text = text[:ls] + text[ls + 1:]
                n += 1
            if n:
                self.editor.text = text
        else:
            self.editor.insert_text(s)
        self.editor.focus = True

    def select_all(self):
        if not self.edit_mode:
            self.toggle_read_only()
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
        if not (0 <= self.cur < len(self.tabs)):
            return
        text = self.editor.text
        path = self.tabs[self.cur].path or ''
        if path.endswith('.json'):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except Exception as exc:
                self.console_write('Format JSON failed: %s' % exc, 'stderr')
                return
        else:
            text = '\n'.join(line.rstrip() for line in text.split('\n'))
        self.editor.text = text
        self.console_write('Formatted.', 'system')

    # ================= find / replace / goto =================
    def find_popup(self):
        self._find_dialog(False)

    def replace_popup(self):
        self._find_dialog(True)

    def _find_dialog(self, with_replace):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(6))
        find_in = TextInput(hint_text='Find', multiline=False, size_hint_y=None, height=dp(44),
                            background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR))
        box.add_widget(find_in)
        rep_in = TextInput(hint_text='Replace with', multiline=False, size_hint_y=None, height=dp(44),
                           background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR))
        if with_replace:
            box.add_widget(rep_in)
        info = Label(text='', color=rgba(TEXT), size_hint_y=None, height=dp(22), font_size=sp(12))
        box.add_widget(info)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        prv, nxt = Btn(text='Prev'), FlatBtn(text='Next')
        row.add_widget(prv)
        row.add_widget(nxt)
        box.add_widget(row)
        if with_replace:
            row2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            rep, rep_all = Btn(text='Replace'), FlatBtn(text='Replace all')
            row2.add_widget(rep)
            row2.add_widget(rep_all)
            box.add_widget(row2)
        close = Btn(text='Close')
        box.add_widget(close)
        p = Popup(title='Find & Replace' if with_replace else 'Find', content=box, size_hint=(0.95, None),
                  height=dp(360) if with_replace else dp(280), title_color=rgba(WHITE),
                  separator_color=rgba(TOP), background_color=rgba(EDITOR))

        def go(forward):
            if find_in.text:
                info.text = 'found' if self.find_in_editor(find_in.text, forward) else 'not found'

        def replace_one(*_):
            needle, rep_text = find_in.text, rep_in.text
            if not needle:
                return
            text = self.editor.text
            start = self.editor.cursor_index()
            i = text.find(needle, start)
            if i < 0:
                i = text.find(needle)
            if i < 0:
                info.text = 'not found'
                return
            self.editor.text = text[:i] + rep_text + text[i + len(needle):]
            self._set_cursor(i + len(rep_text))
            info.text = 'replaced'

        def replace_all(*_):
            needle, rep_text = find_in.text, rep_in.text
            if not needle:
                return
            count = self.editor.text.count(needle)
            self.editor.text = self.editor.text.replace(needle, rep_text)
            info.text = '%d replaced' % count

        nxt.bind(on_release=lambda *_: go(True))
        prv.bind(on_release=lambda *_: go(False))
        find_in.bind(on_text_validate=lambda *_: go(True))
        if with_replace:
            rep.bind(on_release=replace_one)
            rep_all.bind(on_release=replace_all)
        close.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def find_in_editor(self, needle, forward=True):
        text = self.editor.text
        start = self.editor.cursor_index()
        if forward:
            i = text.find(needle, start)
            if i < 0:
                i = text.find(needle)
        else:
            i = text.rfind(needle, 0, max(0, start - 1))
            if i < 0:
                i = text.rfind(needle)
        if i < 0:
            return False
        if not self.edit_mode:
            self.toggle_read_only()
        self._set_cursor(i + len(needle) if forward else i)
        try:
            self.editor.select_text(i, i + len(needle))
        except Exception:
            pass
        return True

    def goto_popup(self):
        def go(value):
            try:
                n = max(1, int(value))
            except ValueError:
                self.info('Go to line', 'Please enter a number.')
                return
            lines = self.editor.text.split('\n')
            n = min(n, len(lines))
            self._set_cursor(sum(len(l) + 1 for l in lines[:n - 1]))
        self.ask_text('Go to line', 'Line number:', go)

    # ================= files =================
    def open_path(self, path, quiet=False):
        path = os.path.abspath(path)
        for i, t in enumerate(self.tabs):
            if t.path == path:
                self.switch(i)
                return
        try:
            text = Path(path).read_bytes().decode('utf-8', errors='replace')
        except Exception as exc:
            if not quiet:
                self.info('Open failed', str(exc))
            self.console_write('Open failed: %s' % exc, 'stderr')
            return
        self._stash()
        self.tabs.append(Tab(path, text))
        self._add_recent(path)
        self.switch(len(self.tabs) - 1)
        self.console_write('Opened %s' % path, 'system')

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
        if not (0 <= self.cur < len(self.tabs)):
            return
        if self.tabs[self.cur].path is None:
            self.save_as()
        else:
            self.save_tab(self.cur)

    def save_tab(self, idx):
        if idx == self.cur:
            self._stash()
        t = self.tabs[idx]
        if not t.path:
            self.save_as(idx)
            return False
        try:
            target = Path(t.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(t.text, encoding='utf-8', newline='\n')
            t.modified = False
            self.refresh_tabs()
            self._add_recent(t.path)
            self.console_write('Saved %s' % t.path, 'system')
            return True
        except Exception as exc:
            self.info('Save failed', str(exc))
            return False

    def save_as(self, idx=None):
        if idx is None:
            idx = self.cur
        if not (0 <= idx < len(self.tabs)):
            return
        t = self.tabs[idx]
        default = t.path or os.path.join(start_dir(), t.hint + '.py')

        def got(path):
            if idx == self.cur:
                self._stash()
            t.path = os.path.abspath(path)
            if self.save_tab(idx):
                self.refresh_tabs()
        self.ask_text('Save as', 'Full path (e.g. /sdcard/Download/app.py):', got, initial=default)

    # ================= sidebar (≡) =================
    def show_sidebar(self):
        mv = ModalView(size_hint=(0.88, 1), anchor_x='left', background='', background_color=rgba(SIDE))
        col = BoxLayout(orientation='vertical', spacing=dp(4), padding=[dp(6), dp(6)])
        nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        body = BoxLayout(orientation='vertical')
        col.add_widget(nav)
        col.add_widget(body)
        mv.add_widget(col)

        def show(view):
            body.clear_widgets()
            if view == 'files':
                self._files_view(body)
            elif view == 'search':
                self._search_view(body)
            elif view == 'alerts':
                body.add_widget(Label(text='No unread notifications', color=rgba(WHITE), font_size=sp(14)))
            elif view == 'favs':
                body.add_widget(Label(text='Favorites are not in this version.', color=rgba(WHITE), font_size=sp(14)))
            elif view == 'plugins':
                body.add_widget(Label(text='Plugin store is not in this version.', color=rgba(WHITE), font_size=sp(14)))

        for text, view in (('Files', 'files'), ('Search', 'search'), ('Alerts', 'alerts'), ('Favs', 'favs'), ('Plugins', 'plugins')):
            nav.add_widget(Btn(text=text, background_color=rgba(TOP), font_size=sp(12),
                               on_release=lambda _b, v=view: show(v)))
        show('files')
        self.open_modal(mv)

    def show_files(self):
        self.show_sidebar()

    def _files_view(self, parent):
        start = start_dir()
        if 0 <= self.cur < len(self.tabs) and self.tabs[self.cur].path:
            start = os.path.dirname(self.tabs[self.cur].path)
        fc = FileChooserListView(path=start, filters=list(TEXT_EXTS))
        self.explorer_fc = fc
        quick = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for text, target in (('Up', 'up'), ('Storage', start_dir()), ('App', self.user_data_dir), ('Home', os.path.expanduser('~'))):
            quick.add_widget(Btn(text=text, background_color=rgba(TOP), font_size=sp(12),
                                 on_release=lambda _b, tg=target: self._fc_go(tg)))
        parent.add_widget(quick)
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
        if target and os.path.isdir(target):
            self.explorer_fc.path = target

    def _fc_dir(self):
        return self.explorer_fc.path if self.explorer_fc else start_dir()

    def _fc_sel(self):
        if self.explorer_fc and self.explorer_fc.selection:
            return self.explorer_fc.selection[0]
        return None

    def _fc_refresh(self):
        try:
            self.explorer_fc._update_files()
        except Exception:
            pass

    def _fc_open(self):
        sel = self._fc_sel()
        if sel and os.path.isfile(sel):
            self.open_path(sel)
        elif sel and os.path.isdir(sel):
            self.explorer_fc.path = sel
        else:
            self.info('Open', 'Select a file first.')

    def _fc_new_file(self):
        def got(name):
            path = os.path.join(self._fc_dir(), name)
            try:
                if os.path.exists(path):
                    raise FileExistsError('File already exists.')
                Path(path).write_text('', encoding='utf-8')
                self._fc_refresh()
                self.open_path(path)
            except Exception as exc:
                self.info('New file failed', str(exc))
        self.ask_text('New file', 'File name (e.g. main.py):', got)

    def _fc_new_folder(self):
        def got(name):
            try:
                os.makedirs(os.path.join(self._fc_dir(), name), exist_ok=False)
                self._fc_refresh()
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
                new = os.path.join(os.path.dirname(sel), name)
                os.rename(sel, new)
                for t in self.tabs:
                    if t.path == sel:
                        t.path = new
                self._fc_refresh()
                self.refresh_tabs()
            except Exception as exc:
                self.info('Rename failed', str(exc))
        self.ask_text('Rename', 'New name:', got, initial=os.path.basename(sel))

    def _fc_delete(self):
        sel = self._fc_sel()
        if not sel:
            self.info('Delete', 'Select a file or folder first.')
            return

        def go(yes):
            if not yes:
                return
            try:
                if os.path.isdir(sel):
                    shutil.rmtree(sel)
                else:
                    os.remove(sel)
                self._fc_refresh()
            except Exception as exc:
                self.info('Delete failed', str(exc))
        self.confirm('Delete', 'Delete %s permanently?' % os.path.basename(sel), go)

    # ---- search in project
    def _search_view(self, parent):
        box = BoxLayout(orientation='vertical', spacing=dp(4))
        q = TextInput(hint_text='Search in files', multiline=False, size_hint_y=None, height=dp(44),
                      background_color=rgba(EDIT_LINE), foreground_color=rgba(WHITE), cursor_color=rgba(CURSOR))
        status = Label(text='', color=rgba(WHITE), size_hint_y=None, height=dp(24), font_size=sp(12))
        sv = ScrollView()
        results = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
        results.bind(minimum_height=results.setter('height'))
        sv.add_widget(results)
        box.add_widget(q)
        box.add_widget(status)
        box.add_widget(sv)
        parent.add_widget(box)

        def run(*_):
            needle = q.text.strip().lower()
            results.clear_widgets()
            if not needle:
                return
            root = os.path.dirname(self.tabs[self.cur].path) if 0 <= self.cur < len(self.tabs) and self.tabs[self.cur].path else start_dir()
            hits = 0
            files_seen = 0
            for dp_, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if not d.startswith('.')][:50]
                for fn in fns:
                    if not fn.lower().endswith(tuple(e.strip('*') for e in TEXT_EXTS)):
                        continue
                    files_seen += 1
                    if files_seen > 300:
                        break
                    path = os.path.join(dp_, fn)
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            for ln, line in enumerate(f, 1):
                                if needle in line.lower():
                                    hits += 1
                                    if hits > 150:
                                        break
                                    b = Btn(text='%s:%d  %s' % (fn, ln, line.strip()[:60]), height=dp(40),
                                            background_color=rgba('#2F343E'), font_size=sp(11), halign='left')
                                    b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(8), s[1])))
                                    b.bind(on_release=lambda _b, p=path, l=ln: self._open_at_line(p, l))
                                    results.add_widget(b)
                    except Exception:
                        pass
            status.text = '%d results in %d files' % (hits, min(files_seen, 300))
        q.bind(on_text_validate=run)

    def _open_at_line(self, path, line):
        self.open_path(path)
        Clock.schedule_once(lambda d: self._goto_line_num(line), 0.2)

    def _goto_line_num(self, n):
        lines = self.editor.text.split('\n')
        n = min(max(1, n), len(lines))
        self._set_cursor(sum(len(l) + 1 for l in lines[:n - 1]))

    # ================= run / preview / terminal =================
    def run_python(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        self._stash()
        t = self.tabs[self.cur]
        self.show_console()
        self.console_write('--- run %s ---' % t.name, 'system')
        out = io.StringIO()
        g = {'__name__': '__main__', '__file__': t.path or t.name}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                exec(compile(t.text, t.name, 'exec'), g)
        except BaseException:
            out.write(traceback.format_exc())
        for line in out.getvalue().splitlines() or ['(no output)']:
            self.console_write(line)
        self.console_write('--- done ---', 'system')

    def preview_html(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        t = self.tabs[self.cur]
        if not t.path:
            self.info('Preview', 'Save the file first (Save as).')
            return
        self.save_tab(self.cur)
        folder = os.path.dirname(t.path)
        name = os.path.basename(t.path)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        self.stop_server()
        try:
            handler = functools.partial(Quiet, directory=folder)
            self.server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), handler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            url = 'http://127.0.0.1:%d/%s' % (PORT, urllib.parse.quote(name))
            self.console_write('Preview: %s' % url, 'system')
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass
        except Exception as exc:
            self.console_write('Preview failed: %s' % exc, 'stderr')

    def stop_server(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
            self.console_write('Preview server stopped.', 'warning')

    def terminal_popup(self):
        def go(cmd):
            self.show_console()
            self.console_write('$ ' + cmd, 'system')

            def worker():
                try:
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                    lines = (res.stdout + res.stderr).splitlines() or ['(exit %s)' % res.returncode]
                except Exception as exc:
                    lines = ['Error: %s' % exc]
                Clock.schedule_once(lambda d: [self.console_write(l) for l in lines], 0)
            threading.Thread(target=worker, daemon=True).start()
        self.ask_text('Terminal', 'Command (e.g. ls, pwd, python3 --version):', go)

    def show_processes(self):
        self.info('Running processes', 'Preview server: %s\nLast run: see Console.' % ('running' if self.server else 'stopped'))

    # ================= console =================
    def show_console(self):
        if self.console_pop is None:
            box = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(6))
            bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            clear_b = Btn(text='Clear', font_size=sp(12))
            copy_b = Btn(text='Copy', font_size=sp(12))
            stop_b = Btn(text='Stop preview', font_size=sp(12))
            bar.add_widget(clear_b)
            bar.add_widget(copy_b)
            bar.add_widget(stop_b)
            box.add_widget(bar)
            box.add_widget(self.console_out)
            p = Popup(title='Console', content=box, size_hint=(0.98, 0.6), title_color=rgba(WHITE),
                      separator_color=rgba(TOP), background_color=rgba(EDITOR))
            clear_b.bind(on_release=lambda *_: setattr(self.console_out, 'text', ''))
            copy_b.bind(on_release=lambda *_: self._copy(self.console_out.text))
            stop_b.bind(on_release=lambda *_: self.stop_server())
            self.console_pop = p
        if self.console_pop not in self.modals:
            self.open_modal(self.console_pop)
        else:
            self.console_pop.open()

    def console_write(self, text, tag='stdout'):
        prefix = {'stderr': '[ERR] ', 'warning': '[WARN] ', 'system': '[SYS] '}.get(tag, '')
        self.console_out.text += '[%s] %s%s\n' % (dt_now(), prefix, str(text))
        if self.console_out.text.count('\n') > 3000:
            self.console_out.text = self.console_out.text.split('\n', 1000)[-1]

    # ================= settings / help / exit =================
    def show_settings(self):
        box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))
        size_lbl = Label(text='Font size: %s' % self.settings['font_size'], color=rgba(WHITE),
                         size_hint_y=None, height=dp(30))
        box.add_widget(size_lbl)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        minus, plus = Btn(text='Smaller'), FlatBtn(text='Bigger')
        row.add_widget(minus)
        row.add_widget(plus)
        box.add_widget(row)

        def change(delta):
            self.settings['font_size'] = max(9, min(30, int(self.settings['font_size']) + delta))
            size_lbl.text = 'Font size: %s' % self.settings['font_size']
            self.editor.font_size = sp(self.settings['font_size'])
            self.color_label.font_size = sp(self.settings['font_size'])
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
        box.add_widget(toggle('wrap', 'Word wrap'))
        box.add_widget(toggle('auto_indent', 'Auto indent'))

        tw = Btn(text='Tab width: %s (tap to change)' % self.settings['tab_width'])

        def tw_change(*_):
            self.settings['tab_width'] = 2 if int(self.settings.get('tab_width', 4)) == 4 else 4
            tw.text = 'Tab width: %s (tap to change)' % self.settings['tab_width']
            self.save_settings()
        tw.bind(on_release=tw_change)
        box.add_widget(tw)

        close = FlatBtn(text='Close')
        box.add_widget(close)
        p = Popup(title='Settings', content=box, size_hint=(0.92, None), height=dp(420),
                  title_color=rgba(WHITE), separator_color=rgba(TOP), background_color=rgba(EDITOR))
        close.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def show_help(self):
        self.info('Help', (
            'tataloo Code\n\n'
            '≡  Files, search in project, alerts.\n'
            '✎  File properties (rename, read only, format).\n'
            '⋮  Main menu (save, find, console, run, settings).\n'
            'Tab bar: tap to switch, x to close, ⋯ for tab options.\n'
            'Color is always on in the editor view when not editing.\n'
            'Keys bar above the status line inserts symbols.\n\n'
            'Not in this version: plugin store, notifications, favorites, emmet.'))

    def exit_app(self):
        unsaved = [t for t in self.tabs if t.modified]
        if not unsaved:
            self.stop()
            return
        self.confirm('Exit', 'You have %d unsaved tab(s). Exit anyway?' % len(unsaved),
                     lambda yes: self._exit_now(yes))

    def _exit_now(self, yes):
        if yes:
            self.save_session()
            self.stop()

    def _on_key(self, window, key, *args):
        if key != 27:
            return False
        if self.modals:
            self.modals[-1].dismiss()
            return True
        self.exit_app()
        return True

    # ================= status =================
    def update_status(self):
        try:
            if not (0 <= self.cur < len(self.tabs)):
                return
            t = self.tabs[self.cur]
            text = self.editor.text
            idx = self.editor.cursor_index()
            line = text.count('\n', 0, idx) + 1
            col = idx - (text.rfind('\n', 0, idx) + 1) + 1
            self.status.text = '%s    Ln %d, Col %d    %s' % (
                t.path or 'unsaved', line, col, 'EDIT' if self.edit_mode else 'COLOR')
            self.subtitle.text = ('Modified' if t.modified else 'Saved') + ('' if self.edit_mode else '  Read only')
        except Exception:
            pass


def dt_now():
    import datetime
    return datetime.datetime.now().strftime('%H:%M:%S')


if __name__ == '__main__':
    try:
        TataloCodeApp().run()
    except Exception:
        save_crash(traceback.format_exc())
        raise
