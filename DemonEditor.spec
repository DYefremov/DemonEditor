import os
import distutils.util

EXE_NAME = 'start.py'
DIR_PATH = os.getcwd()
COMPILING_PLATFORM = distutils.util.get_platform()
PATH_EXE = [os.path.join(DIR_PATH, EXE_NAME)]
STRIP = True

block_cipher = None

ui_files = [('app/ui/*.glade', 'ui'),
            ('app/ui/*.css', 'ui'),
            ('app/ui/*.ui', 'ui'),
            ('app/ui/lang*', 'share/locale'),
            ('app/ui/icons*', 'share/icons')
            ]

a = Analysis([EXE_NAME],
             pathex=PATH_EXE,
             binaries=None,
             datas=ui_files,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure,
          a.zipped_data,
          cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='DemonEditor',
          debug=False,
          strip=STRIP,
          upx=True,
          console=False)

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=STRIP,
               upx=True,
               name='DemonEditor')

app = BUNDLE(coll,
             name='DemonEditor.app',
             icon='icon.icns',
             bundle_identifier=None,
             info_plist={
                 'NSPrincipalClass': 'NSApplication',
                 'CFBundleName': 'DemonEditor',
                 'CFBundleDisplayName': 'DemonEditor',
                 'CFBundleGetInfoString': "Enigma2 channel and satellites editor",
                 'CFBundleShortVersionString': "0.4.8 Pre-alpha",
                 'NSHumanReadableCopyright': u"Copyright © 2020, Dmitriy Yefremov"
             })
