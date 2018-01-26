# DemonEditor

Enigma2 channel and satellites list editor for GNU/Linux.                                                                          
Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).                                                   
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc)

Keyboard shortcuts:                                                                                                                
Ctrl + X, C, V, Up, Down, PageUp, PageDown, S, T, E, L, H, Space; Insert, Delete, F2.
Insert - copies the selected channels from the main list to the bouquet or inserts (creates) a new bouquet.                        
Ctrl + X - only in bouquet list. Ctrl + C - only in services list.                                                                 
Clipboard is "rubber". There is an accumulation before the insertion!                                                              
Ctrl + E, F2 - edit/rename.                                                                                                        
Ctrl + S, T, E in Satellites edit tool for create and edit satellite or transponder.                                               
Ctrl + L - parental lock.                                                                                                          
Ctrl + H - hide/skip.                                                                                                              
Left/Right - remove selection.                                                                                                     

Multiple selections in lists only with Space key (as in file managers)!                                                                                                                                                                             

Extra:                                                                                                                             
Ability to import IPTV into bouquet from m3u files(Enigma2 only)!                                                                                
Tool for downloading picons from lyngsat.com.                                                                                      

Tests only in image based on OpenPLi or last BPanther(neutrino) images with GM 990 Spark Reloaded receiver
in my preferred linux distro (Last Linux Mint 18.* - MATE 64-bit)!

Minimum requirements: Python >= 3.5.2 and GTK+ 3 with PyGObject bindings.

Terrestrial and cable channels at the moment are not supported!

Note. To create a simple debian package, you can use the build-deb.sh

