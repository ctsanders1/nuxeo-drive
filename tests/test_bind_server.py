# coding: utf-8
import os
import tempfile
import unittest

import pytest

from nxdrive.exceptions import FolderAlreadyUsed
from nxdrive.manager import Manager
from nxdrive.options import Options
from .common import TEST_DEFAULT_DELAY, clean_dir


class BindServerTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.join(os.environ.get("WORKSPACE", ""), "tmp")
        self.addCleanup(clean_dir, self.tmpdir)
        if not os.path.isdir(self.tmpdir):
            os.makedirs(self.tmpdir)

        self.local_test_folder = tempfile.mkdtemp(
            "-nxdrive-temp-config", dir=self.tmpdir
        )
        self.nxdrive_conf_folder = os.path.join(
            self.local_test_folder, "nuxeo-drive-conf"
        )

    def tearDown(self):
        Manager._singleton = None

    @Options.mock()
    def test_bind_local_folder_on_config_folder(self):
        Options.delay = TEST_DEFAULT_DELAY
        Options.nxdrive_home = self.nxdrive_conf_folder
        self.manager = Manager()
        self.addCleanup(self.manager.unbind_all)
        self.addCleanup(self.manager.dispose_all)

        with pytest.raises(FolderAlreadyUsed):
            self.manager.bind_server(
                self.nxdrive_conf_folder,
                pytest.nuxeo_url,
                pytest.user,
                pytest.password,
                start_engine=False,
            )
