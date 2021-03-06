# coding: utf-8
import os
import socket
import stat
import sys
from logging import getLogger
from typing import Dict, List, Optional

import xattr
from Foundation import NSBundle, NSDistributedNotificationCenter
from LaunchServices import (
    CFURLCreateWithString,
    LSSetDefaultHandlerForURLScheme,
    LSSharedFileListCopySnapshot,
    LSSharedFileListCreate,
    LSSharedFileListInsertItemURL,
    LSSharedFileListItemCopyDisplayName,
    LSSharedFileListItemRemove,
    kLSSharedFileListFavoriteItems,
    kLSSharedFileListItemBeforeFirst,
)
from nuxeo.compat import quote

from .. import AbstractOSIntegration
from ...constants import BUNDLE_IDENTIFIER
from ...engine.workers import Worker
from ...objects import NuxeoDocumentInfo
from ...utils import force_decode, if_frozen, normalized_path

__all__ = ("DarwinIntegration", "FinderSyncListener")

log = getLogger(__name__)


class DarwinIntegration(AbstractOSIntegration):

    NXDRIVE_SCHEME = "nxdrive"
    NDRIVE_AGENT_TEMPLATE = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0">'
        "<dict>"
        "<key>Label</key>"
        "<string>org.nuxeo.drive.agentlauncher</string>"
        "<key>RunAtLoad</key>"
        "<true/>"
        "<key>Program</key>"
        "<string>%s</string>"
        "</dict>"
        "</plist>"
    )

    def __init__(self, manager: "Manager") -> None:
        super().__init__(manager)
        self._init()

    @if_frozen
    def _init(self) -> None:
        log.debug("Telling plugInKit to use the FinderSync")
        os.system("pluginkit -e use -i {}.NuxeoFinderSync".format(BUNDLE_IDENTIFIER))

    @if_frozen
    def _cleanup(self) -> None:
        log.debug("Telling plugInKit to ignore the FinderSync")
        os.system("pluginkit -e ignore -i {}.NuxeoFinderSync".format(BUNDLE_IDENTIFIER))

    def _get_agent_file(self) -> str:
        return os.path.join(
            os.path.expanduser("~/Library/LaunchAgents"),
            "{}.plist".format(BUNDLE_IDENTIFIER),
        )

    @if_frozen
    def register_startup(self) -> bool:
        """
        Register the Nuxeo Drive.app as a user Launch Agent.
        http://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
        """
        agent = os.path.join(
            os.path.expanduser("~/Library/LaunchAgents"),
            "{}.plist".format(BUNDLE_IDENTIFIER),
        )
        if os.path.isfile(agent):
            return False

        agents_folder = os.path.dirname(agent)
        if not os.path.exists(agents_folder):
            log.debug("Making launch agent folder %r", agents_folder)
            os.makedirs(agents_folder)

        exe = os.path.realpath(sys.executable)
        log.debug("Registering %r for startup in %r", exe, agent)
        with open(agent, "w") as f:
            f.write(self.NDRIVE_AGENT_TEMPLATE % exe)
        return True

    @if_frozen
    def unregister_startup(self) -> bool:
        agent = self._get_agent_file()
        if os.path.isfile(agent):
            log.debug("Unregistering startup agent %r", agent)
            os.remove(agent)
            return True
        return False

    @if_frozen
    def register_protocol_handlers(self) -> None:
        """Register the URL scheme listener using PyObjC"""
        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if bundle_id == "org.python.python":
            log.debug(
                "Skipping URL scheme registration as this program "
                " was launched from the Python OSX app bundle"
            )
            return
        LSSetDefaultHandlerForURLScheme(self.NXDRIVE_SCHEME, bundle_id)
        log.debug(
            "Registered bundle %r for URL scheme %r", bundle_id, self.NXDRIVE_SCHEME
        )

    @if_frozen
    def unregister_protocol_handlers(self) -> None:
        # Don't unregister, should be removed when Bundle removed
        pass

    @staticmethod
    def is_partition_supported(folder: str) -> bool:
        if folder is None:
            return False
        result = False
        to_delete = not os.path.exists(folder)
        try:
            if to_delete:
                os.mkdir(folder)
            if not os.access(folder, os.W_OK):
                os.chmod(
                    folder,
                    stat.S_IXUSR
                    | stat.S_IRGRP
                    | stat.S_IXGRP
                    | stat.S_IRUSR
                    | stat.S_IWGRP
                    | stat.S_IWUSR,
                )
            key, value = "drive-test", b"drive-test"
            xattr.setxattr(folder, key, value)
            if xattr.getxattr(folder, key) == value:
                result = True
            xattr.removexattr(folder, key)
        finally:
            if to_delete:
                try:
                    os.rmdir(folder)
                except:
                    pass
        return result

    def _send_notification(self, name: str, content: Dict[str, str]) -> None:
        """
        Send a notification through the macOS notification center
        to the FinderSync app extension.

        :param name: name of the notification
        :param content: content to send
        """
        nc = NSDistributedNotificationCenter.defaultCenter()
        nc.postNotificationName_object_userInfo_(name, None, content)

    def _set_monitoring(self, operation: str, path: str) -> None:
        """
        Set the monitoring of a folder by the FinderSync.

        :param operation: 'watch' or 'unwatch'
        :param path: path to the folder
        """
        name = "{}.watchFolder".format(BUNDLE_IDENTIFIER)
        self._send_notification(name, {"operation": operation, "path": path})

    @if_frozen
    def watch_folder(self, folder: str) -> None:
        log.debug("FinderSync now watching %r", folder)
        self._set_monitoring("watch", folder)

    @if_frozen
    def unwatch_folder(self, folder: str) -> None:
        log.debug("FinderSync now ignoring %r", folder)
        self._set_monitoring("unwatch", folder)

    @if_frozen
    def send_sync_status(self, state: NuxeoDocumentInfo, path: str) -> None:
        """
        Send the sync status of a file to the FinderSync.

        :param state: current local state of the file
        :param path: full path of the file
        """
        try:
            path = force_decode(path)
            if not os.path.exists(path):
                return

            name = "{}.syncStatus".format(BUNDLE_IDENTIFIER)
            status = "unsynced"

            readonly = (os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP)) == 0
            if readonly:
                status = "locked"
            elif state:
                if state.error_count > 0:
                    status = "error"
                elif state.pair_state == "conflicted":
                    status = "conflicted"
                elif state.local_state == "synchronized":
                    status = "synced"
                elif state.pair_state == "unsynchronized":
                    status = "unsynced"
                elif state.processor != 0:
                    status = "syncing"

            log.trace("Sending status %r for file %r to FinderSync", status, path)
            self._send_notification(name, {"status": status, "path": path})
        except:
            log.exception("Error while trying to send status to FinderSync")

    @if_frozen
    def register_folder_link(self, folder_path: str, name: str = None) -> None:
        favorites = self._get_favorite_list() or []
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        folder_path = normalized_path(folder_path)
        name = os.path.basename(name) if name else self._manager.app_name

        if self._find_item_in_list(favorites, name):
            return

        url = CFURLCreateWithString(None, "file://{}".format(quote(folder_path)), None)
        if not url:
            log.warning("Could not generate valid favorite URL for: %r", folder_path)
            return

        # Register the folder as favorite if not already there
        item = LSSharedFileListInsertItemURL(
            favorites, kLSSharedFileListItemBeforeFirst, name, None, url, {}, []
        )
        if item:
            log.debug("Registered new favorite in Finder for: %r", folder_path)

    @if_frozen
    def unregister_folder_link(self, name: str = None) -> None:
        favorites = self._get_favorite_list()
        if not favorites:
            log.warning("Could not fetch the Finder favorite list.")
            return

        name = os.path.basename(name) if name else self._manager.app_name

        item = self._find_item_in_list(favorites, name)
        if not item:
            return

        LSSharedFileListItemRemove(favorites, item)

    @staticmethod
    def _get_favorite_list() -> List[str]:
        return LSSharedFileListCreate(None, kLSSharedFileListFavoriteItems, None)

    @staticmethod
    def _find_item_in_list(lst: List[str], name: str) -> Optional[str]:
        for item in LSSharedFileListCopySnapshot(lst, None)[0]:
            item_name = LSSharedFileListItemCopyDisplayName(item)
            if name == item_name:
                return item
        return None


class FinderSyncListener(Worker):
    def __init__(self, manager: "Manager") -> None:
        super().__init__()
        self._manager = manager
        self.host = "localhost"
        self.port = 50765
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.get_thread().started.connect(self.run)

    def _execute(self) -> None:
        self._sock.bind((self.host, self.port))
        self._sock.listen(5)
        log.debug("FinderSync listening on %s:%d", self.host, self.port)
        while True:
            self._interact()
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                pass
            else:
                client = SocketThread(conn, addr, self._manager)
                client.start()

    def quit(self) -> None:
        super().quit()
        self._sock.close()


class SocketThread(Worker):
    def __init__(
        self, sock: socket.SocketType, addr: socket.SocketType, manager: "Manager"
    ) -> None:
        super().__init__()
        self._manager = manager
        self._sock = sock
        self.addr = addr
        self.get_thread().started.connect(self.run)

    def _execute(self) -> None:
        content = ""
        while True:
            data = self._sock.recv(1024)
            if not data:
                break
            content += force_decode(data)
        log.trace("SocketThread for %s: received %s", self.addr, content)
        self._sock.close()
        self._manager.send_sync_status(content)
