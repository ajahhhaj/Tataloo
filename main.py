#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ACODE GODMODE Android IDE — Kivy edition."""
from __future__ import annotations
import ast, datetime as dt, json, os, re, sys, traceback, webbrowser
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.modalview import ModalView
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Token
    PYGMENTS = True
except Exception:
    PYGMENTS = False

APP_NAME = 'ACODE GODMODE'
BG = '#0A0A0A'; PANEL = '#101010'; PANEL2 = '#080808'
ACCENT = '#00FF41'; FG = '#E5E5E5'; MUTED = '#777777'
RED = '#FF3355'; CYAN = '#00E5FF'; AMBER = '#FFB000'
EXTENSIONS = {'.py':'Python', '.html':'HTML', '.htm':'HTML', '.css':'CSS', '.js':'JavaScript', '.json':'JSON', '.xml':'XML', '.sql':'SQL', '.sh':'Shell', '.md':'Markdown', '.txt':'Text'}


def rgba(value, alpha=1):
    value=value.lstrip('#')
    return tuple(int(value[i:i+2],16)/255 for i in (0,2,4))+(alpha,)

class FlatButton(Button):
    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint_y', None); kwargs.setdefault('height', dp(48))
        kwargs.setdefault('background_normal', ''); kwargs.setdefault('background_down', '')
        kwargs.setdefault('background_color', rgba('#171717'))
        kwargs.setdefault('color', rgba(ACCENT)); kwargs.setdefault('font_size', '14sp')
        super().__init__(**kwargs)

class Console(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None, height=dp(190), spacing=dp(4), padding=dp(6), **kwargs)
        self.output=TextInput(text='', readonly=True, multiline=True, size_hint_y=1,
            background_color=rgba('#050505'), foreground_color=rgba('#B9FFC8'), cursor_color=rgba(ACCENT),
            font_name='data/fonts/RobotoMono-Regular.ttf', font_size='12sp')
        self.add_widget(self.output)
    def write(self, value, tag='stdout'):
        stamp=dt.datetime.now().strftime('%H:%M:%S')
        prefix={'stderr':'[ERROR] ','warning':'[WARN] ','system':'[SYS] '}.get(tag,'')
        self.output.text += f'[{stamp}] {prefix}{str(value)}' + ('' if str(value).endswith('\n') else '\n')
        self.output.cursor=(0,len(self.output.text.splitlines()))
    def clear(self): self.output.text=''

class EditorTab(BoxLayout):
    def __init__(self, app, path=None, text='', **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.app=app; self.path=str(path) if path else None; self.modified=False
        self.encoding='utf-8'; self.title=Path(path).name if path else f'Untitled-{len(app.tabs)+1}'
        self.editor=TextInput(text=text, multiline=True, undo=True, size_hint=(1,1),
            background_color=rgba('#050505'), foreground_color=rgba(FG), cursor_color=rgba(ACCENT),
            selection_color=rgba('#174D2B'), font_size='14sp', padding=[dp(10),dp(10)],
            font_name=app.font_name, write_tab=False)
        self.editor.bind(text=self.on_change)
        self.add_widget(self.editor)
    def on_change(self, *_):
        if not self.app.loading: self.modified=True; self.app.refresh_tab_buttons()
    def get_text(self): return self.editor.text

class AcodeApp(App):
    current_path=StringProperty('No file open')
    status=StringProperty('Ready')
    word_wrap=BooleanProperty(True)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tabs=[]; self.active=None; self.loading=False; self.project=None
        self.settings={}; self.recent=[]; self.font_name='data/fonts/RobotoMono-Regular.ttf'
        self.root_dir=Path('/storage/emulated/0')
        if not self.root_dir.exists(): self.root_dir=Path(self.user_data_dir)
        self.root_dir.mkdir(parents=True,exist_ok=True)
        self.home=Path(self.user_data_dir); self.home.mkdir(parents=True,exist_ok=True)
        self.settings_path=self.home/'settings.json'; self.session_path=self.home/'session.json'
        try:
            data=json.loads(self.settings_path.read_text(encoding='utf-8'))
            if isinstance(data,dict): self.settings=data
        except Exception: self.settings={}
        self.recent=self.settings.get('recent_files',[])
        self.last_run_globals={}
    def build(self):
        self.title=APP_NAME
        Window.softinput_mode='below_target'
        root=BoxLayout(orientation='vertical', spacing=dp(4), padding=dp(5))
        with root.canvas.before:
            Color(*rgba(BG)); self.bg_rect=Rectangle(pos=root.pos,size=root.size)
        root.bind(pos=self._bg_update,size=self._bg_update)
        header=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(5))
        title=Label(text='ACODE GODMODE',color=rgba(ACCENT),bold=True,font_size='16sp',halign='left')
        title.bind(size=lambda w,v:setattr(w,'text_size',v)); header.add_widget(title)
        header.add_widget(FlatButton(text='+',size_hint_x=None,width=dp(48),on_release=lambda *_:self.new_file()))
        header.add_widget(FlatButton(text='RUN',size_hint_x=None,width=dp(78),on_release=lambda *_:self.run_current()))
        root.add_widget(header)
        toolbar=GridLayout(cols=4,size_hint_y=None,height=dp(100),spacing=dp(4))
        actions=[('Open',self.open_file),('Save',self.save),('Save As',self.save_as),('Explorer',self.show_explorer),('Find',self.find),('Replace',self.replace),('Format',self.format_document),('HTML',self.run_html)]
        for name,fn in actions: toolbar.add_widget(FlatButton(text=name,on_release=lambda _,f=fn:f()))
        root.add_widget(toolbar)
        self.tabbar=ScrollView(size_hint_y=None,height=dp(45),do_scroll_x=True,do_scroll_y=False)
        self.tab_buttons=BoxLayout(size_hint_x=None, spacing=dp(4)); self.tab_buttons.bind(minimum_width=self.tab_buttons.setter('width'))
        self.tabbar.add_widget(self.tab_buttons); root.add_widget(self.tabbar)
        self.editor_host=BoxLayout(orientation='vertical'); root.add_widget(self.editor_host)
        self.console=Console(); root.add_widget(self.console)
        bottom=GridLayout(cols=4,size_hint_y=None,height=dp(50),spacing=dp(4))
        for name,fn in [('New',self.new_file),('Files',self.show_explorer),('Console',self.toggle_console),('Settings',self.show_settings)]:
            bottom.add_widget(FlatButton(text=name,on_release=lambda _,f=fn:f()))
        root.add_widget(bottom)
        self.status_label=Label(text='Ready',size_hint_y=None,height=dp(24),color=rgba(ACCENT),font_size='11sp')
        root.add_widget(self.status_label)
        self.new_file(); self.restore_session()
        Clock.schedule_interval(self.update_status,1)
        Clock.schedule_once(self.request_android_permissions,1)
        return root
    def request_android_permissions(self, *_):
        if platform != 'android': return
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
        except Exception: pass
        try:
            from jnius import autoclass
            Env=autoclass('android.os.Environment'); Ver=autoclass('android.os.Build$VERSION')
            if Ver.SDK_INT>=30 and not Env.isExternalStorageManager():
                Intent=autoclass('android.content.Intent'); Settings=autoclass('android.provider.Settings'); Uri=autoclass('android.net.Uri')
                act=autoclass('org.kivy.android.PythonActivity').mActivity
                act.startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse('package:'+act.getPackageName())))
        except Exception: pass
    def _bg_update(self, widget, *_): self.bg_rect.pos=widget.pos; self.bg_rect.size=widget.size
    def update_status(self, *_):
        if hasattr(self,'status_label'):
            self.status_label.text=f'{self.current_path}   •   {dt.datetime.now():%H:%M:%S}   •   {self.status}'
    def notify(self, message, title='ACODE GODMODE'):
        box=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(10))
        label=Label(text=str(message),color=rgba(FG),halign='left',valign='middle')
        label.bind(size=lambda w,v:setattr(w,'text_size',(v[0],None)))
        box.add_widget(label); box.add_widget(FlatButton(text='OK',on_release=lambda *_:popup.dismiss()))
        popup=Popup(title=title,content=box,size_hint=(.9,.48),background_color=rgba(PANEL)); popup.open()
    def prompt(self, title, hint='', initial='', callback=None, multiline=False):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
        field=TextInput(text=initial,hint_text=hint,multiline=multiline,size_hint_y=1,
                        background_color=rgba('#050505'),foreground_color=rgba(FG),cursor_color=rgba(ACCENT))
        box.add_widget(field); buttons=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(6))
        popup=Popup(title=title,content=box,size_hint=(.92,.48),background_color=rgba(PANEL))
        buttons.add_widget(FlatButton(text='Cancel',on_release=lambda *_:popup.dismiss()))
        def done(*_):
            value=field.text; popup.dismiss()
            if callback: callback(value)
        buttons.add_widget(FlatButton(text='OK',on_release=done)); box.add_widget(buttons); popup.open()
        return popup
    def refresh_tab_buttons(self):
        if not hasattr(self,'tab_buttons'): return
        self.tab_buttons.clear_widgets()
        for tab in self.tabs:
            name=('* ' if tab.modified else '')+tab.title
            btn=FlatButton(text=name+'  x',size_hint_x=None,width=dp(max(110,min(220,len(name)*9+40))))
            btn.bind(on_release=lambda _,t=tab:self.activate_tab(t)); self.tab_buttons.add_widget(btn)
    def new_file(self):
        tab=EditorTab(self); self.tabs.append(tab); self.activate_tab(tab)
    def activate_tab(self, tab):
        if tab not in self.tabs:return
        self.active=tab; self.editor_host.clear_widgets(); self.editor_host.add_widget(tab)
        self.current_path=tab.path or tab.title; self.refresh_tab_buttons(); self.status='Editing'
    def close_tab(self, tab=None):
        tab=tab or self.active
        if not tab:return
        if tab.modified:
            self.prompt('Unsaved changes',f'Save {tab.title} before closing? Type yes to save, anything else to discard.',callback=lambda v:self._close_after_prompt(tab,v))
        else:self._remove_tab(tab)
    def _close_after_prompt(self,tab,value):
        if value.strip().lower() in ('yes','y','بله'): self.save_tab(tab)
        self._remove_tab(tab)
    def _remove_tab(self,tab):
        if tab in self.tabs:self.tabs.remove(tab)
        if self.tabs:self.activate_tab(self.tabs[-1])
        else:self.new_file()
    def file_popup(self, title, callback, initial=None):
        start=str(initial or self.project or self.root_dir)
        if not Path(start).exists():start=str(self.root_dir)
        chooser=FileChooserListView(path=start, filters=['!*~'], dirselect=False)
        box=BoxLayout(orientation='vertical',spacing=dp(6),padding=dp(6)); box.add_widget(chooser)
        row=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(5))
        popup=Popup(title=title,content=box,size_hint=(.96,.88),background_color=rgba(PANEL))
        row.add_widget(FlatButton(text='Cancel',on_release=lambda *_:popup.dismiss()))
        def choose(*_):
            selection=chooser.selection
            if selection: popup.dismiss(); callback(selection[0])
        row.add_widget(FlatButton(text='Select',on_release=choose)); box.add_widget(row); popup.open()
    def open_file(self):
        def opened(path):
            p=Path(path)
            try:
                if p.is_dir(): self.project=p; self.show_explorer(); return
                raw=p.read_bytes(); text=None
                for enc in ('utf-8-sig','utf-16','utf-8','cp1252'):
                    try:text=raw.decode(enc); break
                    except UnicodeDecodeError:continue
                if text is None: raise UnicodeError('Unsupported file encoding')
                for tab in self.tabs:
                    if tab.path==str(p):self.activate_tab(tab);return
                tab=EditorTab(self,p,text); self.tabs.append(tab); self.activate_tab(tab); self.add_recent(str(p)); self.console.write(f'Opened {p}','system')
            except Exception as exc:self.console.write(f'Open failed: {exc}','stderr')
        self.file_popup('Open file',opened)
    def open_path(self,path):
        try:
            p=Path(path); text=p.read_text(encoding='utf-8')
            tab=EditorTab(self,p,text); self.tabs.append(tab); self.activate_tab(tab); self.add_recent(str(p))
        except Exception as exc:self.console.write(f'Open failed: {exc}','stderr')
    def save(self):
        if self.active:
            if self.active.path:self.save_tab(self.active)
            else:self.save_as()
    def save_tab(self,tab):
        try:
            path=Path(tab.path) if tab.path else self.root_dir/(tab.title if '.' in tab.title else tab.title+'.py')
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(tab.get_text(),encoding=tab.encoding or 'utf-8')
            tab.path=str(path); tab.title=path.name; tab.modified=False; self.current_path=str(path)
            self.console.write(f'Saved {path}','system'); self.add_recent(str(path)); self.refresh_tab_buttons(); self.status='Saved'; return True
        except Exception as exc:self.console.write(f'Save failed: {exc}','stderr'); return False
    def save_as(self):
        if not self.active:return
        self.prompt('Save as','Enter full file path',str(self.root_dir/'untitled.py'),lambda value:self._save_as_path(value))
    def _save_as_path(self,value):
        if not value.strip():return
        self.active.path=str(Path(value).expanduser()); self.active.title=Path(value).name; self.save_tab(self.active)
    def add_recent(self,path):
        self.recent=[path]+[p for p in self.recent if p!=path]; self.recent=self.recent[:20]
        self.settings['recent_files']=self.recent; self.save_settings()
    def save_settings(self):
        try:self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as exc:self.console.write(f'Settings error: {exc}','stderr')
    def save_session(self):
        try:self.session_path.write_text(json.dumps({'tabs':[t.path for t in self.tabs if t.path],'active':self.active.path if self.active else None,'project':str(self.project) if self.project else None},ensure_ascii=False),encoding='utf-8')
        except Exception as exc:self.console.write(f'Session save error: {exc}','stderr')
    def restore_session(self):
        try:
            data=json.loads(self.session_path.read_text(encoding='utf-8'))
            for path in data.get('tabs',[]):
                if path and Path(path).is_file():self.open_path(path)
            if data.get('project') and Path(data['project']).is_dir():self.project=Path(data['project'])
        except Exception:pass
    def run_current(self):
        if not self.active:return
        ext=Path(self.active.path or self.active.title).suffix.lower()
        if ext in ('.html','.htm'):self.run_html()
        elif ext in ('.py',''):self.run_python()
        else:self.console.write(f'No runtime for {ext or "this file"}','warning')
    def run_python(self):
        if not self.active:self.console.write('Open a Python file first.','warning');return
        source=self.active.get_text(); filename=self.active.path or '<editor>'
        cwd=Path(self.active.path).parent if self.active.path else self.root_dir
        if self.project and self.project.is_dir():cwd=self.project
        stdout=StringIO(); stderr=StringIO(); namespace={'__name__':'__main__','__file__':filename,'__builtins__':__builtins__}
        self.console.write(f'Running {filename} with embedded Python exec...','system')
        old=os.getcwd()
        try:
            os.chdir(str(cwd))
            with redirect_stdout(stdout),redirect_stderr(stderr):exec(compile(source,filename,'exec'),namespace,namespace)
            self.last_run_globals=namespace; self.status='Execution finished'
        except SystemExit as exc:stderr.write(f'SystemExit: {exc}\n')
        except Exception:traceback.print_exc(file=stderr);self.status='Execution error'
        finally:
            try:os.chdir(old)
            except Exception:pass
        out=stdout.getvalue(); err=stderr.getvalue()
        if out:self.console.write(out.rstrip(),'stdout')
        if err:self.console.write(err.rstrip(),'stderr')
        if not out and not err:self.console.write('Execution finished (no output).','system')
    def run_html(self):
        if not self.active:return
        source=self.active.get_text()
        if self.active.path:self.save_tab(self.active)
        html=BoxLayout(orientation='vertical',spacing=dp(5),padding=dp(6))
        html.add_widget(Label(text='HTML source preview',color=rgba(ACCENT),size_hint_y=None,height=dp(35)))
        preview=TextInput(text=source,readonly=True,background_color=rgba('#050505'),foreground_color=rgba(FG),font_size='12sp')
        html.add_widget(preview)
        row=BoxLayout(size_hint_y=None,height=dp(48)); row.add_widget(FlatButton(text='Open in browser',on_release=lambda *_:self.open_html_browser(source)))
        html.add_widget(row); popup=Popup(title='HTML Preview',content=html,size_hint=(.96,.9)); popup.open()
    def open_html_browser(self,source):
        try:
            path=self.home/'preview.html';path.write_text(source,encoding='utf-8');webbrowser.open(path.as_uri())
            self.console.write('HTML preview opened in browser.','system')
        except Exception as exc:self.console.write(f'HTML preview failed: {exc}','stderr')
    def show_explorer(self):
        start=str(self.project or self.root_dir)
        chooser=FileChooserListView(path=start,dirselect=False)
        box=BoxLayout(orientation='vertical',spacing=dp(6),padding=dp(6));box.add_widget(chooser)
        row=GridLayout(cols=3,size_hint_y=None,height=dp(48),spacing=dp(4));popup=Popup(title='PROJECT EXPLORER',content=box,size_hint=(.96,.9))
        def open_selected(*_):
            if chooser.selection:popup.dismiss();self.open_path(chooser.selection[0])
        def set_folder(*_):
            folder=chooser.path;self.project=Path(folder);self.console.write(f'Project: {folder}','system');popup.dismiss()
        row.add_widget(FlatButton(text='Open',on_release=open_selected));row.add_widget(FlatButton(text='Use folder',on_release=set_folder));row.add_widget(FlatButton(text='Close',on_release=lambda *_:popup.dismiss()))
        box.add_widget(row);popup.open()
    def find(self):
        self.prompt('Find','Text to find',callback=lambda q:self._find_text(q,False))
    def replace(self):
        self.prompt('Find and replace','Search text',callback=self._ask_replace_value)
    def _ask_replace_value(self,needle):
        if not needle:return
        self.prompt('Replace','Replacement text',callback=lambda repl:self._replace_all(needle,repl))
    def _find_text(self,needle,unused=False):
        if not needle or not self.active:return
        text=self.active.get_text(); start=self.active.editor.cursor_index()
        pos=text.lower().find(needle.lower(),start)
        if pos<0:pos=text.lower().find(needle.lower())
        if pos<0:self.console.write(f'No match: {needle}','warning');return
        self.active.editor.select_text(pos,pos+len(needle));self.active.editor.cursor=self.active.editor.get_cursor_from_index(pos+len(needle))
    def _replace_all(self,needle,repl):
        if not self.active or not needle:return
        text=self.active.get_text(); count=text.lower().count(needle.lower())
        pattern=re.compile(re.escape(needle),re.I); self.active.editor.text=pattern.sub(lambda _:repl,text)
        self.console.write(f'Replaced {count} occurrence(s).','system')
    def format_document(self):
        if not self.active:return
        ext=Path(self.active.path or self.active.title).suffix.lower(); text=self.active.get_text()
        try:
            if ext=='.json':text=json.dumps(json.loads(text),ensure_ascii=False,indent=4)
            elif ext=='.py':text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
            else:text='\n'.join(line.rstrip() for line in text.splitlines())
            self.active.editor.text=text;self.active.modified=True;self.console.write('Document formatted.','system')
        except Exception as exc:self.console.write(f'Format failed: {exc}','stderr')
    def toggle_console(self):
        if self.console.parent:self.root.remove_widget(self.console)
        else:self.root.add_widget(self.console,index=1)
    def show_settings(self):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
        wrap=FlatButton(text='Toggle word wrap: '+('ON' if self.word_wrap else 'OFF'))
        def toggle(*_):
            self.word_wrap=not self.word_wrap;wrap.text='Toggle word wrap: '+('ON' if self.word_wrap else 'OFF')
            if self.active:self.active.editor.text=self.active.editor.text
        wrap.bind(on_release=toggle);box.add_widget(wrap)
        box.add_widget(FlatButton(text='Save all open files',on_release=lambda *_:[self.save_tab(t) for t in self.tabs if t.modified]))
        box.add_widget(FlatButton(text='Clear console',on_release=lambda *_:self.console.clear()))
        box.add_widget(FlatButton(text='About',on_release=lambda *_:self.notify('ACODE GODMODE Android IDE\nPython + Kivy','About')))
        popup=Popup(title='Settings',content=box,size_hint=(.9,.55));popup.open()
    def on_stop(self):
        self.save_session();self.save_settings()

if __name__ == '__main__':
    AcodeApp().run()
