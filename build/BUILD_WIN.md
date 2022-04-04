## Launch
The best way to run this program from source is using of [MSYS2](https://www.msys2.org/) platform. 
1. Download and install the platform as described [here](https://www.msys2.org/) up to point 4. 
2. Launch **mingw64** shell.  
![mingw64](https://user-images.githubusercontent.com/7511379/161400639-898ceb10-7de8-4557-bde1-25fe32bdfb03.png)
3. Run first `pacman -Suy` After that, you may need to restart the terminal and re-run the update command. 
4. Install minimal required packages:  
   `pacman -S mingw-w64-x86_64-gtk3 mingw-w64-x86_64-python3 mingw-w64-x86_64-python3-gobject mingw-w64-x86_64-python3-pip mingw-w64-x86_64-python3-requests`  
Optional: `pacman -S mingw-w64-x86_64-python3-pillow`  
To support streams playback, install the following packages (the list may not be complete):   
For [MPV](https://mpv.io/) `pacman -S mingw-w64-x86_64-mpv`,  
For  [GStreamer](https://gstreamer.freedesktop.org/)  `pacman -S mingw-w64-x86_64-gst-libav mingw-w64-x86_64-gst-plugins-bad mingw-w64-x86_64-gst-plugins-base mingw-w64-x86_64-gst-plugins-good mingw-w64-x86_64-gstreamer`  
5. Download and unzip the archive with sources from preferred branch (e.g. [master](https://github.com/DYefremov/DemonEditor/archive/refs/heads/master.zip)) in to folder where MSYS2 is installed. E.g: `c:\msys64\home\username\`
6. Run mingw64 shell. Go to the folder where the program was unpacked. E.g: `cd DemonEditor/`
And run: `./start.py`

## Building a package
To build a standalone package, we can use [PyInstaller](https://pyinstaller.readthedocs.io/en/stable/). 
1. Launch mingw64 shell.
2. Install PyInstaller via pip:  `pip3 install pyinstaller`
3. Go to the folder where the program was unpacked. E.g: `c:\msys64\home\username\DemonEditor\`
4. Сopy and replace the files from the /build/win/ folder to the root .
5. Go to the folder with the program in the running terminal:  `cd DemonEditor/`
6. Give the following command: `pyinstaller.exe DemonEditor.spec`
7. Wait until the operation end. In the dist folder you will find a ready-made build.

### Appearance
To change the look we can use third party [Gtk3 themes and Icon sets](https://www.gnome-look.org).   
To set the default theme:
1. Сreate a folder "`\etc\gtk-3.0\`" in the root of the finished build folder.
2. Create a _settings.ini_ file in this folder with the following content: 
  ```
  [Settings]
  gtk-icon-theme-name = Adwaita
  gtk-theme-name = Windows-10
  ```
In this case, we are using the default icon theme "Adwaita" and the [third party theme](https://github.com/B00merang-Project/Windows-10) "Windows-10".
Themes and icon sets should be located in the `share\themes` and `share\icons` folders respectively. 
To fine-tune the default theme you use, you can use the _win_style.css_ file in the `ui` folder. 
You can find more info about changing the appearance of Gtk applications on the Web yourself. 
