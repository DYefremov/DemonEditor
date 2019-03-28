# DemonEditor

## Enigma2 channel and satellites list editor for GNU/Linux.                                                                          
Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).                                                   
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc)
### Keyboard shortcuts:                                                                                                                
* **Ctrl + Insert** - copies the selected channels from the main list to the the bouquet beginning                                                           
 or inserts (creates) a new bouquet.                                                                                    
* **Ctrl + BackSpace** - copies the selected channels from the main list to the bouquet end.                                                                                
* **Ctrl + X** - only in bouquet list. **Ctrl + C** - only in services list.                                                                 
Clipboard is **"rubber"**. There is an accumulation before the insertion!                                                              
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
* **Ctrl + Up, Down, PageUp, PageDown, Home, End** - move selected items in the list.                                   
* **Ctrl + O** - (re)load user data from current dir.                                                                   
* **Ctrl + D** - load data from receiver.                                                                                                                                                         
* **Ctrl + U/B** upload data/bouquets to receiver.                                                                                                                                                                                                                                           
                                                                                                                                                                                                                                                                                                                                        
### Extra:                                                                                                                
* Multiple selections in lists only with Space key (as in file managers).                                                                                                                                                                                                                                                                                                                                                                                                         
* Ability to import IPTV into bouquet (Neutrino WEBTV) from m3u files.                                                  
* Ability to download picons and update satellites (transponders) from web.                                                                                                                                                                                                                            
* Preview (playing) IPTV or other streams directly from the bouquet list(should be installed VLC).                      
                                         
### Minimum requirements:
Python >= 3.5.2 and GTK+ >= 3.16 with PyGObject bindings.                                                               

### Launching                                                                                                           
To start the program, in most cases it is enough to download the archive, unpack and run it by                                                   
double clicking on DemonEditor.desktop in the root directory, or launching from the console                                                           
with the command: ```./start.py```                                                                              
Extra folders can be deleted, excluding the *app* folder and root files like *DemonEditor.desktop* and *start.py*!      
                                                                                                                                                                       
### Note.
To create a simple **debian package**, you can use the *build-deb.sh.*                                                         

Tests only with openATV image and Formuler F1 receiver in my preferred Linux distros                                    
(latest Linux Mint 18.* and 19 MATE 64-bit)!                                                                                                                                                       

**Terrestrial(DVB-T/T2) and cable(DVB-C) channels are only supported for Enigma2!**                                     

Main supported **lamedb** format is version **4**. Versions **3** and **5** has only experimental support!                                                                                                                                          
For version **3** is only read mode available. When saving, version **4** format is used instead!                                                                                                                       


