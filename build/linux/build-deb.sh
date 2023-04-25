#!/bin/bash
VER="3.6.2_Beta"
B_PATH="dist/DemonEditor"
DEB_PATH="$B_PATH/usr/share/demoneditor"

mkdir -p $B_PATH
cp -TRv deb $B_PATH
rsync --exclude=app/ui/lang --exclude=app/ui/icons --exclude=__pycache__ -arv ../../app $DEB_PATH
rsync --exclude=__pycache__ -arv ../../extensions $DEB_PATH

cd dist
fakeroot dpkg-deb -Zxz --build DemonEditor
mv DemonEditor.deb DemonEditor_$VER.deb

rm -R DemonEditor
