# coding: utf-8
import os
import time
from shutil import copyfile

import pytest
from unittest.mock import Mock, patch

from nxdrive.constants import WINDOWS
from nxdrive.engine.engine import Engine
from tests import DocRemote
from . import LocalTest
from .common import REMOTE_MODIFICATION_TIME_RESOLUTION, UnitTestCase


class TestRemoteMoveAndRename(UnitTestCase):
    def setUp(self):
        """
        Sets up the following remote hierarchy:

        Nuxeo Drive Test Workspace
           |-- Original Fil\xe9 1.odt
           |-- Original File 2.odt
           |-- Original Fold\xe9r 1
           |       |-- Sub-Folder 1.1
           |       |-- Sub-Folder 1.2
           |       |-- Original File 1.1.odt
           |-- Original Folder 2
           |       |-- Original File 3.odt
        """

        remote = self.remote_1

        self.workspace_id = "defaultSyncRootFolderItemFactory#default#" + self.workspace
        self.workspace_pair_local_path = "/" + self.workspace_title

        self.file_1_id = remote.make_file(
            self.workspace_id, "Original Fil\xe9 1.odt", content=b"Some Content 1"
        ).uid

        self.folder_1_id = remote.make_folder(
            self.workspace_id, "Original Fold\xe9r 1"
        ).uid
        self.folder_1_1_id = remote.make_folder(self.folder_1_id, "Sub-Folder 1.1").uid
        self.file_1_1_id = remote.make_file(
            self.folder_1_id, "Original File 1.1.odt", content=b"Some Content 1"
        ).uid

        self.folder_2_id = remote.make_folder(
            self.workspace_id, "Original Folder 2"
        ).uid
        self.file_3_id = remote.make_file(
            self.folder_2_id, "Original File 3.odt", content=b"Some Content 3"
        ).uid

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def get_state(self, remote):
        return self.engine_1.get_dao().get_normal_state_from_remote(remote)

    def test_remote_rename_file(self):
        remote = self.remote_1
        local = self.local_1

        file_1_docref = self.file_1_id.split("#")[-1]
        file_1_version = remote.get_info(file_1_docref).version

        # Rename /Original Fil\xe9 1.odt to /Renamed File 1.odt
        remote.rename(self.file_1_id, "Renamed File 1.odt")
        assert remote.get_fs_info(self.file_1_id).name == "Renamed File 1.odt"

        self.wait_sync(wait_for_async=True)

        version = remote.get_info(file_1_docref).version

        # Check remote file name
        assert remote.get_fs_info(self.file_1_id).name == "Renamed File 1.odt"
        assert file_1_version == version

        # Check local file name
        assert not local.exists("/Original Fil\xe9 1.odt")
        assert local.exists("/Renamed File 1.odt")

        # Check file state
        file_1_state = self.get_state(self.file_1_id)
        assert file_1_state.local_path == (
            self.workspace_pair_local_path + "/" + "Renamed File 1.odt"
        )
        assert file_1_state.local_name == "Renamed File 1.odt"

        # Rename 'Renamed File 1.odt' to 'Renamed Again File 1.odt'
        # and 'Original File 1.1.odt' to
        # 'Renamed File 1.1.odt' at the same time as they share
        # the same digest but do not live in the same folder
        # Wait for 1 second to make sure the file's last modification time
        # will be different from the pair state's last remote update time
        time.sleep(REMOTE_MODIFICATION_TIME_RESOLUTION)
        remote.rename(self.file_1_id, "Renamed Again File 1.odt")
        assert remote.get_fs_info(self.file_1_id).name == "Renamed Again File 1.odt"
        remote.rename(self.file_1_1_id, "Renamed File 1.1 \xe9.odt")
        assert remote.get_fs_info(self.file_1_1_id).name == "Renamed File 1.1 \xe9.odt"

        self.wait_sync(wait_for_async=True)

        info = remote.get_fs_info(self.file_1_id)
        assert info.name == "Renamed Again File 1.odt"
        assert remote.get_fs_info(self.file_1_1_id).name == "Renamed File 1.1 \xe9.odt"
        version = remote.get_info(file_1_docref).version
        assert file_1_version == version

        # Check local file names
        assert not local.exists("/Renamed File 1.odt")
        assert local.exists("/Renamed Again File 1.odt")
        assert not local.exists("/Original Fold\xe9r 1/Original File 1.1.odt")
        assert local.exists("/Original Fold\xe9r 1/Renamed File 1.1 \xe9.odt")

        # Check file states
        file_1_state = self.get_state(self.file_1_id)
        assert file_1_state.local_path == (
            self.workspace_pair_local_path + "/" + "Renamed Again File 1.odt"
        )
        assert file_1_state.local_name == "Renamed Again File 1.odt"
        file_1_1_state = self.get_state(self.file_1_1_id)
        assert file_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Fold\xe9r 1"
            "/Renamed File 1.1 \xe9.odt"
        )
        assert file_1_1_state.local_name == "Renamed File 1.1 \xe9.odt"

        # Test for encoding error regressions
        assert self.engine_1.get_dao()._get_recursive_condition(file_1_1_state)
        assert self.engine_1.get_dao()._get_recursive_remote_condition(file_1_1_state)

        # Check parents of renamed files to ensure it is an actual rename
        # that has been performed and not a move
        file_1_local_info = local.get_info("/Renamed Again File 1.odt")
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        assert file_1_parent_path == self.sync_root_folder_1

        file_1_1_local_info = local.get_info(
            "/Original Fold\xe9r 1/Renamed File 1.1 \xe9.odt"
        )
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        assert file_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Fold\xe9r 1"
        )

    def test_remote_rename_update_content_file(self):
        remote = self.remote_1
        local = self.local_1

        # Update the content of /'Original Fil\xe9 1.odt' and rename it
        # to /Renamed File 1.odt
        remote.update_content(
            self.file_1_id, b"Updated content", filename="Renamed File 1.odt"
        )
        assert remote.get_fs_info(self.file_1_id).name == "Renamed File 1.odt"
        assert remote.get_content(self.file_1_id) == b"Updated content"

        self.wait_sync(wait_for_async=True)

        # Check local file name
        assert not local.exists("/Original Fil\xe9 1.odt")
        assert local.exists("/Renamed File 1.odt")
        assert local.get_content("/Renamed File 1.odt") == b"Updated content"

    def test_remote_move_file(self):
        remote = self.remote_1
        local = self.local_1

        # Move /Original Fil\xe9 1.odt
        #   to /Original Fold\xe9r 1/Original Fil\xe9 1.odt
        remote.move(self.file_1_id, self.folder_1_id)
        assert remote.get_fs_info(self.file_1_id).name == "Original Fil\xe9 1.odt"
        assert remote.get_fs_info(self.file_1_id).parent_uid == self.folder_1_id

        self.wait_sync(wait_for_async=True)

        # Check remote file
        assert remote.get_fs_info(self.file_1_id).name == "Original Fil\xe9 1.odt"
        assert remote.get_fs_info(self.file_1_id).parent_uid == self.folder_1_id

        # Check local file
        assert not local.exists("/Original Fil\xe9 1.odt")
        assert local.exists("/Original Fold\xe9r 1/Original Fil\xe9 1.odt")
        file_1_local_info = local.get_info(
            "/Original Fold\xe9r 1/Original Fil\xe9 1.odt"
        )
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        assert file_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Fold\xe9r 1"
        )

        # Check file state
        file_1_state = self.get_state(self.file_1_id)
        assert file_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Fold\xe9r 1/"
            "Original Fil\xe9 1.odt"
        )
        assert file_1_state.local_name == "Original Fil\xe9 1.odt"

    def test_remote_move_and_rename_file(self):
        remote = self.remote_1
        local = self.local_1

        # Rename /'Original Fil\xe9 1.odt' to /Renamed File 1.odt
        remote.rename(self.file_1_id, "Renamed File 1 \xe9.odt")
        remote.move(self.file_1_id, self.folder_1_id)
        assert remote.get_fs_info(self.file_1_id).name == "Renamed File 1 \xe9.odt"
        assert remote.get_fs_info(self.file_1_id).parent_uid == self.folder_1_id

        self.wait_sync(wait_for_async=True)

        # Check remote file
        assert remote.get_fs_info(self.file_1_id).name == "Renamed File 1 \xe9.odt"
        assert remote.get_fs_info(self.file_1_id).parent_uid == self.folder_1_id

        # Check local file
        assert not local.exists("/Original Fil\xe9 1.odt")
        assert local.exists("/Original Fold\xe9r 1/Renamed File 1 \xe9.odt")
        file_1_local_info = local.get_info(
            "/Original Fold\xe9r 1/Renamed File 1 \xe9.odt"
        )
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        assert file_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Fold\xe9r 1"
        )

        # Check file state
        file_1_state = self.get_state(self.file_1_id)
        assert file_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Fold\xe9r 1"
            "/Renamed File 1 \xe9.odt"
        )
        assert file_1_state.local_name == "Renamed File 1 \xe9.odt"

    def test_remote_rename_folder(self):
        remote = self.remote_1
        local = self.local_1

        # Rename a non empty folder with some content
        remote.rename(self.folder_1_id, "Renamed Folder 1 \xe9")
        assert remote.get_fs_info(self.folder_1_id).name == "Renamed Folder 1 \xe9"

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The client folder has been renamed
        assert not local.exists("/Original Fold\xe9r 1")
        assert local.exists("/Renamed Folder 1 \xe9")

        # The content of the renamed folder is left unchanged
        # Check child name
        assert local.exists("/Renamed Folder 1 \xe9/Original File 1.1.odt")
        file_1_1_local_info = local.get_info(
            "/Renamed Folder 1 \xe9/Original File 1.1.odt"
        )
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        assert file_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Renamed Folder 1 \xe9"
        )

        # Check child state
        file_1_1_state = self.get_state(self.file_1_1_id)
        assert file_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Renamed Folder 1 \xe9"
            "/Original File 1.1.odt"
        )
        assert file_1_1_state.local_name == "Original File 1.1.odt"

        # Check child name
        assert local.exists("/Renamed Folder 1 \xe9/Sub-Folder 1.1")
        folder_1_1_local_info = local.get_info("/Renamed Folder 1 \xe9/Sub-Folder 1.1")
        folder_1_1_parent_path = os.path.dirname(folder_1_1_local_info.filepath)
        assert folder_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Renamed Folder 1 \xe9"
        )

        # Check child state
        folder_1_1_state = self.get_state(self.folder_1_1_id)
        assert folder_1_1_state
        assert folder_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Renamed Folder 1 \xe9" "/Sub-Folder 1.1"
        )
        assert folder_1_1_state.local_name == "Sub-Folder 1.1"

    def test_remote_rename_case_folder(self):
        remote = self.remote_1
        local = self.local_1

        assert local.exists("/Original Fold\xe9r 1")

        remote.rename(self.folder_1_id, "Original folder 1")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Original folder 1")

        remote.rename(self.folder_1_id, "Original Fold\xe9r 1")
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Original Fold\xe9r 1")

    def test_remote_rename_case_folder_stopped(self):
        remote = self.remote_1
        local = self.local_1
        self.engine_1.stop()
        assert local.exists("/Original Fold\xe9r 1")

        remote.rename(self.folder_1_id, "Original folder 1")
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Original folder 1")

        self.engine_1.stop()
        remote.rename(self.folder_1_id, "Original Fold\xe9r 1")
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Original Fold\xe9r 1")

    def test_remote_move_folder(self):
        remote = self.remote_1
        local = self.local_1

        # Move a non empty folder with some content
        remote.move(self.folder_1_id, self.folder_2_id)
        assert remote.get_fs_info(self.folder_1_id).name == "Original Fold\xe9r 1"
        assert remote.get_fs_info(self.folder_1_id).parent_uid == self.folder_2_id

        # Synchronize: only the folder move is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # Check remote folder
        assert remote.get_fs_info(self.folder_1_id).name == "Original Fold\xe9r 1"
        assert remote.get_fs_info(self.folder_1_id).parent_uid == self.folder_2_id

        # Check local folder
        assert not local.exists("/Original Fold\xe9r 1")
        assert local.exists("/Original Folder 2/Original Fold\xe9r 1")
        folder_1_local_info = local.get_info("/Original Folder 2/Original Fold\xe9r 1")
        folder_1_parent_path = os.path.dirname(folder_1_local_info.filepath)
        assert folder_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Folder 2"
        )

        # Check folder state
        folder_1_state = self.get_state(self.folder_1_id)
        assert folder_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Folder 2/"
            "Original Fold\xe9r 1"
        )
        assert folder_1_state.local_name == "Original Fold\xe9r 1"

        # The content of the renamed folder is left unchanged
        assert local.exists(
            "/Original Folder 2" "/Original Fold\xe9r 1" "/Original File 1.1.odt"
        )
        file_1_1_local_info = local.get_info(
            "/Original Folder 2/Original Fold\xe9r 1/Original File 1.1.odt"
        )
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        assert file_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Folder 2", "Original Fold\xe9r 1"
        )

        # Check child state
        file_1_1_state = self.get_state(self.file_1_1_id)
        assert file_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Folder 2"
            "/Original Fold\xe9r 1"
            "/Original File 1.1.odt"
        )
        assert file_1_1_state.local_name == "Original File 1.1.odt"

        # Check child name
        assert local.exists(
            "/Original Folder 2" "/Original Fold\xe9r 1" "/Sub-Folder 1.1"
        )
        folder_1_1_local_info = local.get_info(
            "/Original Folder 2/Original Fold\xe9r 1/Sub-Folder 1.1"
        )
        folder_1_1_parent_path = os.path.dirname(folder_1_1_local_info.filepath)
        assert folder_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Original Folder 2", "Original Fold\xe9r 1"
        )

        # Check child state
        folder_1_1_state = self.get_state(self.folder_1_1_id)
        assert folder_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Original Folder 2"
            "/Original Fold\xe9r 1"
            "/Sub-Folder 1.1"
        )
        assert folder_1_1_state.local_name == "Sub-Folder 1.1"

    def test_concurrent_remote_rename_folder(self):
        remote = self.remote_1
        local = self.local_1

        # Rename non empty folders concurrently
        remote.rename(self.folder_1_id, "Renamed Folder 1")
        assert remote.get_fs_info(self.folder_1_id).name == "Renamed Folder 1"
        remote.rename(self.folder_2_id, "Renamed Folder 2")
        assert remote.get_fs_info(self.folder_2_id).name == "Renamed Folder 2"

        # Synchronize: only the folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The content of the renamed folders is left unchanged
        # Check child name
        assert local.exists("/Renamed Folder 1/Original File 1.1.odt")
        file_1_1_local_info = local.get_info("/Renamed Folder 1/Original File 1.1.odt")
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        assert file_1_1_parent_path == os.path.join(
            self.sync_root_folder_1, "Renamed Folder 1"
        )

        # Check child state
        file_1_1_state = self.get_state(self.file_1_1_id)
        assert file_1_1_state.local_path == (
            self.workspace_pair_local_path + "/Renamed Folder 1"
            "/Original File 1.1.odt"
        )
        assert file_1_1_state.local_name == "Original File 1.1.odt"

        # Check child name
        assert local.exists("/Renamed Folder 2/Original File 3.odt")
        file_3_local_info = local.get_info("/Renamed Folder 2/Original File 3.odt")
        file_3_parent_path = os.path.dirname(file_3_local_info.filepath)
        assert file_3_parent_path == os.path.join(
            self.sync_root_folder_1, "Renamed Folder 2"
        )

        # Check child state
        file_3_state = self.get_state(self.file_3_id)
        assert file_3_state.local_path == (
            self.workspace_pair_local_path + "/Renamed Folder 2" "/Original File 3.odt"
        )
        assert file_3_state.local_name == "Original File 3.odt"

    def test_remote_rename_sync_root_folder(self):
        remote = self.remote_1
        local = LocalTest(self.local_nxdrive_folder_1)

        # Rename a sync root folder
        remote.rename(self.workspace_id, "Renamed Nuxeo Drive Test Workspace")
        assert (
            remote.get_fs_info(self.workspace_id).name
            == "Renamed Nuxeo Drive Test Workspace"
        )

        # Synchronize: only the sync root folder renaming is detected: all
        # the descendants are automatically realigned
        self.wait_sync(wait_for_async=True)

        # The client folder has been renamed
        assert not local.exists("/Nuxeo Drive Test Workspace")
        assert local.exists("/Renamed Nuxeo Drive Test Workspace")

        renamed_workspace_path = os.path.join(
            self.local_nxdrive_folder_1, "Renamed Nuxeo Drive Test Workspace"
        )

        # The content of the renamed folder is left unchanged
        # Check child name
        assert local.exists(
            "/Renamed Nuxeo Drive Test Workspace" "/Original Fil\xe9 1.odt"
        )
        file_1_local_info = local.get_info(
            "/Renamed Nuxeo Drive Test Workspace/Original Fil\xe9 1.odt"
        )
        file_1_parent_path = os.path.dirname(file_1_local_info.filepath)
        assert file_1_parent_path == renamed_workspace_path

        # Check child state
        file_1_state = self.get_state(self.file_1_id)
        assert (
            file_1_state.local_path == "/Renamed Nuxeo Drive Test Workspace"
            "/Original Fil\xe9 1.odt"
        )
        assert file_1_state.local_name == "Original Fil\xe9 1.odt"

        # Check child name
        assert local.exists(
            "/Renamed Nuxeo Drive Test Workspace" "/Original Fold\xe9r 1"
        )
        folder_1_local_info = local.get_info(
            "/Renamed Nuxeo Drive Test Workspace/Original Fold\xe9r 1"
        )
        folder_1_parent_path = os.path.dirname(folder_1_local_info.filepath)
        assert folder_1_parent_path == renamed_workspace_path

        # Check child state
        folder_1_state = self.get_state(self.folder_1_id)
        assert (
            folder_1_state.local_path == "/Renamed Nuxeo Drive Test Workspace"
            "/Original Fold\xe9r 1"
        )
        assert folder_1_state.local_name == "Original Fold\xe9r 1"

        # Check child name
        assert local.exists(
            "/Renamed Nuxeo Drive Test Workspace/"
            "Original Fold\xe9r 1"
            "/Sub-Folder 1.1"
        )
        folder_1_1_local_info = local.get_info(
            "/Renamed Nuxeo Drive Test Workspace/"
            "Original Fold\xe9r 1"
            "/Sub-Folder 1.1"
        )
        folder_1_1_parent_path = os.path.dirname(folder_1_1_local_info.filepath)
        assert folder_1_1_parent_path == os.path.join(
            renamed_workspace_path, "Original Fold\xe9r 1"
        )

        # Check child state
        folder_1_1_state = self.get_state(self.folder_1_1_id)
        assert (
            folder_1_1_state.local_path == "/Renamed Nuxeo Drive Test Workspace"
            "/Original Fold\xe9r 1/Sub-Folder 1.1"
        )
        assert folder_1_1_state.local_name == "Sub-Folder 1.1"

        # Check child name
        assert local.exists(
            "/Renamed Nuxeo Drive Test Workspace/"
            "Original Fold\xe9r 1"
            "/Original File 1.1.odt"
        )
        file_1_1_local_info = local.get_info(
            "/Renamed Nuxeo Drive Test Workspace/"
            "Original Fold\xe9r 1"
            "/Original File 1.1.odt"
        )
        file_1_1_parent_path = os.path.dirname(file_1_1_local_info.filepath)
        assert file_1_1_parent_path == os.path.join(
            renamed_workspace_path, "Original Fold\xe9r 1"
        )

        # Check child state
        file_1_1_state = self.get_state(self.file_1_1_id)
        assert (
            file_1_1_state.local_path == "/Renamed Nuxeo Drive Test Workspace"
            "/Original Fold\xe9r 1/Original File 1.1.odt"
        )
        assert file_1_1_state.local_name == "Original File 1.1.odt"

    def test_remote_move_to_non_sync_root(self):
        # Grant ReadWrite permission on Workspaces for test user
        workspaces_path = "/default-domain/workspaces"
        input_obj = "doc:" + workspaces_path
        pytest.root_remote.operations.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user=self.user_1,
            permission="ReadWrite",
            grant=True,
        )

        workspaces_info = pytest.root_remote.fetch(workspaces_path)
        workspaces = workspaces_info["uid"]

        # Get remote client with Workspaces as base folder and local client
        remote = DocRemote(
            pytest.nuxeo_url,
            self.user_1,
            "nxdrive-test-device-1",
            pytest.version,
            password=self.password_1,
            base_folder=workspaces,
            upload_tmp_dir=self.upload_tmp_dir,
        )
        local = self.local_1

        # Create a non synchronized folder
        unsync_folder = remote.make_folder("/", "Non synchronized folder")

        try:
            # Move 'Original Fold\xe9r 1' to Non synchronized folder
            remote.move(
                "/nuxeo-drive-test-workspace/Original Fold\xe9r 1",
                "/Non synchronized folder",
            )
            assert not remote.exists(
                "/nuxeo-drive-test-workspace" "/Original Fold\xe9r 1"
            )
            assert remote.exists("/Non synchronized folder" "/Original Fold\xe9r 1")

            # Synchronize: the folder move is detected as a deletion
            self.wait_sync(wait_for_async=True)

            # Check local folder
            assert not local.exists("/Original Fold\xe9r 1")

            # Check folder state
            assert self.get_state(self.folder_1_id) is None
        finally:
            # Clean the non synchronized folder
            remote.delete(unsync_folder, use_trash=False)


class TestSyncRemoteMoveAndRename(UnitTestCase):
    def setUp(self):
        local = self.local_1
        remote = self.remote_1

        # Create documents in the remote root workspace
        self.workspace_id = "defaultSyncRootFolderItemFactory#default#" + self.workspace
        self.workspace_pair_local_path = "/" + self.workspace_title
        self.folder_id = remote.make_folder(self.workspace_id, "Test folder").uid

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder")

    @pytest.mark.skipif(not WINDOWS, reason="Windows only.")
    def test_synchronize_remote_move_file_while_accessing(self):
        local = self.local_1
        remote = self.remote_1

        file_path = os.path.join(local.abspath("/Test folder"), "testFile.pdf")
        copyfile(self.location + "/resources/testFile.pdf", file_path)
        self.wait_sync()
        file_id = local.get_remote_id("/Test folder/testFile.pdf")
        assert file_id

        # Create a document by streaming a binary file ( open it as append )
        with open(file_path, "a"):
            # Rename remote folder then synchronize
            remote.move(file_id, self.workspace_id)
            self.wait_sync(wait_for_async=True)
            assert local.exists("/Test folder/testFile.pdf")
            assert not local.exists("/testFile.pdf")

        # The source file is accessed by another processor, but no error
        assert not self.engine_1.get_dao().get_errors()

        self.wait_sync(wait_for_async=True)
        assert local.exists("/testFile.pdf")
        assert not local.exists("/Test folder/testFile.pdf")

    def test_synchronize_remote_move_while_download_file(self):
        local = self.local_1
        remote = self.remote_1

        # Create documents in the remote root workspace
        new_folder_id = remote.make_folder(self.folder_id, "New folder").uid
        self.wait_sync(wait_for_async=True)

        def _suspend_check(*_):
            """ Add delay when upload and download. """
            if self.engine_1.file_id and not self.engine_1.has_rename:
                # Rename remote file while downloading
                remote.move(self.engine_1.file_id, new_folder_id)
                self.engine_1.has_rename = True
            time.sleep(3)
            Engine.suspend_client(self.engine_1)

        self.engine_1.has_rename = False
        self.engine_1.file_id = None

        try:
            self.engine_1.remote.check_suspended = _suspend_check
            with open(self.location + "/resources/testFile.pdf", "rb") as f:
                content = f.read()
            self.engine_1.file_id = remote.make_file(
                self.folder_id, "testFile.pdf", content=content
            ).uid

            # Rename remote folder then synchronize
            self.wait_sync(wait_for_async=True)
            assert not local.exists("/Test folder/testFile.pdf")
            assert local.exists("/Test folder/New folder/testFile.pdf")
        finally:
            self.engine_1.remote.check_suspended = Engine.suspend_client

    @pytest.mark.skipif(not WINDOWS, reason="Windows only.")
    def test_synchronize_remote_rename_file_while_accessing(self):
        local = self.local_1
        remote = self.remote_1

        file_path = os.path.join(local.abspath("/Test folder"), "testFile.pdf")
        copyfile(self.location + "/resources/testFile.pdf", file_path)
        self.wait_sync()
        file_id = local.get_remote_id("/Test folder/testFile.pdf")
        assert file_id

        # Create a document by streaming a binary file
        with open(file_path, "a"):
            # Rename remote folder then synchronize
            remote.rename(file_id, "testFile2.pdf")
            self.wait_sync(wait_for_async=True)
            assert local.exists("/Test folder/testFile.pdf")
            assert not local.exists("/Test folder/testFile2.pdf")

        # The source file is accessed by another processor, but no errors
        assert not self.engine_1.get_dao().get_errors()

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test folder/testFile2.pdf")
        assert not local.exists("/Test folder/testFile.pdf")

    def test_synchronize_remote_rename_while_download_file(self):
        local = self.local_1
        remote = self.remote_document_client_1

        def check_suspended(*_):
            """ Add delay when upload and download. """
            if not self.engine_1.has_rename:
                # Rename remote file while downloading
                self.remote_1.rename(self.folder_id, "Test folder renamed")
                self.engine_1.has_rename = True
            time.sleep(3)
            Engine.suspend_client(self.engine_1)

        self.engine_1.has_rename = False

        with patch.object(
            self.engine_1.remote, "check_suspended", new_callable=check_suspended
        ):
            with open(self.location + "/resources/testFile.pdf", "rb") as f:
                remote.make_file("/Test folder", "testFile.pdf", content=f.read())

            # Rename remote folder then synchronize
            self.wait_sync(wait_for_async=True)
            assert not local.exists("/Test folder")
            assert local.exists("/Test folder renamed")
            assert local.exists("/Test folder renamed/testFile.pdf")

    def test_synchronize_remote_rename_while_upload(self):
        if WINDOWS:
            self._remote_rename_while_upload()
        else:
            func = "nxdrive.client.remote_client.os.fstatvfs"
            with patch(func) as mock_os:
                mock_os.return_value = Mock()
                mock_os.return_value.f_bsize = 4096
                self._remote_rename_while_upload()

    def _remote_rename_while_upload(self):
        local = self.local_1
        remote = self.remote_1

        def check_suspended(*_):
            """ Add delay when upload and download. """
            if not local.exists("/Test folder renamed"):
                time.sleep(1)
            Engine.suspend_client(self.engine_1)

        with patch.object(self.engine_1.remote, "check_suspended", new=check_suspended):
            # Create a document by streaming a binary file
            file_path = os.path.join(local.abspath("/Test folder"), "testFile.pdf")
            copyfile(self.location + "/resources/testFile.pdf", file_path)
            file_path = os.path.join(local.abspath("/Test folder"), "testFile2.pdf")
            copyfile(self.location + "/resources/testFile.pdf", file_path)

            # Rename remote folder then synchronize
            remote.rename(self.folder_id, "Test folder renamed")

            self.wait_sync(wait_for_async=True)
            assert not local.exists("/Test folder")
            assert local.exists("/Test folder renamed")
            assert local.exists("/Test folder renamed/testFile.pdf")
            assert local.exists("/Test folder renamed/testFile2.pdf")


class TestRemoteMove(UnitTestCase):
    def test_remote_create_and_move(self):
        """
        NXDRIVE-880: folder created and moved on the server does
        not sync properly.
        """

        local = self.local_1
        remote = self.remote_document_client_1
        engine = self.engine_1

        # Create a folder with some stuff inside, and sync
        a1 = remote.make_folder("/", "a1")
        for idx in range(5):
            fname = "file-{}.txt".format(idx)
            remote.make_file(a1, fname, content=b"Content of " + fname.encode("utf-8"))
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Create another folder and move a1 inside it, and sync
        a3 = remote.make_folder("/", "a3")
        remote.move(a1, a3)
        self.wait_sync(wait_for_async=True)

        # Checks
        assert not local.exists("/a1")
        assert len(local.get_children_info("/a3/a1")) == 5


class TestRemoteFiles(UnitTestCase):
    def test_remote_create_files_upper_lower_cases(self):
        """
        Check that remote (lower|upper)case renaming is taken
        into account locally.
        """
        remote = self.remote_document_client_1
        local = self.local_1
        engine = self.engine_1

        # Create an innocent file, lower case
        filename = "abc.txt"
        doc = remote.make_file("/", filename, content=b"case")
        engine.start()
        self.wait_sync(wait_for_async=True)

        # Check
        assert remote.exists("/" + filename)
        assert local.exists("/" + filename)

        # Remotely rename to upper case
        filename_upper = filename.upper()
        remote.update_content(doc, b"CASE", filename=filename_upper)
        self.wait_sync(wait_for_async=True)

        # Check - server
        children = remote.get_children_info(self.workspace_1)
        assert len(children) == 1
        assert children[0].filename == filename_upper

        # Check - client
        children = local.get_children_info("/")
        assert len(children) == 1
        assert children[0].name == filename_upper
