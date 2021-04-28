# <img src="app/ui/icons/hicolor/96x96/apps/demon-editor.png" width="32" /> DemonEditor
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![platform](https://img.shields.io/badge/platform-windows-lightgrey)
## Enigma2 channel and satellite list editor for MS Windows (experimental).  

[<img src="https://user-images.githubusercontent.com/7511379/116426009-6bd3fa80-a84b-11eb-81ea-3407396a0c4b.png" width="850"/>](https://user-images.githubusercontent.com/7511379/116426009-6bd3fa80-a84b-11eb-81ea-3407396a0c4b.png)   

Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).  
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc).                                
**The functionality and performance of this version may be different from the [Linux version](https://github.com/DYefremov/DemonEditor)!**

## Main features of the program
* Editing bouquets, channels, satellites.
* Import function.
* Backup function.
* Extended support of IPTV.
* Support of picons.
* Importing services, downloading picons and updating satellites from the Web.
* Import to bouquet(Neutrino WEBTV) from m3u.
* Export of bouquets with IPTV services in m3u.
* Assignment of EPGs from DVB or XML for IPTV services (only Enigma2, experimental).
* Preview (playback) of IPTV or other streams directly from the bouquet list.
* Control panel with the ability to view EPG and manage timers (via HTTP API, experimental).
* Simple FTP client (experimental). 

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
*Python >= 3.5.2, GTK+ >= 3.22 with PyGObject bindings, python3-requests.*
                                                                    
## Important
**This version is not fully tested and has experimental status!**

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
