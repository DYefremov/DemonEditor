# DemonEditor

## Experimental version of Enigma2 channel and satellites list editor for MacOS.
Experimental support of Neutrino-MP or others on the same basis (BPanther, etc).                                                   
Focused on the convenience of working in lists from the keyboard. The mouse is also fully supported (Drag and Drop etc)

## Note
This version is only for users those who wish to try running this program on MacOS.
The functionality and performance of this version may be very different from the main version!                           
**Not all features are supported and tested!**                                                                    
                                             
### Minimum requirements:
Python >= **3.5**, GTK+ >= **3.16**, pygobject3, adwaita-icon-theme, python3-requests.                                  
**Installation:**                                                                             
```brew install gtk+3 pygobject3 adwaita-icon-theme```                                                                  
```pip3 install requests```

### Launching                                                                                                           
To start the program, in most cases it is enough to download the archive,
unpack and run it from the terminal with the command: ```./start.py```
                                                                                                                                                                                                                                                
### Note.
**Terrestrial(DVB-T/T2) and cable channels are supported(Enigma2 only) with limitation!** 

Main supported **lamedb** format is version **4**. Versions **3** and **5** has only experimental support!                                                                                                                                          
For version **3** is only read mode available. When saving, version **4** format is used instead! 
