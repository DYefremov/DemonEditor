# -*- mode: python ; coding: utf-8 -*-

EXE_NAME = 'start.py'
DIR_PATH = os.getcwd()
PATH_EXE = [os.path.join(DIR_PATH, EXE_NAME)]

block_cipher = None


excludes = ['app.tools.mpv',
            'gi.repository.Gst',
            'gi.repository.GstBase',
            'gi.repository.GstVideo',
            'youtube_dl',
            'tkinter']


ui_files = [('app\\ui\\*.glade', 'ui'),
            ('app\\ui\\*.css', 'ui'),
            ('app\\ui\\*.ui', 'ui'),
            ('app\\ui\\epg\\*.glade', 'ui\\epg'),
            ('app\\ui\\xml\\*.glade', 'ui\\xml'),
            ('app\\ui\\lang*', 'share\\locale'),
            ('app\\ui\\icons*', 'share\\icons'),
            ('extensions\\*', 'extensions')
            ]


a = Analysis([EXE_NAME],
             pathex=PATH_EXE,
             binaries=[],
             datas=ui_files,
             hiddenimports=['fileinput', 'uuid', 'ctypes.wintypes', 'asyncio'],
             hookspath=[],
             runtime_hooks=[],
             hooksconfig={
                "gi": {
                    "languages": ["en", "be", "es", "it", "nl",
                                  "pl", "pt", "ru", "tr", "zh_CN"],
                    "module-versions": {
                        "Gtk": "3.0",
                        "GtkSource": "3",
                    },
                },
             },
             excludes=excludes,
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='DemonEditor',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False, icon='icon.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='DemonEditor')
