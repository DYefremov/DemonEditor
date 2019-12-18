# DemonEditor

## Experimental version for Mac OS.
This version is only for users those who wish to try running this program on **Mac OS**.                                
The functionality and performance of this version may be very different from the main version!                                                     
**Not all features are supported and tested!**                                                                    
                                             
### Minimum requirements:
Python >= **3.5**, GTK+ >= **3.16**, pygobject3, adwaita-icon-theme, python3-requests.                                  
**Installation:**                                                                             
```brew install python3 gtk+3 pygobject3 adwaita-icon-theme```                                                                  
```pip3 install requests```                                                                                                                                                                                          
**Optional:**                                                                                                                                                                                                                      
```pip3 install pyobjc```                                                                                                
**Launching:**                                                                                                                                                                                                                     
To start the program, just download the archive, unpack and run it from the terminal with the command: ```./start.py``` 

### Building standalone application:                                                                                     
Install [PyInstaller](https://www.pyinstaller.org/) with the command from the terminal:                                                                    
```pip3 install pyinstaller```                                                                                          
and in th root dir run command:                                                                                         
```pyinstaller DemonEditor.spec``` 
                                                                                                                                                                     
If you need to change the application icon, replace the icon.icns file with yours with the same name                    
or edit the DemonEditor.spec file.                                                                                                                                                                                                                                                                                                                                                                   
                                 
To run the program, copy the **dist/DemonEditor.app** bundle to the **Application** directory.                          
Perhaps in the security settings it will be necessary to allow the launch of this application!                           

Users of the **64-bit version of the OS** can download a ready-made package from [here](https://github.com/DYefremov/DemonEditor/raw/experimental-mac/dist/DemonEditor.app.zip). Just unpack and run.                                                                                           
**Note. The package may not contain all the latest changes!**                                                            
                                                                       
                                                                                                                                                                                                                                            
