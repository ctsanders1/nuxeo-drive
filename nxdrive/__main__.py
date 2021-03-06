# coding: utf-8
"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import sys
from contextlib import suppress


def show_critical_error() -> None:
    """ Display a "friendly" dialog box on fatal error. """

    import traceback

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QTextEdit,
        QVBoxLayout,
    )

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    dialog = QDialog()
    dialog.setWindowTitle("Nuxeo Drive - Fatal error")
    dialog.resize(600, 400)
    layout = QVBoxLayout()
    css = "font-family: monospace; font-size: 12px;"
    details = ["Exception:"]

    with suppress(Exception):
        from nxdrive.utils import find_icon

        dialog.setWindowIcon(QIcon(find_icon("app_icon.svg")))

    # Display a little message to apologize
    text = f"""Ooops! Unfortunately, a fatal error occurred and Nuxeo Drive has stopped.
Please share the following informations with Nuxeo support : we’ll do our best to fix it!
"""
    info = QLabel(text)
    info.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    layout.addWidget(info)

    # Display the the exception
    label_exc = QLabel("Exception:")
    label_exc.setAlignment(Qt.AlignVCenter)
    exception = QTextEdit()
    exception.setStyleSheet(css)
    exception.setReadOnly(True)
    exc_formatted = traceback.format_exception(*sys.exc_info())
    details += exc_formatted
    exception.setText("".join(exc_formatted))
    layout.addWidget(label_exc)
    layout.addWidget(exception)

    # Display last lines from the memory log
    with suppress(Exception):
        from nxdrive.report import Report

        # Last 20th lines
        lines = Report.export_logs(-20)
        lines = b"\n".join(lines).decode(errors="replace")

        details += ["Logs before the crash:", lines]
        label_log = QLabel("Logs before the crash:")
        label_log.setAlignment(Qt.AlignVCenter)
        layout.addWidget(label_log)

        logs = QTextEdit()
        logs.setStyleSheet(css)
        logs.setReadOnly(True)
        logs.setLineWrapColumnOrWidth(4096)
        logs.setLineWrapMode(QTextEdit.FixedPixelWidth)
        logs.setText(lines)
        layout.addWidget(logs)

    # Buttons
    buttons = QDialogButtonBox()
    buttons.setStandardButtons(QDialogButtonBox.Ok)
    buttons.accepted.connect(dialog.close)
    layout.addWidget(buttons)

    def copy() -> None:
        """Copy details to the clipboard and change the text of the button. """
        copy_to_clipboard("\n".join(details))
        copy_paste.setText("Details copied!")

    # "Copy details" button
    with suppress(Exception):
        from nxdrive.utils import copy_to_clipboard

        copy_paste = buttons.addButton("Copy details", QDialogButtonBox.ActionRole)
        copy_paste.clicked.connect(copy)

    dialog.setLayout(layout)
    dialog.show()
    app.exec_()


def main() -> int:
    """ Entry point. """

    if sys.version_info < (3, 6):
        raise RuntimeError("Nuxeo Drive requires Python 3.6+")

    try:
        from nxdrive.commandline import CliHandler

        return CliHandler().handle(sys.argv)
    except:
        show_critical_error()
        return 1


sys.exit((main()))
