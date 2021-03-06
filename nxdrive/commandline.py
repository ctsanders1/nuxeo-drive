# coding: utf-8
""" Utilities to operate Nuxeo Drive from the command line. """

import faulthandler
import os
import sys
import traceback
from argparse import ArgumentParser, Namespace
from configparser import DEFAULTSECT, ConfigParser
from datetime import datetime
from logging import getLogger
from typing import List, Union

from . import __version__
from .logging_config import configure
from .options import Options
from .utils import force_encode, get_default_nuxeo_drive_folder, normalized_path

try:
    import ipdb as pdb
except ImportError:
    import pdb

try:
    from PyQt5.QtNetwork import QSslSocket
except ImportError:
    QSslSocket = None

__all__ = ("CliHandler",)

log = getLogger(__name__)

USAGE = """ndrive [command]

If no command is provided, the graphical application is
started along with a synchronization process.

Possible commands:
- console
- bind-server
- unbind-server
- bind-root
- unbind-root
- clean_folder
- access-online
- copy-share-link
- edit-metadata

To get options for a specific command:

  ndrive command --help

"""


class CliHandler:
    """ Set default arguments. """

    def get_version(self) -> str:
        return __version__

    def make_cli_parser(self, add_subparsers: bool = True) -> ArgumentParser:
        """
        Parse commandline arguments using a git-like subcommands scheme.
        """

        common_parser = ArgumentParser(add_help=False)
        common_parser.add_argument(
            "--nxdrive-home",
            default=Options.nxdrive_home,
            help="Folder to store the Nuxeo Drive configuration",
        )

        common_parser.add_argument(
            "--log-level-file",
            default=Options.log_level_file,
            choices=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR"),
            help="Minimum log level for the file log",
        )

        common_parser.add_argument(
            "--log-level-console",
            default=Options.log_level_console,
            choices=("TRACE", "DEBUG", "INFO", "WARNING", "ERROR"),
            help="Minimum log level for the console log",
        )

        common_parser.add_argument("--log-filename", help="File used to store the logs")

        common_parser.add_argument(
            "--locale", default=Options.locale, help="Select the default language"
        )

        common_parser.add_argument("--force-locale", help="Force the language")

        common_parser.add_argument(
            "--update-site-url",
            default=Options.update_site_url,
            help="Website for client auto-update",
        )

        common_parser.add_argument(
            "--beta-update-site-url",
            default=Options.beta_update_site_url,
            help="Website for client beta auto-update",
        )

        common_parser.add_argument(
            "--debug",
            default=Options.debug,
            action="store_true",
            help="Fire a debugger (ipdb or pdb) one uncaught error",
        )

        common_parser.add_argument(
            "--nofscheck",
            default=Options.nofscheck,
            action="store_true",
            help="Fire a debugger (ipdb or pdb) one uncaught error",
        )

        common_parser.add_argument("--proxy-server", help="Define proxy server")

        common_parser.add_argument(
            "--consider-ssl-errors",
            default=Options.consider_ssl_errors,
            action="store_true",
            help="Do not ignore SSL errors in Qt network manager requests",
        )

        common_parser.add_argument(
            "--debug-pydev",
            default=Options.debug_pydev,
            action="store_true",
            help="Allow debugging with a PyDev server",
        )

        common_parser.add_argument(
            "--delay",
            default=Options.delay,
            type=int,
            help="Delay in seconds for remote polling",
        )

        common_parser.add_argument(
            "--max-sync-step",
            default=Options.max_sync_step,
            type=int,
            help="Number of consecutive sync operations to perform "
            "without refreshing the internal state DB",
        )

        common_parser.add_argument(
            "--handshake-timeout",
            default=Options.handshake_timeout,
            type=int,
            help="HTTP request timeout in seconds for the handshake",
        )

        common_parser.add_argument(
            "--timeout",
            default=Options.timeout,
            type=int,
            help="HTTP request timeout in seconds for sync Automation call",
        )

        common_parser.add_argument(
            "--update-check-delay",
            default=Options.update_check_delay,
            type=int,
            help="Delay in seconds between checks for application update",
        )

        common_parser.add_argument(
            "--max-errors",
            default=Options.max_errors,
            type=int,
            help="Maximum number of tries before giving up synchronization of "
            "a file in error",
        )

        common_parser.add_argument(
            "-v",
            "--version",
            action="version",
            version=self.get_version(),
            help="Print the current version of the Nuxeo Drive client",
        )

        parser = ArgumentParser(
            parents=[common_parser],
            description="Command line interface for Nuxeo Drive operations.",
            usage=USAGE,
        )

        if not add_subparsers:
            return parser

        subparsers = parser.add_subparsers(title="Commands")

        # Link to a remote Nuxeo server
        bind_server_parser = subparsers.add_parser(
            "bind-server",
            help="Attach a local folder to a Nuxeo server.",
            parents=[common_parser],
        )
        bind_server_parser.set_defaults(command="bind_server")
        bind_server_parser.add_argument(
            "--password", help="Password for the Nuxeo account"
        )
        bind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server.",
            type=str,
            default=get_default_nuxeo_drive_folder(),
        )
        bind_server_parser.add_argument(
            "username", help="User account to connect to Nuxeo"
        )
        bind_server_parser.add_argument("nuxeo_url", help="URL of the Nuxeo server.")
        bind_server_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Unlink from a remote Nuxeo server
        unbind_server_parser = subparsers.add_parser(
            "unbind-server",
            help="Detach from a remote Nuxeo server.",
            parents=[common_parser],
        )
        unbind_server_parser.set_defaults(command="unbind_server")
        unbind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that hosts the list of synchronized "
            "workspaces with a remote Nuxeo server.",
            type=str,
            default=get_default_nuxeo_drive_folder(),
        )

        # Bind root folders
        bind_root_parser = subparsers.add_parser(
            "bind-root",
            help="Register a folder as a synchronization root.",
            parents=[common_parser],
        )
        bind_root_parser.set_defaults(command="bind_root")
        bind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.",
        )
        bind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server. Must be bound with the "
            '"bind-server" command.',
            type=str,
            default=get_default_nuxeo_drive_folder(),
        )
        bind_root_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Unlink from a remote Nuxeo root
        unbind_root_parser = subparsers.add_parser(
            "unbind-root",
            help="Unregister a folder as a synchronization root.",
            parents=[common_parser],
        )
        unbind_root_parser.set_defaults(command="unbind_root")

        unbind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.",
        )
        unbind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server. Must be bound with the "
            '"bind-server" command.',
            type=str,
            default=get_default_nuxeo_drive_folder(),
        )
        unbind_root_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Uninstall
        uninstall_parser = subparsers.add_parser(
            "uninstall", help="Remove app data", parents=[common_parser]
        )
        uninstall_parser.set_defaults(command="uninstall")

        # Run in console mode
        console_parser = subparsers.add_parser(
            "console", help="Start in GUI-less mode.", parents=[common_parser]
        )
        console_parser.set_defaults(command="console")

        # Clean the folder
        clean_parser = subparsers.add_parser(
            "clean_folder",
            help="Remove all ndrive attributes from this folder and children.",
            parents=[common_parser],
        )
        clean_parser.add_argument("--local-folder", help="Local folder to clean.")
        clean_parser.set_defaults(command="clean_folder")

        # Context menu: Access online
        ctx_item1 = subparsers.add_parser(
            "access-online",
            help="Open the document in the browser.",
            parents=[common_parser],
        )
        ctx_item1.set_defaults(command="ctx_access_online")
        ctx_item1.add_argument("--file", default="", help="File path.")

        # Context menu: Copy the share-link
        ctx_item2 = subparsers.add_parser(
            "copy-share-link",
            help="Copy the document's share-link to the clipboard.",
            parents=[common_parser],
        )
        ctx_item2.set_defaults(command="ctx_copy_share_link")
        ctx_item2.add_argument("--file", default="", help="File path.")

        # Context menu: Edit metadata
        ctx_item3 = subparsers.add_parser(
            "edit-metadata",
            help="Display the metadata window for a given file.",
            parents=[common_parser],
        )
        ctx_item3.set_defaults(command="ctx_edit_metadata")
        ctx_item3.add_argument("--file", default="", help="File path.")

        return parser

    """Command Line Interface handler: parse options and execute operation"""

    def parse_cli(self, argv: List[str]) -> Namespace:
        """Parse the command line argument using argparse and protocol URL"""
        # Filter psn argument provided by OSX .app service launcher
        # https://developer.apple.com/library/mac/documentation/Carbon/Reference/LaunchServicesReference/LaunchServicesReference.pdf
        # When run from the .app bundle generated with py2app with
        # argv_emulation=True this is already filtered out but we keep it
        # for running CLI from the source folder in development.
        argv = [a for a in argv if not a.startswith("-psn_")]

        # Preprocess the args to detect protocol handler calls and be more
        # tolerant to missing subcommand
        has_command = False

        filtered_args = []
        for arg in argv[1:]:
            if arg.startswith("nxdrive://"):
                Options.set("protocol_url", arg, setter="cli")
                continue
            if not arg.startswith("-"):
                has_command = True
            filtered_args.append(arg)

        parser = self.make_cli_parser(add_subparsers=has_command)
        # Change default value according to config.ini
        self.load_config(parser)
        options = parser.parse_args(filtered_args)
        if options.debug:
            # Automatically check all operations done with the Python client
            import nuxeo.constants

            nuxeo.constants.CHECK_PARAMS = True

            # Install Post-Mortem debugger hook

            def info(etype, value, tb):
                traceback.print_exception(etype, value, tb)
                pdb.pm()

            sys.excepthook = info

        return options

    def load_config(self, parser: ArgumentParser) -> None:
        config_name = "config.ini"
        config = ConfigParser()
        configs = []
        path = os.path.join(os.path.dirname(sys.executable), config_name)
        if os.path.exists(path):
            configs.append(path)
        if os.path.exists(config_name):
            configs.append(config_name)
        user_ini = os.path.expanduser(os.path.join(Options.nxdrive_home, config_name))
        if os.path.exists(user_ini):
            configs.append(user_ini)
        if configs:
            config.read(configs)

        from .osi import AbstractOSIntegration

        args = AbstractOSIntegration.get(None).get_system_configuration()
        if config.has_option(DEFAULTSECT, "env"):
            env = config.get(DEFAULTSECT, "env")
            for item in config.items(env):
                if item[0] == "env":
                    continue

                value = item[1]
                if value == "":
                    continue

                if "\n" in value:
                    if "=" in value:
                        log.error(
                            "Malformatted parameter in config.ini: %r => %r",
                            item[0],
                            value,
                        )
                        value = value.split()[0].split("=")[0].strip()
                    else:
                        # Treat multiline option as a set
                        value = tuple(sorted(item[1].split()))
                args[item[0].replace("-", "_")] = value
        if args:
            Options.update(args, setter="local")
            parser.set_defaults(**args)

    def _configure_logger(self, command: str, options: Namespace) -> None:
        """ Configure the logging framework from the provided options. """

        # Ensure the log folder exists
        folder_log = os.path.expanduser(os.path.join(options.nxdrive_home, "logs"))
        if not os.path.exists(folder_log):
            os.makedirs(folder_log)

        filename = options.log_filename
        if filename is None:
            filename = os.path.join(options.nxdrive_home, "logs", "nxdrive.log")

        configure(
            log_filename=filename,
            file_level=options.log_level_file,
            console_level=options.log_level_console,
            command_name=command,
        )

    def uninstall(self) -> None:
        self.manager.osi.uninstall()

    def handle(self, argv: List[str]) -> int:
        """ Parse options, setup logs and manager and dispatch execution. """
        options = self.parse_cli(argv)

        if getattr(options, "local_folder", ""):
            options.local_folder = normalized_path(options.local_folder)

        # 'launch' is the default command if None is provided
        command = getattr(options, "command", "launch")

        if command != "uninstall":
            # Configure the logging framework, except for the tests as they
            # configure their own.
            # Don't need uninstall logs either for now.
            self._configure_logger(command, options)

        log.debug("Command line: argv=%r, options=%r", argv, options)
        if QSslSocket:
            has_ssl_support = QSslSocket.supportsSsl()
            log.info("SSL support: %r", has_ssl_support)
            if not has_ssl_support:
                options.consider_ssl_errors = False

        # Update default options
        # We cannot use fail_on_error=True because options is a namespace
        # and contains a lot of inexistant Options values.
        Options.update(options, setter="cli", fail_on_error=False)

        if command != "uninstall":
            # Install utility to help debugging segmentation faults
            self._install_faulthandler()

        # Initialize a manager for this process
        self.manager = self.get_manager()

        # Find the command to execute based on the
        handler = getattr(self, command, None)
        if not handler:
            raise NotImplementedError(
                "No handler implemented for command {}".format(command)
            )

        return handler(options)

    def get_manager(self) -> "Manager":
        from .manager import Manager

        return Manager()

    def _get_application(
        self, console: bool = False
    ) -> Union["Application", "ConsoleApplication"]:
        if console:
            from .console import ConsoleApplication as Application
        else:
            from .gui.application import Application
            from .gui.systray import SystrayWindow
            from PyQt5.QtQml import qmlRegisterType

            qmlRegisterType(SystrayWindow, "SystrayWindow", 1, 0, "SystrayWindow")
        return Application(self.manager)

    def launch(self, options: Namespace = None, console: bool = False) -> int:
        """Launch the Qt app in the main thread and sync in another thread."""
        from .utils import PidLockFile

        lock = PidLockFile(self.manager.nxdrive_home, "qt")
        if lock.lock():
            if Options.protocol_url:
                payload = force_encode(Options.protocol_url)
                self._send_to_running_instance(payload)
            else:
                log.warning("%s is already running: exiting.", self.manager.app_name)
            return 0

        app = self._get_application(console=console)
        exit_code = app.exec_()
        lock.unlock()
        log.debug("%s exited with code %d", self.manager.app_name, exit_code)
        return exit_code

    def _send_to_running_instance(self, payload: bytes) -> bool:
        from PyQt5.QtCore import QByteArray
        from PyQt5.QtNetwork import QLocalSocket

        log.debug(
            f"Opening local socket to send to the running instance (payload={payload})"
        )
        client = QLocalSocket()
        client.connectToServer("com.nuxeo.drive.protocol")

        if not client.waitForConnected():
            log.error(f"Unable to open client socket: {client.errorString()}")
            return 0

        client.write(QByteArray(payload))
        client.waitForBytesWritten()
        client.disconnectFromServer()
        client.waitForDisconnected()
        del client
        log.debug("Successfully closed client socket")

    def clean_folder(self, options: Namespace) -> int:
        from .client.local_client import LocalClient

        if not options.local_folder:
            print("A folder must be specified")
            return 1

        client = LocalClient(options.local_folder)
        client.clean_xattr_root()
        return 0

    def console(self, options: Namespace) -> int:
        if options.debug_pydev:
            from pydev import pydevd

            pydevd.settrace()
        return self.launch(options=options, console=True)

    def ctx_access_online(self, options: Namespace) -> None:
        """ Event fired by "Access online" menu entry. """
        file_path = normalized_path(options.file)
        self.manager.ctx_access_online(file_path)

    def ctx_copy_share_link(self, options: Namespace) -> None:
        """ Event fired by "Copy share-link" menu entry. """
        file_path = normalized_path(options.file)
        self.manager.ctx_copy_share_link(file_path)

    def ctx_edit_metadata(self, options: Namespace) -> None:
        """ Event fired by "Edit metadata" menu entry. """
        file_path = normalized_path(options.file)
        self.manager.ctx_edit_metadata(file_path)

    def download_edit(self, options: Namespace) -> int:
        self.launch(options=options)
        return 0

    def bind_server(self, options: Namespace) -> int:
        password, check_credentials = None, True
        if not options.password:
            check_credentials = False
        else:
            password = options.password
        if not options.local_folder:
            options.local_folder = get_default_nuxeo_drive_folder()

        self.manager.bind_server(
            options.local_folder,
            options.nuxeo_url,
            options.username,
            password,
            start_engine=False,
            check_credentials=check_credentials,
        )
        return 0

    def unbind_server(self, options: Namespace) -> int:
        for uid, engine in self.manager.get_engines().items():
            if engine.local_folder == options.local_folder:
                self.manager.unbind_engine(uid)
                return 0
        log.error("No engine registered for local folder %r", options.local_folder)
        return 1

    def bind_root(self, options: Namespace) -> int:
        for engine in self.manager.get_engines().values():
            log.trace("Comparing: %r to %r", engine.local_folder, options.local_folder)
            if engine.local_folder == options.local_folder:
                engine.remote.register_as_root(options.remote_root)
                return 0
        log.error("No engine registered for local folder %r", options.local_folder)
        return 1

    def unbind_root(self, options: Namespace) -> int:
        for engine in self.manager.get_engines().values():
            if engine.local_folder == options.local_folder:
                engine.remote.unregister_as_root(options.remote_root)
                return 0
        log.error("No engine registered for local folder %r", options.local_folder)
        return 1

    @staticmethod
    def _install_faulthandler() -> None:
        """ Utility to help debug segfaults. """
        segfault_filename = os.path.expanduser(
            os.path.join(Options.nxdrive_home, "logs", "segfault.log")
        )
        log.debug("Enabling faulthandler in %r", segfault_filename)

        segfault_file = open(segfault_filename, "a")
        try:
            segfault_file.write("\n\n\n>>> {}\n".format(datetime.now()))
            faulthandler.enable(file=segfault_file)
        finally:
            segfault_file.close()
