import os
import datetime
import distutils.util

EXE_NAME = 'start.py'
DIR_PATH = os.getcwd()
COMPILING_PLATFORM = distutils.util.get_platform()
PATH_EXE = [os.path.join(DIR_PATH, EXE_NAME)]
STRIP = True
BUILD_DATE = datetime.datetime.now().strftime("%y%m%d")

block_cipher = None

excludes = ['app.tools.mpv',
            'gi.repository.Gst',
            'gi.repository.GstBase',
            'gi.repository.GstVideo',
            'youtube_dl',
            'tkinter']

ui_files = [('app/ui/*.glade', 'ui'),
            ('app/ui/*.css', 'ui'),
            ('app/ui/*.ui', 'ui'),
            ('app/ui/epg/*.glade', 'ui/epg'),
            ('app/ui/xml/*.glade', 'ui/xml'),
            ('app/ui/lang*', 'share/locale'),
            ('app/ui/icons*', 'share/icons'),
            ('extensions/*', 'extensions')
            ]

a = Analysis([EXE_NAME],
             pathex=PATH_EXE,
             binaries=None,
             datas=ui_files,
             hiddenimports=['fileinput', 'uuid', 'asyncio', 'getpass'],
             hookspath=[],
             runtime_hooks=[],
             hooksconfig={
                "gi": {
                    "languages": ["en", "be", "es", "it", "nl", "pl",
                                  "pt", "ru", "sk", "tr", "zh_CN"],
                    "module-versions": {
                        "Gtk": "3.0"
                    },
                },
             },
             excludes=excludes,
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
                 'CFBundleGetInfoString': "Enigma2 channel and satellite editor",
                 'LSApplicationCategoryType': 'public.app-category.utilities',
                 'LSMinimumSystemVersion': '10.13',
                 'CFBundleShortVersionString': f"3.14.2.{BUILD_DATE} Beta",
                 'NSHumanReadableCopyright': u"Copyright © 2018-2025, Dmitriy Yefremov",
                 'NSRequiresAquaSystemAppearance': 'false',
                 'NSHighResolutionCapable': 'true'
             })
