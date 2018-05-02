# DemonEditor

## Enigma2 channel and satellites list editor for GNU/Linux.                                                                          
Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).                                                   
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc)
### Keyboard shortcuts:                                                                                                                
**Ctrl + X, C, V, Up, Down, PageUp, PageDown, Home, End, S, T, E, L, H, Space; Insert, Delete, F2, Enter, P.**                                                    
* **Insert** - copies the selected channels from the main list to the bouquet or inserts (creates) a new bouquet.                                     
* **Ctrl + X** - only in bouquet list. **Ctrl + C** - only in services list.                                                                 
Clipboard is **"rubber"**. There is an accumulation before the insertion!                                                              
* **Ctrl + E** - edit.                                                                                                                                                                                                                                                                                                                    
* **Ctrl + R, F2** - rename.                                                                                                                                                                                                                                                                                                                     
* **Ctrl + S, T** in Satellites edit tool for create satellite or transponder.                                                                 
* **Ctrl + L** - parental lock.                                                                                                          
* **Ctrl + H** - hide/skip.                                                                                                                                                                                                 
* **P** - enable/disable preview mode for IPTV in the bouquet list.                                                                                                 
* **Enter** - start play IPTV or other stream in the bouquet list.                                                      
* **Space** - select/deselect.                                                                                                                                                                                                                                                                                                           
* **Left/Right** - remove selection.                                                                                       
* **Ctrl + Up, Down, PageUp, PageDown, Home, End** - move selected items in the list.                                                                                                                                                                                                                                                                                                                                        
### Extra:
* Multiple selections in lists only with Space key (as in file managers).                                                                                                                                                                                                                                                                                                                                                                                                         
* Ability to import IPTV into bouquet (Neutrino WEBTV) from m3u files.                                                                                                                                  
* Tool for downloading picons from lyngsat.com.                                                                                                                                                  
* Preview (playing)  IPTV or other streams directly from the bouquet list(should be installed VLC).                                                                                                                                                                                                                                          
### Minimum requirements:
Python >= 3.5.2 and GTK+ 3 with PyGObject bindings.
#### Note.
To create a simple debian package, you can use the build-deb.sh                                                         

Tests only in image based on OpenPLi or last BPanther(neutrino) images with GM 990 Spark Reloaded receiver
in my preferred linux distro (Last Linux Mint 18.* - MATE 64-bit)!

**Terrestrial and cable channels at the moment are not supported!**


