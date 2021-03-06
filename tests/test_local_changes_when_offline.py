# coding: utf-8
""""
Test if changes made to local file system when Drive is offline sync's back
later when Drive becomes online.
"""

import shutil

from nxdrive.constants import MAC, WINDOWS
from .common import FILE_CONTENT, UnitTestCase

if WINDOWS:
    from win32com.shell import shell, shellcon
else:
    import xattr

    if MAC:
        import Cocoa


class TestOfflineChangesSync(UnitTestCase):
    """
    All changes made in local PC while drive is offline should sync later when
    drive comes back online.
    offline can be one of: suspended, exited or disconnect
    See NXDRIVE-686
    """

    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        self.local = self.local_1
        self.remote = self.remote_document_client_1
        # Create a folder and a file in server side.
        # Wait for Drive to finish sync (download)
        self.folder1_remote = self.remote.make_folder("/", "Folder1")
        self.file1_remote = self.remote.make_file(
            self.folder1_remote, "File1.txt", FILE_CONTENT
        )
        self.wait_sync(wait_for_async=True)

        # Verify that the folder and file are sync'd (download) successfully
        assert self.local.exists("/Folder1/File1.txt")

    @staticmethod
    def copy_with_xattr(src, dst):
        """
        Custom copy tree method that also copies xattr along with
        shutil.copytree functionality.
        """

        if WINDOWS:
            # Make a copy of file1 using shell (to copy including xattr)
            shell.SHFileOperation(
                (0, shellcon.FO_COPY, src, dst, shellcon.FOF_NOCONFIRMATION, None, None)
            )
        elif MAC:
            fm = Cocoa.NSFileManager.defaultManager()
            fm.copyItemAtPath_toPath_error_(src, dst, None)
        else:
            shutil.copy2(src, dst)
            remote_id = xattr.getxattr(src, "user.ndrive")
            xattr.setxattr(dst, "user.ndrive", remote_id)

    def test_copy_paste_when_engine_suspended(self):
        """
        Copy paste and a rename operation together on same file while drive is
        offline should be detected and synced to server as soon as drive comes
        back online.
        """

        # Make drive offline (by suspend)
        self.engine_1.suspend()

        # Make a copy of the file (with xattr included)
        self.copy_with_xattr(
            self.local.abspath("/Folder1/File1.txt"),
            self.local.abspath("/Folder1/File1 - Copy.txt"),
        )

        # Rename the original file
        self.local.rename("/Folder1/File1.txt", "File1_renamed.txt")

        # Bring drive online (by resume)
        self.engine_1.resume()
        # Wait for Drive to sync the changes to server
        self.wait_sync(wait_for_async=True)

        # Verify there is no change in local pc
        assert self.local.exists("/Folder1/File1_renamed.txt")
        assert self.local.exists("/Folder1/File1 - Copy.txt")
        assert not self.local.exists("/Folder1/File1.txt")

        # Verify that local changes are uploaded to server successfully
        if self.remote.exists("/Folder1/File1 - Copy.txt"):
            # '/Folder1/File1 - Copy.txt' is uploaded to server.
            # So original file named should be changed as 'File_renamed.txt'
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1_renamed.txt"
        else:
            # Original file is renamed as 'File1 - Copy.txt'.
            # This is a bug only if Drive is online during copy + rename
            assert self.remote.exists("/Folder1/File1_renamed.txt")
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1 - Copy.txt"

    def test_copy_paste_normal(self):
        """
        Copy paste and a rename operation together on same file while drive is
        offline should be detected and synced to server as soon as drive comes
        back online.
        """

        # Make a copy of the file (with xattr included)
        self.copy_with_xattr(
            self.local.abspath("/Folder1/File1.txt"),
            self.local.abspath("/Folder1/File1 - Copy.txt"),
        )

        # Rename the original file
        self.local.rename("/Folder1/File1.txt", "File1_renamed.txt")

        # Wait for Drive to sync the changes to server
        self.wait_sync(wait_for_async=True)

        # Verify there is no change in local pc
        assert self.local.exists("/Folder1/File1_renamed.txt")
        assert self.local.exists("/Folder1/File1 - Copy.txt")
        assert not self.local.exists("/Folder1/File1.txt")

        # Verify that local changes are uploaded to server successfully
        if self.remote.exists("/Folder1/File1 - Copy.txt"):
            # '/Folder1/File1 - Copy.txt' is uploaded to server.
            # So original file named should be changed as 'File_renamed.txt'
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1_renamed.txt"
        else:
            # Original file is renamed as 'File1 - Copy.txt'.
            # This is a bug only if Drive is online during copy + rename
            assert self.remote.exists("/Folder1/File1_renamed.txt")
            remote_info = self.remote.get_info(self.file1_remote)
            assert remote_info.name == "File1 - Copy.txt"
