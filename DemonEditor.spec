# -*- mode: python ; coding: utf-8 -*-

EXE_NAME = 'start.py'
DIR_PATH = os.getcwd()
PATH_EXE = [os.path.join(DIR_PATH, EXE_NAME)]

block_cipher = None

ui_files = [('app\\ui\\*.glade', 'ui'),
            ('app\\ui\\*.css', 'ui'),
            ('app\\ui\\*.ui', 'ui'),
            ('app\\ui\\lang*', 'share\\locale'),
            ('app\\ui\\icons*', 'share\\icons')
            ]


a = Analysis([EXE_NAME],
             pathex=PATH_EXE,
             binaries=[],
             datas=ui_files,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=['youtube_dl', 'tkinter'],
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
