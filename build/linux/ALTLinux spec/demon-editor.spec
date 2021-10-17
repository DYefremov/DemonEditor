Name:  demon-editor
Version: 2.0
Release: slava0
BuildArch: noarch
Summary: Enigma2 channel and satellite list editor
Url: https://github.com/DYefremov/DemonEditor
License: MIT
Group: Other
Source: %name-%version-development.tar.gz
Patch0: %name-%version-development-startfix.patch
AutoReq: no
Requires: python3 python3-module-requests python3-module-pygobject3 python3-module-chardet libmpv1 
BuildRequires: python3-dev python3-module-mpl_toolkits

%description
Enigma2 channel and satellites list editor for GNU/Linux.

Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc).

Main features of the program:
   Editing bouquets, channels, satellites.
   Import function.
   Backup function.
   Support of picons.
   Importing services, downloading picons and updating satellites from the Web.
   Extended support of IPTV.
   Import to bouquet(Neutrino WEBTV) from m3u.
   Export of bouquets with IPTV services in m3u.
   Assignment of EPGs from DVB or XML for IPTV services (only Enigma2, experimental).
   Playback of IPTV or other streams directly from the bouquet list.
   Control panel with the ability to view EPG and manage timers (via HTTP API, experimental).
   Simple FTP client (experimental).

%prep 
%setup -n %name-%version-development
%patch0 -p1

%install
%__install -d %buildroot%_datadir/demoneditor/app
 %__install -m644 app/*py %buildroot%_datadir/demoneditor/app
%__install -d %buildroot%_datadir/demoneditor/app/eparser
 %__install -m644 app/eparser/*py %buildroot%_datadir/demoneditor/app/eparser
%__install -d %buildroot%_datadir/demoneditor/app/eparser/enigma
 %__install -m644 app/eparser/enigma/*py %buildroot%_datadir/demoneditor/app/eparser/enigma
%__install -d %buildroot%_datadir/demoneditor/app/eparser/neutrino
 %__install -m644 app/eparser/neutrino/*py %buildroot%_datadir/demoneditor/app/eparser/neutrino
%__install -d %buildroot%_datadir/demoneditor/app/tools
 %__install -m644 app/tools/*py %buildroot%_datadir/demoneditor/app/tools
%__install -d %buildroot%_datadir/demoneditor/app/ui
 %__install -m644 app/ui/*py %buildroot%_datadir/demoneditor/app/ui
 %__install -m644 app/ui/*glade %buildroot%_datadir/demoneditor/app/ui
 %__install -m644 app/ui/*css %buildroot%_datadir/demoneditor/app/ui
 %__install -m644 app/ui/*ui %buildroot%_datadir/demoneditor/app/ui
 %__install -m755 start.py %buildroot%_datadir/demoneditor

%__install -d %buildroot%_iconsdir/hicolor/96x96/apps
%__install -d %buildroot%_iconsdir/hicolor/scalable/apps
 %__install -m644 app/ui/icons/hicolor/96x96/apps/%name.* %buildroot%_iconsdir/hicolor/96x96/apps
 %__install -m644 app/ui/icons/hicolor/scalable/apps%name.* -d %buildroot%_iconsdir/hicolor/scalable/apps

%__install -d %buildroot%_datadir/locale
cp -r app/ui/lang/* %buildroot%_datadir/locale

%__install -d %buildroot%_bindir
echo "#!/bin/bash
python3 %_datadir/demoneditor/start.py $1" > %buildroot%_bindir/%name
chmod 755 %buildroot%_bindir/%name

%__install -d %buildroot%_desktopdir
%__install -m644 DemonEditor.desktop %buildroot%_desktopdir/DemonEditor.desktop

%find_lang %name

%files -f %name.lang
%doc deb/DEBIAN/README.source
%_bindir/%name
%_datadir/demoneditor
%_iconsdir/*/*/*/%name.*
%_desktopdir/DemonEditor.desktop

%changelog
* Wed Sep 29 2021 Viacheslav Dikonov <sdiconov@mail.ru> 1.0.10-slava0
- ALTLinux package


