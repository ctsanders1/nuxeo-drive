# coding: utf-8
import os
import sys
from contextlib import suppress
from ctypes import windll
from logging import getLogger
from typing import Any, Dict, Tuple

import win32api
import win32file
import winerror
import winreg
from win32com.client import Dispatch
from win32com.shell import shell, shellcon
from win32con import LOGPIXELSX

from .. import AbstractOSIntegration
from ...constants import APP_NAME
from ...options import Options
from ...utils import find_icon

__all__ = ("WindowsIntegration",)

log = getLogger(__name__)


class IconOverlay:

    # This UID must be the same as in tools/windows/setup-addons.iss
    _reg_clsid_ = "{6AB83667-881F-40CD-9BB2-9413575DB414}"
    _reg_progid_ = "NuxeoDrive.PythonOverlayHandler"
    _reg_desc_ = "Icon Overlay Handler for Nuxeo Drive"
    _public_methods_ = ["GetOverlayInfo", "GetPriority", "IsMemberOf"]
    _com_interfaces_ = [shell.IID_IShellIconOverlayIdentifier]

    def __init__(self) -> None:
        log.debug("Starting")
        self.icons = {
            "modified": find_icon("overlay\\win32\\ModifiedIcon.ico"),
            "normal": find_icon("overlay\\win32\\NormalIcon.ico"),
        }

    def GetOverlayInfo(self) -> Tuple[str, int, int]:
        log.debug("Return Normal icon")
        return self.icons["normal"], 0, shellcon.ISIOI_ICONFILE

    def GetPriority(self) -> int:
        log.debug("Return priority 50")
        return 50

    def IsMemberOf(self, fname: str, attributes) -> bool:
        log.debug("calling isMember on %r with attrs = %r", fname, attributes)
        if "nuxeo" in fname:
            if "finan" in fname:
                return winerror.S_FALSE

            log.debug("return ok for synced")
            return winerror.S_OK
        return winerror.S_FALSE


class WindowsIntegration(AbstractOSIntegration):

    __zoom_factor = None

    @property
    def zoom_factor(self) -> float:
        if not self.__zoom_factor:
            try:
                # Enable DPI detection
                windll.user32.SetProcessDPIAware()
                display = windll.user32.GetDC(None)
                dpi = windll.gdi32.GetDeviceCaps(display, LOGPIXELSX)
                windll.user32.ReleaseDC(None, display)
                # See https://technet.microsoft.com/en-us/library/dn528846.aspx
                self.__zoom_factor = dpi / 96.0
            except:
                log.debug("Cannot get zoom factor (using default 1.0)", exc_info=True)
                self.__zoom_factor = 1.0
        return self.__zoom_factor

    @staticmethod
    def is_partition_supported(folder: str) -> bool:
        if not folder.endswith("\\"):
            folder += "\\"
        if win32file.GetDriveType(folder) != win32file.DRIVE_FIXED:
            return False
        volume = win32file.GetVolumePathName(folder)
        volume_info = win32api.GetVolumeInformation(volume)
        return volume_info[4] == "NTFS"

    def get_system_configuration(self) -> Dict[str, Any]:
        """Retrieve the configuration stored in the registry, if any."""
        result = {}
        key = winreg.HKEY_CURRENT_USER
        subkey = "Software\\Nuxeo\\Drive"
        with suppress(OSError), winreg.OpenKey(key, subkey) as k:
            for idx in range(winreg.QueryInfoKey(k)[1]):
                name, value, _ = winreg.EnumValue(k, idx)
                result[name.replace("-", "_").lower()] = value
        return result

    def register_folder_link(self, folder_path: str, name: str = None) -> None:
        if not Options.is_frozen:
            return

        favorite = self._get_folder_link(name)
        if not os.path.isfile(favorite):
            self._create_shortcut(favorite, folder_path)

    def unregister_folder_link(self, name: str = None) -> None:
        if not Options.is_frozen:
            return

        with suppress(OSError):
            os.remove(self._get_folder_link(name))

    def register_startup(self) -> bool:
        if not Options.is_frozen:
            return False

        return self._registry_add(
            key=winreg.HKEY_CURRENT_USER,
            subkey="Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            name=APP_NAME,
            value=sys.executable,
        )

    def unregister_startup(self) -> bool:
        if not Options.is_frozen:
            return False

        return self._registry_del(
            key=winreg.HKEY_CURRENT_USER,
            subkey="Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            name=APP_NAME,
        )

    def addons_installed(self) -> bool:
        """Check if add-ons are installed or not."""
        return False

    def install_addons(self) -> bool:
        """Register the application in the "icon overlay" softwares list."""
        return False

    def _registry_add(
        self,
        key: str,
        subkey: str,
        name: str,
        value: str = None,
        cat: str = winreg.REG_SZ,
    ) -> bool:
        """Add one key into the registry."""
        try:
            with winreg.CreateKey(key, subkey) as k:
                winreg.SetValueEx(k, name, 0, cat, value)
        except OSError:
            log.exception(f"Registry: cannot add {key}\\{subkey}\\{name}")
            return False
        else:
            return True

    def _registry_del(self, key: str, subkey: str, name: str) -> bool:
        """Delete one key from the registry."""
        try:
            with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            log.exception(f"Registry: cannot delete {key}\\{subkey}\\{name}")
            return False
        else:
            return True

    def _create_shortcut(self, favorite: str, filepath: str) -> None:
        try:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(favorite)
            shortcut.Targetpath = filepath
            shortcut.WorkingDirectory = os.path.dirname(filepath)
            shortcut.IconLocation = filepath
            shortcut.save()
        except:
            log.exception("Could not create the favorite for %r", filepath)
        else:
            log.debug("Registered new favorite in Explorer for %r", filepath)

    def _get_folder_link(self, name: str = None) -> str:
        return os.path.join(
            os.path.expanduser("~"), "Links", (name or self._manager.app_name) + ".lnk"
        )
