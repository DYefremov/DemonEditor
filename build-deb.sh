#!/bin/bash
VER="0.3.0_Pre-alpha"
B_PATH="dist/DemonEditor"
DEB_PATH="$B_PATH/usr/share/demoneditor"

mkdir -p $B_PATH
cp -TRv deb $B_PATH
cp -Rv app $DEB_PATH
cp -Rv start.py $DEB_PATH

cd dist
fakeroot dpkg-deb --build DemonEditor
mv DemonEditor.deb DemonEditor_$VER.deb

rm -R DemonEditor




