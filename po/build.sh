#!/bin/bash
#xgettext --keyword=translatable --sort-output -L Glade -o po/demon-editor.po app/ui/main_window.glade

for dir in */;
do
  msgfmt $dir* -o ../app/ui/lang/${dir%/}/LC_MESSAGES/demon-editor.mo
done