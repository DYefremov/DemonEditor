# <img src="app/ui/icons/hicolor/96x96/apps/demon-editor.png" width="32" /> DemonEditor
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![platform](https://img.shields.io/badge/platform-linux%20|%20macos-lightgrey)  
### Enigma2 channel and satellite list editor for GNU/Linux. 
[<img src="https://user-images.githubusercontent.com/7511379/118884719-8277e980-b8ff-11eb-8621-c8c4afd6181b.png" width="560"/>](https://user-images.githubusercontent.com/7511379/118884719-8277e980-b8ff-11eb-8621-c8c4afd6181b.png)  

Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).                                                   
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc).

## Main features of the program
* Editing bouquets, channels, satellites.  
  [<img src="https://user-images.githubusercontent.com/7511379/118884747-8ad02480-b8ff-11eb-9104-8cf8fb6e785d.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118884747-8ad02480-b8ff-11eb-9104-8cf8fb6e785d.png)
* Import function.  
  [<img src="https://user-images.githubusercontent.com/7511379/118526825-4dc23180-b749-11eb-8197-e9bbccbc3bdf.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118526825-4dc23180-b749-11eb-8197-e9bbccbc3bdf.png)
* Backup function.  
  [<img src="https://user-images.githubusercontent.com/7511379/118528402-f58c2f00-b74a-11eb-9b84-edf220526e6e.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118528402-f58c2f00-b74a-11eb-9b84-edf220526e6e.png)
* Support of picons.  
  [<img src="https://user-images.githubusercontent.com/7511379/118526864-5c104d80-b749-11eb-8497-6e8c78542ab1.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118526864-5c104d80-b749-11eb-8497-6e8c78542ab1.png)
* Importing services, downloading picons and updating satellites from the Web.  
  [<img src="https://user-images.githubusercontent.com/7511379/118530243-1a81a180-b74d-11eb-8e01-aea904d954af.png" width="250"/>](https://user-images.githubusercontent.com/7511379/118530243-1a81a180-b74d-11eb-8e01-aea904d954af.png)
  [<img src="https://user-images.githubusercontent.com/7511379/118526706-31be9000-b749-11eb-9956-c4bf2e13f968.png" width="292"/>](https://user-images.githubusercontent.com/7511379/118526706-31be9000-b749-11eb-9956-c4bf2e13f968.png)
* Extended support of IPTV.
* Import to bouquet(Neutrino WEBTV) from m3u.
* Export of bouquets with IPTV services in m3u.
* Assignment of EPG from DVB or XML for IPTV services (only Enigma2, experimental).
* Preview (playback) of IPTV or other streams directly from the bouquet list.  
  [<img src="https://user-images.githubusercontent.com/7511379/118884891-b3f0b500-b8ff-11eb-8717-3588d6e089de.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118884891-b3f0b500-b8ff-11eb-8717-3588d6e089de.png)
* Control panel with the ability to view EPG and manage timers (via HTTP API, experimental).  
  [<img src="https://user-images.githubusercontent.com/7511379/118886284-66754780-b901-11eb-9068-29b5a607ccaf.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118886284-66754780-b901-11eb-9068-29b5a607ccaf.png)
* Simple FTP client (experimental).   
  [<img src="https://user-images.githubusercontent.com/7511379/118527372-e8bb0b80-b749-11eb-9653-4ad64c99a05a.png" width="480"/>](https://user-images.githubusercontent.com/7511379/118527372-e8bb0b80-b749-11eb-9653-4ad64c99a05a.png)
  
#### Keyboard shortcuts
* **Ctrl + X** - only in bouquet list.
* **Ctrl + C** - only in services list.                                                              
Clipboard is **"rubber"**. There is an accumulation before the insertion!                                                                                                                     
* **Ctrl + Insert** - copies the selected channels from the main list to the bouquet  
  beginning or inserts (creates) a new bouquet.  
* **Ctrl + BackSpace** - copies the selected channels from the main list to the bouquet end.
* **Ctrl + E** - edit.                                                                                                                                                                                                                                                                                                                    
* **Ctrl + R, F2** - rename.                                                                                                                                                                                                                                                                                                                     
* **Ctrl + S, T** in Satellites edit tool for create satellite or transponder.                                                                 
* **Ctrl + L** - parental lock.                                                                                                          
* **Ctrl + H** - hide/skip.                                                                                                                                                                                                 
* **Ctrl + P** - start play IPTV or other stream in the bouquet list.                                                                                        
* **Ctrl + Z** - switch(**zap**) the channel(works when the HTTP API is enabled, Enigma2 only).                         
* **Ctrl + W** - switch to the channel and watch in the program.                                                                                                                                                                                                                                                                                                                                                                                                     
* **Space** - select/deselect.                                                                                                                                                                                                                                                                                                           
* **Left/Right** - remove selection.                                                                                       
* **Ctrl + Up, Down, PageUp, PageDown, Home, End**- move selected items in the list.  
* **Ctrl + O** - (re)load user data from current dir.                                                                   
* **Ctrl + D** - load data from receiver.                                                                                                                                                         
* **Ctrl + U/B** - upload data/bouquets to receiver.
* **Ctrl + I** - extra info, details.
* **Ctrl + F** - show/hide search bar.
* **Ctrl + Shift + F** - show/hide filter bar.
                                                                          
For **multiple** selection with the mouse, press and hold the **Ctrl** key!

## Minimum requirements
*Python >= 3.6, GTK+ >= 3.22, python3-gi, python3-gi-cairo, python3-requests.*

***Optional:** python3-pil, python3-chardet.*                      
## Installation and Launch
* ### Linux                                                                                                          
To start the program, in most cases it is enough to download the [archive](https://github.com/DYefremov/DemonEditor/archive/master.zip), unpack  
and run it by double clicking on DemonEditor.desktop in the root directory,  
or launching from the console with the command:```./start.py```                                                                                
Extra folders can be deleted, excluding the *app* folder and root files like *DemonEditor.desktop* and *start.py*!      

To create a simple **debian package**, you can use the *build-deb.sh.* You can also download a ready-made *.deb package from the [releases](https://github.com/DYefremov/DemonEditor/releases) page.                                                 
Users of **LTS** versions of [Ubuntu](https://ubuntu.com/) or distributions based on them can use [PPA](https://launchpad.net/~dmitriy-yefremov/+archive/ubuntu/demon-editor) repository.  
A ready-made [package](https://aur.archlinux.org/packages/demoneditor-bin) is also available for [Arch Linux](https://archlinux.org/) users in the [AUR](https://aur.archlinux.org/) repository. 
* ### macOS
**This program can be run on macOS.** To work in this OS, you must use a [separate branch](https://github.com/DYefremov/DemonEditor/tree/experimental-mac). A ready-made package can be downloaded from the [releases](https://github.com/DYefremov/DemonEditor/releases) page.  
**The functionality and performance of this version may be different from the Linux version!**

## Important
The program is tested only with [openATV](https://www.opena.tv/) image and **Formuler F1** receiver in [Linux Mint](https://linuxmint.com/) (MATE 64-bit) distribution!

Terrestrial(DVB-T/T2) and cable(DVB-C) channels are only supported for Enigma2.                                                                                                
Main supported *lamedb* format is version **4**. Versions **3** and **5** has only **experimental** support! For version **3** is only read mode available. When saving, version **4** format is used instead.   

When using the multiple import feature, from *lamedb* will be taken data **only for channels that are in the selected bouquets!**
If you need full set of the data, including *[satellites, terrestrial, cables].xml* (current files will be overwritten), 
just load your data via *"File/Open"* and press *"Save"*. When importing separate bouquet files, only those services 
(excluding IPTV) that are in the **current open lamedb** (main list of services) will be imported.

For streams playback, this app supports [VLC](https://www.videolan.org/vlc/), [MPV](https://mpv.io/) and [GStreamer](https://gstreamer.freedesktop.org/). Depending on your distro, you may need to install additional packages and libraries. 
#### Command line arguments:
* **-l** - write logs to file.
* **-d on/off** - turn on/off debug mode. Allows to display more information in the logs.

## License
Licensed under the [MIT](LICENSE) license.                  
