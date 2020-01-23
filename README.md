# <img src="app/ui/icons/hicolor/96x96/apps/demon-editor.png" width="32" /> DemonEditor

## Enigma2 channel and satellites list editor for macOS (experimental).
This version is only for users those who wish to try running this program on **macOS**.                                
The functionality and performance of this version may be very different from the main version!                                                     
**Not all features are supported and tested!**                                                                    
                                             
### Minimum requirements:
Python >= **3.5**, GTK+ >= **3.16**, pygobject3, adwaita-icon-theme, python3-requests.                                  
#### Installation:                                                                             
```brew install python3 gtk+3 pygobject3 adwaita-icon-theme```                                                                  
```pip3 install requests```                                                                                                                                                                                          
#### Optional:                                                                                                          
```brew install wget imagemagick```                                                                                                                                                                                                                                                                                                      
```pip3 install pyobjc```                                                                                                
#### Launching:                                                                                                                                                                                                                     
To start the program, just download the archive, unpack and run it from the terminal with the command: ```./start.py``` 

### Building standalone application:                                                                                     
Install [PyInstaller](https://www.pyinstaller.org/) with the command from the terminal:                                                                    
```pip3 install pyinstaller```                                                                                          
and in th root dir run command:                                                                                         
```pyinstaller DemonEditor.spec``` 
                                                                                                                                              
Users of the **64-bit version of the OS** can download a ready-made package from [here](https://github.com/DYefremov/DemonEditor/raw/experimental-mac/dist/DemonEditor.app.zip).                                     
Just unpack and run. Recommended copy the bundle to the **Application** directory.                                      
Perhaps in the security settings it will be necessary to allow the launch of this application!

**Note. The package may not contain all the latest changes!**                                                            
                                                                       
                                                                                                                                                                                                                                            
