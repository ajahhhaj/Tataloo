#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tataloo Code - full Android editor (Kivy). Pure Python, no extra libraries."""
import contextlib
import functools
import http.server
import io
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
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup, platform

APP_NAME = 'tataloo Code'
PORT = 8765
TEXT_EXTS = ('*.py', '*.html', '*.htm', '*.css', '*.js', '*.json', '*.xml', '*.txt', '*.md', '*.sql', '*.sh', '*.csv')
MAX_HILITE = 120000

BG = '#0A0A0A'
PANEL = '#121212'
PANEL2 = '#080808'
ACCENT = '#00FF41'
FG = '#E5E5E5'
MUTED = '#777777'
EDITOR_BG = '#050505'
LINE = '#174D2B'

C_KW = 'FF4FD8'
C_BUILTIN = '00E5FF'
C_STR = 'FFD166'
C_COMMENT = '5FAF7A'
C_NUM = 'FF9F43'
C_FUNC = '7CFF6B'
C_DEC = 'C084FC'
C_CLASS = 'FFB86C'

PY_KW = set('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'.split())
PY_BUILTIN = set('print len range str int float list dict set tuple bool open input type isinstance super self cls enumerate zip map filter sorted sum min max abs round exec eval'.split())
HTML_KW = set('html head body div span p a img ul ol li table tr td th script style link meta title h1 h2 h3 h4 h5 h6 input button form'.split())
JS_KW = set('var let const function return if else for while do switch case break continue new this class extends import export async await try catch throw null undefined true false'.split())

TOKEN_RE = re.compile(
    r'(#[^\n]*|//[^\n]*)'
    r'|("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`[^`]*`)'
    r'|(@[A-Za-z_][\w.]*)'
    r'|(\b\d+(?:\.\d+)?\b)'
    r'|(\b[A-Za-z_][\w]*\b)'
)


def rgba(value, alpha=1.0):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (alpha,)


def hilite(text, ext):
    """Return Kivy markup with syntax colours. Works for py, js, html, css, json."""
    if len(text) > MAX_HILITE:
        return escape_markup(text)
    if ext in ('.html', '.htm'):
        kw = HTML_KW
    elif ext in ('.js',):
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
            out.append('[color=%s]%s[/color]' % (C_COMMENT, esc))
        elif m.group(2):
            out.append('[color=%s]%s[/color]' % (C_STR, esc))
        elif m.group(3):
            out.append('[color=%s]%s[/color]' % (C_DEC, esc))
        elif m.group(4):
            out.append('[color=%s]%s[/color]' % (C_NUM, esc))
        else:
            word = tok
            after = text[m.end():m.end() + 1]
            if word in kw:
                out.append('[color=%s][b]%s[/b][/color]' % (C_KW, esc))
            elif word in PY_BUILTIN:
                out.append('[color=%s]%s[/color]' % (C_BUILTIN, esc))
            elif word[:1].isupper() and ext == '.py':
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


class Btn(Button):
    def __init__(self, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', rgba('#141414'))
        kw.setdefault('color', rgba(ACCENT))
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(44))
        kw.setdefault('font_size', sp(13))
        super().__init__(**kw)


class SmallBtn(Btn):
    def __init__(self, **kw):
        kw.setdefault('size_hint_x', None)
        kw.setdefault('width', dp(70))
        kw.setdefault('height', dp(40))
        super().__init__(**kw)


class Lbl(Label):
    def __init__(self, **kw):
        kw.setdefault('color', rgba(FG))
        kw.setdefault('font_size', sp(12))
        super().__init__(**kw)
        self.bind(size=lambda w, s: setattr(w, 'text_size', (s[0], s[1])))


class CodeEditor(TextInput):
    """TextInput with auto-indent on Enter."""

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

    @property
    def name(self):
        return Path(self.path).name if self.path else 'untitled'


class TataloCodeApp(App):
    title = APP_NAME

    # ---------------- lifecycle ----------------
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
        Window.clearcolor = rgba(BG)
        Window.softinput_mode = 'below_target'
        self.home = Path(self.user_data_dir)
        self.home.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.home / 'settings.json'
        self.session_path = self.home / 'session.json'
        self.settings = {'font_size': 14, 'wrap': False, 'auto_indent': True, 'tab_width': 4,
                         'console_visible': True, 'recent': []}
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                self.settings.update(data)
        except Exception:
            pass
        self.tabs = []
        self.cur = -1
        self.loading = False
        self.color_mode = False
        self.modals = []
        self.explorer_fc = None
        self.explorer_pop = None
        self.server = None
        self.process_text = 'Ready'

        root = BoxLayout(orientation='vertical', padding=dp(4), spacing=dp(3))

        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        top.add_widget(SmallBtn(text='Menu', width=dp(78), on_release=lambda *_: self.show_menu()))
        self.title_label = Lbl(text=APP_NAME, color=rgba(ACCENT), bold=True, font_size=sp(15))
        top.add_widget(self.title_label)
        top.add_widget(SmallBtn(text='Save', width=dp(70), on_release=lambda *_: self.save()))
        top.add_widget(SmallBtn(text='Run', width=dp(64), on_release=lambda *_: self.run_python()))
        root.add_widget(top)

        tool_sv = ScrollView(size_hint_y=None, height=dp(44), do_scroll_y=False, bar_width=0)
        tool = BoxLayout(size_hint_x=None, spacing=dp(4))
        tool.bind(minimum_width=tool.setter('width'))
        for text, fn in (('Files', self.show_explorer), ('New', self.new_untitled), ('Open', self.open_file),
                         ('Find', self.find_popup), ('Replace', self.replace_popup), ('Goto', self.goto_popup),
                         ('Undo', self.undo), ('Redo', self.redo), ('Color', self.toggle_color),
                         ('Format', self.format_doc), ('Preview', self.preview_html), ('Console', self.toggle_console),
                         ('Settings', self.show_settings), ('Help', self.show_help)):
            tool.add_widget(SmallBtn(text=text, width=dp(84), on_release=lambda _b, f=fn: f()))
        tool_sv.add_widget(tool)
        root.add_widget(tool_sv)

        tabs_sv = ScrollView(size_hint_y=None, height=dp(42), do_scroll_y=False, bar_width=0)
        self.tab_row = BoxLayout(size_hint_x=None, spacing=dp(3))
        self.tab_row.bind(minimum_width=self.tab_row.setter('width'))
        tabs_sv.add_widget(self.tab_row)
        root.add_widget(tabs_sv)

        self.editor_host = BoxLayout()
        root.add_widget(self.editor_host)

        self.editor = CodeEditor(multiline=True, write_tab=False, font_size=sp(self.settings['font_size']),
                                 font_name='Roboto', background_color=rgba(EDITOR_BG),
                                 foreground_color=rgba(FG), cursor_color=rgba(ACCENT),
                                 selection_color=rgba(LINE, 0.8), padding=[dp(8), dp(6)])
        self.editor.app_ref = self
        self.editor.bind(text=self._on_text, cursor=self._on_cursor)
        if hasattr(self.editor, 'do_wrap'):
            self.editor.do_wrap = bool(self.settings.get('wrap'))

        self.color_label = Label(text='', markup=True, color=rgba(FG), font_size=sp(self.settings['font_size']),
                                 font_name='Roboto', size_hint_y=None, halign='left', valign='top')
        self.color_label.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        self.color_label.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(20)))
        self.color_sv = ScrollView(bar_width=dp(4))
        self.color_wrap = BoxLayout(size_hint_y=None, padding=[dp(8), dp(6)])
        self.color_wrap.add_widget(self.color_label)
        self.color_sv.add_widget(self.color_wrap)
        self.color_label.bind(height=lambda w, v: setattr(self.color_wrap, 'height', v + dp(12)))
        self.color_wrap.height = dp(40)

        sym_sv = ScrollView(size_hint_y=None, height=dp(40), do_scroll_y=False, bar_width=0)
        sym = BoxLayout(size_hint_x=None, spacing=dp(3))
        sym.bind(minimum_width=sym.setter('width'))
        for s in ['Tab', '<Tab', '(', ')', '[', ']', '{', '}', '"', "'", ':', '=', '.', ',', '_', '-', '+', '*', '/', '\\', '#', '<', '>', '&', '|', '!', '?', '@', '$', '%', ';']:
            act = s
            sym.add_widget(SmallBtn(text=s, width=dp(44), height=dp(36), font_size=sp(14),
                                    on_release=lambda _b, a=act: self.sym_key(a)))
        sym_sv.add_widget(sym)
        root.add_widget(sym_sv)

        self.console_box = BoxLayout(orientation='vertical', size_hint_y=0.32, spacing=dp(2))
        head = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(3))
        head.add_widget(Lbl(text='CONSOLE', color=rgba(ACCENT), bold=True, size_hint_x=0.4))
        head.add_widget(SmallBtn(text='Clear', width=dp(64), on_release=lambda *_: self.console_clear()))
        head.add_widget(SmallBtn(text='Copy', width=dp(64), on_release=lambda *_: self.console_copy()))
        head.add_widget(SmallBtn(text='Terminal', width=dp(90), on_release=lambda *_: self.terminal_popup()))
        head.add_widget(SmallBtn(text='Stop', width=dp(60), on_release=lambda *_: self.stop_server()))
        self.console_box.add_widget(head)
        self.console_out = TextInput(readonly=True, multiline=True, font_size=sp(11), font_name='Roboto',
                                     background_color=rgba('#050505'), foreground_color=rgba('B9FFC8'),
                                     padding=[dp(6), dp(4)])
        self.console_box.add_widget(self.console_out)
        root.add_widget(self.console_box)

        self.status = Lbl(text='Ready', size_hint_y=None, height=dp(22), color=rgba(ACCENT), font_size=sp(11))
        root.add_widget(self.status)

        self.root_widget = root
        self._rebuild_editor_view()
        self.console_write('tataloo Code ready.')
        self.refresh_tabs()
        if not self.settings.get('console_visible', True):
            self.console_box.parent and root.remove_widget(self.console_box)

        self.new_untitled()
        Clock.schedule_once(self._restore_session, 0.2)
        Clock.schedule_once(self._ask_permissions, 1.0)
        Clock.schedule_interval(self._tick, 1.0)
        Window.bind(on_keyboard=self._on_key)
        return root

    def on_pause(self):
        self.save_session()
        return True

    def on_stop(self):
        self.save_session()
        self.save_settings()

    def _tick(self, dt_):
        self.update_status()

    # ---------------- settings / session ----------------
    def save_settings(self):
        try:
            self.settings_path.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            self.console_write('Settings save error: %s' % exc, 'stderr')

    def save_session(self):
        try:
            if self.cur >= 0:
                self._stash()
            data = {'paths': [t.path for t in self.tabs if t.path], 'active': self.tabs[self.cur].path if 0 <= self.cur < len(self.tabs) and self.tabs[self.cur].path else None}
            self.session_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            self.save_settings()
        except Exception:
            pass

    def _restore_session(self, *_):
        try:
            data = json.loads(self.session_path.read_text(encoding='utf-8'))
        except Exception:
            return
        active = data.get('active') if isinstance(data, dict) else None
        paths = data.get('paths', []) if isinstance(data, dict) else []
        for p in paths:
            if p and os.path.isfile(p):
                self.open_path(p, quiet=True)
        if active:
            for i, t in enumerate(self.tabs):
                if t.path == active:
                    self.switch(i)
        if self.tabs and self.cur < 0:
            self.switch(0)

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

    # ---------------- popups helpers ----------------
    def open_modal(self, widget):
        self.modals.append(widget)
        widget.bind(on_dismiss=lambda *_: self.modals.remove(widget) if widget in self.modals else None)
        widget.open()
        return widget

    def info(self, title, text):
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        sv = ScrollView()
        lab = Label(text=text, color=rgba(FG), font_size=sp(13), size_hint_y=None, halign='left', valign='top')
        lab.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        lab.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(10)))
        sv.add_widget(lab)
        box.add_widget(sv)
        ok = Btn(text='OK')
        box.add_widget(ok)
        p = Popup(title=title, content=box, size_hint=(0.92, 0.7), title_color=rgba(ACCENT),
                  separator_color=rgba(ACCENT), background_color=rgba(PANEL))
        ok.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def ask_text(self, title, prompt, callback, initial=''):
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        box.add_widget(Lbl(text=prompt, size_hint_y=None, height=dp(24)))
        ti = TextInput(text=initial, multiline=False, size_hint_y=None, height=dp(44),
                       background_color=rgba(PANEL2), foreground_color=rgba(FG), cursor_color=rgba(ACCENT))
        box.add_widget(ti)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        ok, cancel = Btn(text='OK'), Btn(text='Cancel')
        row.add_widget(ok)
        row.add_widget(cancel)
        box.add_widget(row)
        p = Popup(title=title, content=box, size_hint=(0.92, None), height=dp(230),
                  title_color=rgba(ACCENT), separator_color=rgba(ACCENT), background_color=rgba(PANEL))

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
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        box.add_widget(Lbl(text=text, size_hint_y=1))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        yes, no = Btn(text='Yes'), Btn(text='No')
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        p = Popup(title=title, content=box, size_hint=(0.9, None), height=dp(210),
                  title_color=rgba(ACCENT), separator_color=rgba(ACCENT), background_color=rgba(PANEL))
        yes.bind(on_release=lambda *_: (p.dismiss(), callback(True)))
        no.bind(on_release=lambda *_: (p.dismiss(), callback(False)))
        self.open_modal(p)

    def choose(self, title, options):
        """options: list of (label, callback)"""
        mv = ModalView(size_hint=(0.86, None), height=dp(60 + 50 * len(options)), background='', background_color=rgba(PANEL))
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        box.add_widget(Lbl(text=title, color=rgba(ACCENT), bold=True, size_hint_y=None, height=dp(30)))
        for label, fn in options:
            b = Btn(text=label)
            b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), Clock.schedule_once(lambda d: f(), 0.05)))
            box.add_widget(b)
        mv.add_widget(box)
        self.open_modal(mv)

    # ---------------- main menu ----------------
    def show_menu(self):
        groups = [
            ('FILE', [('New file', self.new_untitled), ('Open file', self.open_file), ('Save', self.save),
                      ('Save as', self.save_as), ('Close file', self.close_current), ('Close all tabs', self.close_all),
                      ('Open recent', self.open_recent), ('Files (explorer)', self.show_explorer)]),
            ('EDIT', [('Find', self.find_popup), ('Replace', self.replace_popup), ('Go to line', self.goto_popup),
                      ('Select all', self.select_all), ('Undo', self.undo), ('Redo', self.redo),
                      ('Format document', self.format_doc)]),
            ('VIEW', [('Color view on/off', self.toggle_color), ('Console on/off', self.toggle_console),
                      ('Word wrap on/off', self.toggle_wrap)]),
            ('RUN', [('Run Python', self.run_python), ('Preview HTML', self.preview_html),
                     ('Stop server', self.stop_server), ('Terminal command', self.terminal_popup)]),
            ('TOOLS', [('Settings', self.show_settings), ('Help', self.show_help),
                       ('Plugins', lambda: self.info('Plugins', 'Plugin store is not in this version.')),
                       ('Notifications', lambda: self.info('Notifications', 'No notifications in this version.')),
                       ('Favorites', lambda: self.info('Favorites', 'Favorites are not in this version.')),
                       ('Running processes', self.show_processes), ('Exit', self.exit_app)]),
        ]
        mv = ModalView(size_hint=(0.96, 0.94), background='', background_color=rgba(PANEL))
        sv = ScrollView()
        box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(3), padding=dp(8))
        box.bind(minimum_height=box.setter('height'))
        for title, items in groups:
            box.add_widget(Lbl(text=title, color=rgba(ACCENT), bold=True, size_hint_y=None, height=dp(32)))
            for label, fn in items:
                b = Btn(text=label, halign='left', height=dp(44))
                b.bind(size=lambda inst, s: setattr(inst, 'text_size', (s[0] - dp(12), s[1])))
                b.bind(on_release=lambda _b, f=fn: (mv.dismiss(), Clock.schedule_once(lambda d: f(), 0.05)))
                box.add_widget(b)
        sv.add_widget(box)
        mv.add_widget(sv)
        self.open_modal(mv)

    # ---------------- tabs ----------------
    def refresh_tabs(self):
        self.tab_row.clear_widgets()
        for i, t in enumerate(self.tabs):
            active = i == self.cur
            bg = rgba('#18251b') if active else rgba('#0B0B0B')
            name = ('* ' if t.modified else '') + ('[P] ' if t.pinned else '') + t.name
            b = Btn(text=name, size_hint_x=None, width=dp(150), height=dp(38), background_color=bg,
                    color=rgba(ACCENT) if active else rgba(FG), font_size=sp(12))
            b.bind(on_release=lambda _b, idx=i: self.switch(idx))
            m = SmallBtn(text='...', width=dp(40), height=dp(38), on_release=lambda _b, idx=i: self.tab_menu(idx))
            self.tab_row.add_widget(b)
            self.tab_row.add_widget(m)
        self.title_label.text = (self.tabs[self.cur].name if 0 <= self.cur < len(self.tabs) else APP_NAME)

    def tab_menu(self, idx):
        t = self.tabs[idx]
        self.choose(t.name, [
            ('Pin / unpin', lambda: self._toggle_pin(idx)),
            ('Close', lambda: self.close_index(idx)),
            ('Close others', lambda: self.close_others(idx)),
            ('Close tabs to the left', lambda: self.close_side(idx, 'left')),
            ('Close tabs to the right', lambda: self.close_side(idx, 'right')),
            ('Copy path', lambda: self._copy(t.path or t.name)),
        ])

    def _toggle_pin(self, idx):
        self.tabs[idx].pinned = not self.tabs[idx].pinned
        self.refresh_tabs()

    def _copy(self, text):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            self.console_write('Copied: %s' % text)
        except Exception as exc:
            self.console_write('Copy failed: %s' % exc, 'stderr')

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
        self.update_status()
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
        if self.color_mode:
            self._refresh_color()

    def _on_cursor(self, *_):
        self.update_status()

    def new_untitled(self):
        self._stash()
        n = sum(1 for t in self.tabs if not t.path) + 1
        t = Tab(None, '')
        t.name_hint = 'untitled-%d' % n
        self.tabs.append(t)
        self.switch(len(self.tabs) - 1)

    def close_index(self, idx):
        if not (0 <= idx < len(self.tabs)):
            return
        t = self.tabs[idx]
        def do_close(save=False):
            if save:
                if self.cur == idx:
                    self._stash()
                if not self.save_tab(idx):
                    return
            if self.tabs:
                self.tabs.pop(idx)
            if not self.tabs:
                self.cur = -1
                self.new_untitled()
                return
            if self.cur == idx:
                self.cur = -1
                self.switch(min(idx, len(self.tabs) - 1))
            elif self.cur > idx:
                self.cur -= 1
                self.refresh_tabs()
            else:
                self.refresh_tabs()
        if t.modified:
            self.confirm('Unsaved changes', 'Save changes to %s before closing?' % t.name, do_close)
        else:
            do_close(False)

    def close_current(self):
        self.close_index(self.cur)

    def close_all(self):
        def step(*_):
            if self.tabs:
                self.close_index(0)
                Clock.schedule_once(step, 0.3)
        step()

    def close_others(self, keep):
        keep_tab = self.tabs[keep]
        for t in list(self.tabs):
            if t is not keep_tab and not t.pinned:
                self.tabs.remove(t)
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

    # ---------------- editor view ----------------
    def _rebuild_editor_view(self):
        self.editor_host.clear_widgets()
        if self.color_mode:
            self._refresh_color()
            self.editor_host.add_widget(self.color_sv)
        else:
            self.editor_host.add_widget(self.editor)

    def _refresh_color(self):
        if not (0 <= self.cur < len(self.tabs)):
            self.color_label.text = ''
            return
        t = self.tabs[self.cur]
        ext = Path(t.path).suffix.lower() if t.path else '.py'
        text = self.editor.text if self.cur >= 0 else t.text
        self.color_label.text = hilite(text, ext)

    def toggle_color(self):
        self._stash()
        self.color_mode = not self.color_mode
        self._rebuild_editor_view()
        self.update_status()

    def toggle_console(self):
        if self.console_box.parent is not None:
            self.root_widget.remove_widget(self.console_box)
            self.settings['console_visible'] = False
        else:
            self.root_widget.add_widget(self.console_box, index=1)
            self.settings['console_visible'] = True

    def toggle_wrap(self):
        self.settings['wrap'] = not self.settings.get('wrap')
        if hasattr(self.editor, 'do_wrap'):
            self.editor.do_wrap = bool(self.settings['wrap'])
        self.save_settings()

    def sym_key(self, s):
        if self.color_mode:
            self.toggle_color()
        if s == 'Tab':
            self.editor.insert_text(' ' * int(self.settings.get('tab_width', 4)))
        elif s == '<Tab':
            cur_line = self._current_line_start()
            text = self.editor.text
            if text[cur_line:cur_line + 1] == ' ':
                for _ in range(int(self.settings.get('tab_width', 4))):
                    if self.editor.text[cur_line:cur_line + 1] == ' ':
                        self.editor.text = self.editor.text[:cur_line] + self.editor.text[cur_line + 1:]
        else:
            self.editor.insert_text(s)
        self.editor.focus = True

    def _current_line_start(self):
        idx = self.editor.cursor_index()
        return self.editor.text.rfind('\n', 0, idx) + 1

    def select_all(self):
        if self.color_mode:
            self.toggle_color()
        self.editor.select_all()

    def undo(self):
        if self.color_mode:
            self.toggle_color()
        try:
            self.editor.do_undo()
        except Exception as exc:
            self.console_write('Undo: %s' % exc, 'warning')

    def redo(self):
        if self.color_mode:
            self.toggle_color()
        try:
            self.editor.do_redo()
        except Exception as exc:
            self.console_write('Redo: %s' % exc, 'warning')

    def format_doc(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        if self.color_mode:
            self.toggle_color()
        text = self.editor.text
        if self.tabs[self.cur].path and self.tabs[self.cur].path.endswith('.json'):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except Exception as exc:
                self.console_write('Format JSON failed: %s' % exc, 'stderr')
                return
        else:
            text = '\n'.join(line.rstrip() for line in text.split('\n'))
        self.editor.text = text
        self.console_write('Formatted.')

    # ---------------- find / replace / goto ----------------
    def find_popup(self):
        self._find_dialog(False)

    def replace_popup(self):
        self._find_dialog(True)

    def _find_dialog(self, with_replace):
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        find_in = TextInput(hint_text='Find', multiline=False, size_hint_y=None, height=dp(44),
                            background_color=rgba(PANEL2), foreground_color=rgba(FG), cursor_color=rgba(ACCENT))
        box.add_widget(find_in)
        rep_in = TextInput(hint_text='Replace with', multiline=False, size_hint_y=None, height=dp(44),
                           background_color=rgba(PANEL2), foreground_color=rgba(FG), cursor_color=rgba(ACCENT))
        if with_replace:
            box.add_widget(rep_in)
        info = Lbl(text='', size_hint_y=None, height=dp(22))
        box.add_widget(info)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        nxt, prv = Btn(text='Next'), Btn(text='Prev')
        row.add_widget(prv)
        row.add_widget(nxt)
        box.add_widget(row)
        if with_replace:
            row2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            rep, rep_all = Btn(text='Replace'), Btn(text='Replace all')
            row2.add_widget(rep)
            row2.add_widget(rep_all)
            box.add_widget(row2)
        close = Btn(text='Close')
        box.add_widget(close)
        p = Popup(title='Find & Replace' if with_replace else 'Find', content=box, size_hint=(0.95, None),
                  height=dp(360) if with_replace else dp(280), title_color=rgba(ACCENT),
                  separator_color=rgba(ACCENT), background_color=rgba(PANEL))

        def go(forward):
            needle = find_in.text
            if not needle:
                return
            if self.color_mode:
                self.toggle_color()
            ok = self.find_in_editor(needle, forward)
            info.text = 'found' if ok else 'not found'

        def replace_one(*_):
            needle, rep_text = find_in.text, rep_in.text
            if not needle:
                return
            if self.color_mode:
                self.toggle_color()
            text = self.editor.text
            start = self.editor.cursor_index()
            i = text.find(needle, start)
            if i < 0:
                i = text.find(needle)
            if i < 0:
                info.text = 'not found'
                return
            self.editor.text = text[:i] + rep_text + text[i + len(needle):]
            self.editor.cursor = self.editor.get_cursor_from_index(i + len(rep_text))
            info.text = 'replaced'

        def replace_all(*_):
            needle, rep_text = find_in.text, rep_in.text
            if not needle:
                return
            if self.color_mode:
                self.toggle_color()
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
        self.editor.cursor = self.editor.get_cursor_from_index(i + len(needle) if forward else i)
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
            if self.color_mode:
                self.toggle_color()
            lines = self.editor.text.split('\n')
            n = min(n, len(lines))
            idx = sum(len(l) + 1 for l in lines[:n - 1])
            self._set_cursor(idx)
        self.ask_text('Go to line', 'Line number:', go)

    # ---------------- files ----------------
    def open_file(self):
        self.show_explorer()

    def open_path(self, path, quiet=False):
        path = os.path.abspath(path)
        for i, t in enumerate(self.tabs):
            if t.path == path:
                self.switch(i)
                return
        try:
            raw = Path(path).read_bytes()
            text = raw.decode('utf-8', errors='replace')
        except Exception as exc:
            if not quiet:
                self.info('Open failed', str(exc))
            self.console_write('Open failed: %s' % exc, 'stderr')
            return
        self._stash()
        t = Tab(path, text)
        self.tabs.append(t)
        self._add_recent(path)
        self.switch(len(self.tabs) - 1)
        self.console_write('Opened %s' % path, 'system')

    def _add_recent(self, path):
        rec = [path] + [p for p in self.settings.get('recent', []) if p != path]
        self.settings['recent'] = rec[:15]
        self.save_settings()

    def open_recent(self):
        items = [(os.path.basename(p) + '  -  ' + p, (lambda pp=p: self.open_path(pp)))
                 for p in self.settings.get('recent', []) if os.path.isfile(p)]
        if not items:
            self.info('Open recent', 'No recent files yet.')
            return
        self.choose('Open recent', items[:12])

    def save(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        if self.tabs[self.cur].path is None:
            return self.save_as()
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
        default = t.path or os.path.join(start_dir(), getattr(t, 'name_hint', 'untitled') + '.py')

        def got(path):
            if idx == self.cur:
                self._stash()
            t.path = os.path.abspath(path)
            if self.save_tab(idx):
                self.refresh_tabs()
                self.update_status()
        self.ask_text('Save as', 'Full file path (e.g. /sdcard/Download/app.py):', got, initial=default)

    # ---------------- explorer ----------------
    def show_explorer(self):
        start = self.tabs[self.cur].path if 0 <= self.cur < len(self.tabs) and self.tabs[self.cur].path else start_dir()
        if os.path.isfile(start):
            start = os.path.dirname(start)
        box = BoxLayout(orientation='vertical', padding=dp(4), spacing=dp(4))
        quick = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        fc = FileChooserListView(path=start, filters=list(TEXT_EXTS), show_hidden=False)
        self.explorer_fc = fc
        for text, target in (('Up', None), ('Storage', start_dir()), ('App', self.user_data_dir), ('Home', os.path.expanduser('~'))):
            quick.add_widget(SmallBtn(text=text, width=dp(80), height=dp(38), on_release=lambda _b, tg=target: self._fc_go(tg)))
        box.add_widget(quick)
        box.add_widget(fc)
        acts = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for text, fn in (('Open', self._fc_open), ('New file', self._fc_new_file), ('New folder', self._fc_new_folder),
                         ('Rename', self._fc_rename), ('Delete', self._fc_delete), ('Close', None)):
            if fn is None:
                acts.add_widget(Btn(text=text, on_release=lambda *_: self.explorer_pop.dismiss()))
            else:
                acts.add_widget(Btn(text=text, on_release=lambda _b, f=fn: f()))
        box.add_widget(acts)
        p = Popup(title='Files', content=box, size_hint=(0.97, 0.94), title_color=rgba(ACCENT),
                  separator_color=rgba(ACCENT), background_color=rgba(PANEL))
        self.explorer_pop = p
        self.open_modal(p)

    def _fc_go(self, target):
        if self.explorer_fc is None:
            return
        if target is None:
            target = os.path.dirname(self.explorer_fc.path.rstrip('/')) or '/'
        if os.path.isdir(target):
            self.explorer_fc.path = target

    def _fc_current_dir(self):
        return self.explorer_fc.path if self.explorer_fc else start_dir()

    def _fc_selected(self):
        if self.explorer_fc and self.explorer_fc.selection:
            return self.explorer_fc.selection[0]
        return None

    def _fc_open(self):
        sel = self._fc_selected()
        if sel and os.path.isfile(sel):
            if self.explorer_pop:
                self.explorer_pop.dismiss()
            self.open_path(sel)
        elif sel and os.path.isdir(sel):
            self.explorer_fc.path = sel
        else:
            self.info('Open', 'Select a file first.')

    def _fc_new_file(self):
        def got(name):
            path = os.path.join(self._fc_current_dir(), name)
            try:
                if os.path.exists(path):
                    raise FileExistsError('File already exists.')
                Path(path).write_text('', encoding='utf-8')
                self.explorer_fc._update_files()
                self.open_path(path)
            except Exception as exc:
                self.info('New file failed', str(exc))
        self.ask_text('New file', 'File name (e.g. main.py):', got)

    def _fc_new_folder(self):
        def got(name):
            try:
                os.makedirs(os.path.join(self._fc_current_dir(), name), exist_ok=False)
                self.explorer_fc._update_files()
            except Exception as exc:
                self.info('New folder failed', str(exc))
        self.ask_text('New folder', 'Folder name:', got)

    def _fc_rename(self):
        sel = self._fc_selected()
        if not sel:
            self.info('Rename', 'Select a file or folder first.')
            return

        def got(name):
            try:
                os.rename(sel, os.path.join(os.path.dirname(sel), name))
                self.explorer_fc._update_files()
                for t in self.tabs:
                    if t.path == sel:
                        t.path = os.path.join(os.path.dirname(sel), name)
                self.refresh_tabs()
            except Exception as exc:
                self.info('Rename failed', str(exc))
        self.ask_text('Rename', 'New name:', got, initial=os.path.basename(sel))

    def _fc_delete(self):
        sel = self._fc_selected()
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
                self.explorer_fc._update_files()
            except Exception as exc:
                self.info('Delete failed', str(exc))
        self.confirm('Delete', 'Delete %s permanently?' % os.path.basename(sel), go)

    # ---------------- run / preview / terminal ----------------
    def run_python(self):
        if not (0 <= self.cur < len(self.tabs)):
            return
        self._stash()
        t = self.tabs[self.cur]
        name = t.name
        self.console_write('--- run %s ---' % name, 'system')
        out = io.StringIO()
        g = {'__name__': '__main__', '__file__': t.path or name}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                exec(compile(t.text, name, 'exec'), g)
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
        self.info('Running processes', 'Status: %s\nServer: %s' % (self.process_text, 'running' if self.server else 'stopped'))

    # ---------------- settings / help / exit ----------------
    def show_settings(self):
        box = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))
        size_lbl = Lbl(text='Font size: %s' % self.settings['font_size'], size_hint_y=None, height=dp(30))
        box.add_widget(size_lbl)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        minus, plus = Btn(text='-  smaller'), Btn(text='+  bigger')
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

        def toggle_key(key, label_text):
            b = Btn(text='%s: %s' % (label_text, 'on' if self.settings.get(key) else 'off'))
            def flip(*_):
                self.settings[key] = not self.settings.get(key)
                b.text = '%s: %s' % (label_text, 'on' if self.settings.get(key) else 'off')
                if key == 'wrap' and hasattr(self.editor, 'do_wrap'):
                    self.editor.do_wrap = bool(self.settings['wrap'])
                self.save_settings()
            b.bind(on_release=flip)
            return b
        box.add_widget(toggle_key('wrap', 'Word wrap'))
        box.add_widget(toggle_key('auto_indent', 'Auto indent'))

        tw_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        tw_lbl = Lbl(text='Tab width: %s' % self.settings['tab_width'])
        tw_btn = Btn(text='Change tab width')

        def tw_change(*_):
            self.settings['tab_width'] = 2 if int(self.settings.get('tab_width', 4)) == 4 else 4
            tw_lbl.text = 'Tab width: %s' % self.settings['tab_width']
            self.save_settings()
        tw_btn.bind(on_release=tw_change)
        tw_row.add_widget(tw_lbl)
        tw_row.add_widget(tw_btn)
        box.add_widget(tw_row)

        close = Btn(text='Close')
        box.add_widget(close)
        p = Popup(title='Settings', content=box, size_hint=(0.92, None), height=dp(400),
                  title_color=rgba(ACCENT), separator_color=rgba(ACCENT), background_color=rgba(PANEL))
        close.bind(on_release=lambda *_: p.dismiss())
        self.open_modal(p)

    def show_help(self):
        self.info('Help', (
            'tataloo Code\n\n'
            '- Menu: all actions (File, Edit, View, Run, Tools).\n'
            '- Files: browse storage, open, create, rename, delete.\n'
            '- Tabs: tap to switch, ... for pin/close options.\n'
            '- Color: colored syntax view (Color again to edit).\n'
            '- Find / Replace / Go to line in Edit tools.\n'
            '- Run: runs Python in-app, output goes to Console.\n'
            '- Preview: serves the HTML file locally and opens it.\n'
            '- Terminal: runs shell commands (Android shell).\n'
            '- Symbol bar under the editor: quick symbols and Tab.\n\n'
            'Not in this version: plugins store, notifications, favorites, emmet.'))

    def exit_app(self):
        unsaved = [t for t in self.tabs if t.modified]
        if not unsaved:
            self.stop()
            return

        def go(yes):
            if yes is None:
                return
            if yes:
                self.save_session()
                self.stop()
            else:
                self.stop()
        self.confirm('Exit', 'You have %d unsaved tab(s). Exit anyway?' % len(unsaved), go)

    def _on_key(self, window, key, *args):
        if key != 27:
            return False
        if self.modals:
            self.modals[-1].dismiss()
            return True
        self.exit_app()
        return True

    # ---------------- console ----------------
    def console_write(self, text, tag='stdout'):
        prefix = {'stderr': '[ERR] ', 'warning': '[WARN] ', 'system': '[SYS] '}.get(tag, '')
        stamp = dt_now()
        self.console_out.text += '[%s] %s%s\n' % (stamp, prefix, str(text))
        if self.console_out.text.count('\n') > 3000:
            self.console_out.text = self.console_out.text.split('\n', 1000)[-1]

    def console_clear(self):
        self.console_out.text = ''

    def console_copy(self):
        self._copy(self.console_out.text)

    # ---------------- status ----------------
    def update_status(self):
        try:
            if 0 <= self.cur < len(self.tabs):
                t = self.tabs[self.cur]
                idx = self.editor.cursor_index() if not self.color_mode else 0
                text = self.editor.text if not self.color_mode else t.text
                line = text.count('\n', 0, idx) + 1
                col = idx - (text.rfind('\n', 0, idx) + 1) + 1
                where = 'Ln %d, Col %d' % (line, col)
                path = t.path or 'unsaved'
                mode = 'COLOR' if self.color_mode else 'EDIT'
                self.status.text = '%s  |  %s  |  %s  |  %s' % (path, where, mode, 'modified' if t.modified else 'saved')
        except Exception:
            pass


def dt_now():
    import datetime
    return datetime.datetime.now().strftime('%H:%M:%S')


if __name__ == '__main__':
    try:
        TataloCodeApp().run()
    except Exception:
        err = traceback.format_exc()
        save_crash(err)
        raise
