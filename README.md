# <img src="app/ui/icons/hicolor/96x96/apps/demon-editor.png" width="32" /> DemonEditor
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![platform](https://img.shields.io/badge/platform-linux%20|%20macos-lightgrey)  
### Enigma2 channel and satellite list editor for GNU/Linux.
Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).

## Main features of the program
* Editing bouquets, channels, satellites.  
  [<img src="https://user-images.githubusercontent.com/7511379/141680963-9b8eb6cc-c712-46b2-aefe-19769e21a7d5.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141680963-9b8eb6cc-c712-46b2-aefe-19769e21a7d5.png)
* Import function.  
  [<img src="https://user-images.githubusercontent.com/7511379/141681059-68bc1b55-6fab-436c-aa73-ef24e2e5113b.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681059-68bc1b55-6fab-436c-aa73-ef24e2e5113b.png)
* Backup function.  
  [<img src="https://user-images.githubusercontent.com/7511379/141681104-ed9b5d35-25de-426f-b9bb-2a6e4db022bb.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681104-ed9b5d35-25de-426f-b9bb-2a6e4db022bb.png)
* Support of picons.  
  [<img src="https://user-images.githubusercontent.com/7511379/141681115-957c63a3-4113-422d-bb27-2d96b1463cd1.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681115-957c63a3-4113-422d-bb27-2d96b1463cd1.png)
* Importing services, downloading picons and updating satellites from the Web.  
  [<img src="https://user-images.githubusercontent.com/7511379/141681075-28f18ea5-e456-4e84-bf64-1b7d9a95324d.png" width="262"/>](https://user-images.githubusercontent.com/7511379/141681075-28f18ea5-e456-4e84-bf64-1b7d9a95324d.png)
  [<img src="https://user-images.githubusercontent.com/7511379/141681040-b1ad190a-6bc2-4741-bb42-1fb219a0fcab.png" width="250"/>](https://user-images.githubusercontent.com/7511379/141681040-b1ad190a-6bc2-4741-bb42-1fb219a0fcab.png)
* Extended support of IPTV.
* Import to bouquet(Neutrino WEBTV) from m3u.
* Export of bouquets with IPTV services in m3u.
* Assignment of EPG from DVB or XML for IPTV services (Enigma2 only).  
  [<img src="https://user-images.githubusercontent.com/7511379/141681187-fae4e784-c9e0-43df-b499-4d38e83d6560.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681187-fae4e784-c9e0-43df-b499-4d38e83d6560.png)
* Playback of IPTV or other streams directly from the bouquet list.  
  [<img src="https://user-images.githubusercontent.com/7511379/141681129-98f78cdc-9a98-46ef-b738-618a327634d4.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681129-98f78cdc-9a98-46ef-b738-618a327634d4.png)
* Control panel (via HTTP API).  
  [<img src="https://user-images.githubusercontent.com/7511379/141684475-4511ea4f-b152-42d5-b9c8-f3e1e9a160d0.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141684475-4511ea4f-b152-42d5-b9c8-f3e1e9a160d0.png)
* Ability to view EPG and manage timers (via HTTP API).  
* Simple FTP client (experimental).   
  [<img src="https://user-images.githubusercontent.com/7511379/141681165-5679c331-72e7-4044-b365-dcdb30b1433c.png" width="480"/>](https://user-images.githubusercontent.com/7511379/141681165-5679c331-72e7-4044-b365-dcdb30b1433c.png)  

**To increase program functionality you can use [extensions](https://github.com/DYefremov/demoneditor-extensions).**   
  
#### Keyboard shortcuts
* **Ctrl + X** - only in bouquet list.
* **Ctrl + C** - only in services list.                                                               
* **Ctrl + Insert** - copies the selected channels from the main list to the bouquet  
  beginning or inserts (creates) a new bouquet.  
* **Ctrl + BackSpace** - copies the selected channels from the main list to the bouquet end.
* **Ctrl + E** - edit.                                                                                                                                                                                                                                                                                                                    
* **Ctrl + R, F2** - rename.  
* **Ctrl + Alt + R** - rename for bouquet.    
* **Ctrl + S, T** in Satellites edit tool for create satellite or transponder.                                                                 
* **Ctrl + L** - parental lock.                                                                                                          
* **Ctrl + H** - hide/skip.                                                                                                                                                                                                  
* **Space** - select/deselect.                                                                                                                                                                                                                                                                                                           
* **Left/Right** - remove selection.                                                                                       
* **Ctrl + Up, Down, PageUp, PageDown, Home, End**- move selected items in the list.  
* **Ctrl + O** - (re)load user data from current dir.                                                                   
* **Ctrl + D** - load data from receiver.                                                                                                                                                         
* **Ctrl + U/B** - upload data/bouquets to receiver.
* **Ctrl + I** - extra info, details.
* **Ctrl + F** - show search bar.
* **Ctrl + Shift + F** - show/hide filter bar.
* **Ctrl + T** - show/hide built-in Telnet client.
* **Ctrl + Shift + L** - show/hide logging panel.
* **Shift + P** - start play IPTV or other stream in the bouquet list.                                                                                        
* **Shift + Z** - switch(**zap**) the channel(works when the HTTP API is enabled, Enigma2 only).                         
* **Shift + W** - switch to the channel and watch in the program.        
                                                                          
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
**This program can be run on macOS.**  
To run the program on macOS, you need to install [Homebrew](https://brew.sh/).  
Then install the required components via terminal:  
```brew install python3 gtk+3 pygobject3 adwaita-icon-theme python-requests gtksourceview3```  

*Optional:* ```brew install pillow python-chardet```  

Launch is similar to Linux.

You can also download the ready-made package as a ***.dmg** file from the [releases](https://github.com/DYefremov/DemonEditor/releases) page.  
Recommended copy the package to the **Application** directory.  
Perhaps in the security settings it will be necessary to allow the launch of this application!  

* ### MS Windows  
**Windows users can also run this program.**  
One way is to use the [MSYS2](https://www.msys2.org/) platform. You can use [this](https://github.com/DYefremov/DemonEditor/blob/master/build/BUILD_WIN.md) quick guide.   
In addition, you can download a ready-made build (**64-bit**) from the [releases](https://github.com/DYefremov/DemonEditor/releases) page.  

**All builds may contain components distributed under the GPL [v3](http://www.gnu.org/licenses/gpl-3.0.html) or lower license.  
By downloading and using this packages you agree to the terms of this [license](http://www.gnu.org/licenses/gpl-3.0.html) and the possible inconvenience associated with this!** 

THIS SOFTWARE COMES WITH ABSOLUTELY NO WARRANTY.                                                                        
AUTHOR IS NOT LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY CONNECTION WITH THIS SOFTWARE.

## Important
The program is tested only with [openATV](https://www.opena.tv/) image and **Formuler F1** receiver in [Linux Mint](https://linuxmint.com/) (MATE 64-bit) distribution!  
Support for DVB-T/T2 and DVB-C channels for Neutrino is not fully implemented and has an experimental status.  

Main supported *lamedb* format is version **4**. Versions **3** and **5** has only **experimental** support! For version **3** is only read mode available. When saving, version **4** format is used instead.   

When using the multiple import feature, from *lamedb* will be taken data **only for channels that are in the selected bouquets!**
If you need full set of the data, including *[satellites, terrestrial, cables].xml* (current files will be overwritten), 
just load your data via *"File/Open"* and press *"Save"*. When importing separate bouquet files, only those services 
(excluding IPTV) that are in the **current open lamedb** (main list of services) will be imported.

**The built-in Telnet client does not support ANSI escape sequences!**

For streams playback, this app supports [VLC](https://www.videolan.org/vlc/), [MPV](https://mpv.io/) and [GStreamer](https://gstreamer.freedesktop.org/). Depending on your distro, you may need to install additional packages and libraries.   
#### Command line arguments:
* **-l** - write logs to file.
* **-d on/off** - turn on/off debug mode. Allows to display more information in the logs.

## License
Licensed under the [MIT](LICENSE) license.                  
