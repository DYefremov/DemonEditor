# <img src="app/ui/icons/hicolor/96x96/apps/demon-editor.png" width="32" /> DemonEditor
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![platform](https://img.shields.io/badge/platform-macos-lightgrey)
## Enigma2 channel and satellite list editor for macOS.
[<img src="https://user-images.githubusercontent.com/7511379/119127827-76924180-ba3d-11eb-8ba8-1dc3bdc7f191.png" width="655"/>](https://user-images.githubusercontent.com/7511379/119127827-76924180-ba3d-11eb-8ba8-1dc3bdc7f191.png)  

Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).  
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc).                                
**The functionality and performance of this version may be different from the [Linux version](https://github.com/DYefremov/DemonEditor)!**

## Main features of the program
* Editing bouquets, channels, satellites.  
  [<img src="https://user-images.githubusercontent.com/7511379/119127978-b822ec80-ba3d-11eb-8720-e458f0ccf60e.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119127978-b822ec80-ba3d-11eb-8720-e458f0ccf60e.png)
* Import function.  
   [<img src="https://user-images.githubusercontent.com/7511379/119128084-d852ab80-ba3d-11eb-8bf9-d40f4f59314b.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119128084-d852ab80-ba3d-11eb-8bf9-d40f4f59314b.png)
* Backup function.  
  [<img src="https://user-images.githubusercontent.com/7511379/119128119-e4d70400-ba3d-11eb-88b4-86e6bea21314.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119128119-e4d70400-ba3d-11eb-88b4-86e6bea21314.png)
* Support of picons.  
  [<img src="https://user-images.githubusercontent.com/7511379/119128127-e99bb800-ba3d-11eb-93d9-3444b7332778.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119128127-e99bb800-ba3d-11eb-93d9-3444b7332778.png)
* Importing services, downloading picons and updating satellites from the Web.  
   [<img src="https://user-images.githubusercontent.com/7511379/119128104-de488c80-ba3d-11eb-800c-e070f476f6a8.png" width="250"/>](https://user-images.githubusercontent.com/7511379/119128104-de488c80-ba3d-11eb-800c-e070f476f6a8.png)
  [<img src="https://user-images.githubusercontent.com/7511379/119128066-d2f56100-ba3d-11eb-864a-bf2c22c74d5e.png" width="259"/>](https://user-images.githubusercontent.com/7511379/119128066-d2f56100-ba3d-11eb-864a-bf2c22c74d5e.png)
* Extended support of IPTV.
* Import to bouquet(Neutrino WEBTV) from m3u.
* Export of bouquets with IPTV services in m3u.
* Assignment of EPGs from DVB or XML for IPTV services (only Enigma2, experimental).
* Playback of IPTV or other streams directly from the bouquet list (should be installed [VLC](https://www.videolan.org/vlc/)).
* Control panel with the ability to view EPG and manage timers (via HTTP API, experimental).  
  [<img src="https://user-images.githubusercontent.com/7511379/119128157-f28c8980-ba3d-11eb-975e-cdbac32349ed.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119128157-f28c8980-ba3d-11eb-975e-cdbac32349ed.png)
* Simple FTP client (experimental).   
[<img src="https://user-images.githubusercontent.com/7511379/119128176-f7e9d400-ba3d-11eb-813d-08972d103cce.png" width="480"/>](https://user-images.githubusercontent.com/7511379/119128176-f7e9d400-ba3d-11eb-813d-08972d103cce.png)

#### Keyboard shortcuts                                                                                                                                                                                            
* **&#8984; + X** - only in bouquet list.
* **&#8984; + C** - only in services list.                                                                                                                                                    
Clipboard is **"rubber"**. There is an accumulation before the insertion!                                                              
* **&#8984; + E** - edit. 
* **&#8984; + R, F2** - rename.
* **&#8984; + S, T** in Satellites edit tool for create satellite or transponder.
* **&#8984; + L** - parental lock.
* **&#8984; + H** - hide/skip.                                                                                                                                                                                                 
* **&#8984; + P** - start play IPTV or other stream in the bouquet list.
* **&#8984; + Z** - switch(**zap**) the channel(works when the HTTP API is enabled, Enigma2 only).                         
* **&#8984; + W** - switch to the channel and watch in the program.
* **&#8984; + Up/Down** - move selected items in the list. 
* **&#8984; + O** - (re)load user data from current dir. 
* **&#8984; + D** - load data from receiver. 
* **&#8984; + U/B** - upload data/bouquets to receiver.
* **&#8984; + F** - show/hide search bar.
* **&#8679; + &#8984; + F** - show/hide filter bar.
* **Left/Right** - remove selection.

For **multiple** selection with the mouse, press and hold the **&#8984;** key!

## Minimum requirements
*Python >= 3.5.2, GTK+ >= 3.22 with PyGObject bindings, python3-requests.*
                                                                    
## Installation and Launch                                                                          
To run the program on macOS, you need to install [brew](https://brew.sh/).  
Then install the required components via terminal:  
```brew install python3 gtk+3 pygobject3 adwaita-icon-theme```                                                                  
```pip3 install requests```                                                                                                                                                                                          
#### Optional:                                                                                                          
```pip3 install pillow, pyobjc```

To start the program, just download the [archive](https://github.com/DYefremov/DemonEditor/archive/experimental-mac.zip), unpack and run it from the terminal   
with the command: ```./start.py```
## Standalone package
You can also download the ready-made package as a ***.dmg** file from the [releases](https://github.com/DYefremov/DemonEditor/releases) page.  
Recommended copy the package to the **Application** directory.  
Perhaps in the security settings it will be necessary to allow the launch of this application!  
**The package may not contain all the latest changes. Not all features can be supported and tested!**

THIS SOFTWARE COMES WITH ABSOLUTELY NO WARRANTY.                                                                        
AUTHOR IS NOT LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY CONNECTION WITH THIS SOFTWARE.                           
The package may contain components distributed under the GPL [v3](http://www.gnu.org/licenses/gpl-3.0.html) or lower license.  
By downloading and using this package you agree to the terms of this [license](http://www.gnu.org/licenses/gpl-3.0.html) and the possible inconvenience associated with this! 

#### Building your own package                                                                                                                                                                                                                                                                
Install [PyInstaller](https://www.pyinstaller.org/) with the command from the terminal:
                                                                   
```pip3 install pyinstaller```
                                                                                          
and in the root dir run command: 
                                                                                        
```pyinstaller DemonEditor.spec``` 
## Important
**This version may not be fully tested!**

Terrestrial(DVB-T/T2) and cable(DVB-C) channels are only supported for Enigma2.                                                                                                
Main supported *lamedb* format is version **4**. Versions **3** and **5** has only **experimental** support!                                                                                                                                                        
For version **3** is only read mode available. When saving, version **4** format is used instead.   

When using the multiple import feature, from *lamedb* will be taken data **only for channels that are in the selected bouquets!**
If you need full set of the data, including *[satellites, terrestrial, cables].xml* (current files will be overwritten), 
just load your data via *"File/Open"* and press *"Save"*. When importing separate bouquet files, only those services 
(excluding IPTV) that are in the **current open lamedb** (main list of services) will be imported.
#### Command line arguments:
* **-l** - write logs to file.
* **-d on/off** - turn on/off debug mode. Allows to display more information in the logs.
* **-t on/off** - show/hide simple built-in **telnet** client (experimental). **ANSI escape sequences are not supported!**

## License
Licensed under the [MIT](LICENSE) license.                                     
