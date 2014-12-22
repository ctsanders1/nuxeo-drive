import unittest
import os
import tempfile

from nxdrive.osi.command.commandline import CliHandler


class CommandLineTestCase(unittest.TestCase):
    def setUp(self):
        self.cmd = CliHandler()

    def create_ini(self, filename='config.ini', env='PROD'):
        with open(filename, 'w+') as inifile:
            inifile.writelines(['[DEFAULT]\n',
                            'env=' + env + '\n',
                            '[PROD]\n',
                            'log-level-console=PROD\n',
                            '[DEV]\n',
                            'log-level-console=DEV\n'])

    def clean_ini(self, filename='config.ini'):
        if os.path.exists(filename):
            os.remove(filename)

    def test_update__site_url(self):
        argv = ["ndrive",
                "--update-site-url", "DEBUG_TEST",
                "console"]
        options = self.cmd.parse_cli([])
        self.assertEqual(options.update_site_url,
                         "http://community.nuxeo.com/static/drive/",
                         "The official default")
        # Normal arg
        options = self.cmd.parse_cli(argv)
        self.assertEqual(options.update_site_url, "DEBUG_TEST",
                            "Should be debug test")

    def test_default_override(self):
        self.clean_ini()
        argv = ["ndrive",
                "--log-level-console", "DEBUG_TEST",
                "console"]
        # Default value
        options = self.cmd.parse_cli([])
        self.assertEqual(options.log_level_console, "INFO",
                            "The official default is INFO")
        # Normal arg
        options = self.cmd.parse_cli(argv)
        self.assertEqual(options.log_level_console, "DEBUG_TEST",
                            "Should be debug test")
        # config.ini override
        self.create_ini()
        options = self.cmd.parse_cli([])
        self.assertEqual(options.log_level_console, "PROD",
                            "The config.ini shoud link to PROD")
        # config.ini override, but arg specified
        options = self.cmd.parse_cli(argv)
        self.assertEqual(options.log_level_console, "DEBUG_TEST",
                            "Should be debug test")
        # other usage section
        self.create_ini(env='DEV')
        options = self.cmd.parse_cli([])
        self.assertEqual(options.log_level_console, "DEV",
                            "The config.ini shoud link to DEV")
        # user config.ini override
        self.cmd.default_home = tempfile.mkdtemp("config")
        conf = os.path.join(self.cmd.default_home, 'config.ini')
        self.create_ini(conf, "PROD")
        options = self.cmd.parse_cli([])
        self.assertEqual(options.log_level_console, "PROD",
                            "The config.ini shoud link to PROD")
        self.clean_ini(conf)
        options = self.cmd.parse_cli([])
        self.assertEqual(options.log_level_console, "DEV",
                            "The config.ini shoud link to DEV")
        self.clean_ini()
