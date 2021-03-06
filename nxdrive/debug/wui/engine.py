# coding: utf-8
import time
from logging import getLogger

from PyQt5.QtCore import pyqtSlot

from ...gui.dialog import QMLDriveApi
from ...logging_config import MAX_LOG_DISPLAYED, get_handler

__all__ = ()

log = getLogger(__name__)


class DebugDriveApi(QMLDriveApi):
    def __init__(self, application, dlg):
        super(DebugDriveApi, self).__init__(application, dlg)

    def _get_full_queue(self, queue, dao=None):
        result = []
        while queue:
            result.append(self._export_state(dao.get_state_from_id(queue.pop().id)))
        return result

    def _export_engine(self, engine):
        result = super(DebugDriveApi, self)._export_engine(engine)
        result["queue"]["metrics"] = engine.get_queue_manager().get_metrics()
        result["queue"][
            "local_folder_enable"
        ] = engine.get_queue_manager()._local_folder_enable
        result["queue"][
            "local_file_enable"
        ] = engine.get_queue_manager()._local_file_enable
        result["queue"][
            "remote_folder_enable"
        ] = engine.get_queue_manager()._remote_folder_enable
        result["queue"][
            "remote_file_enable"
        ] = engine.get_queue_manager()._remote_file_enable
        result["queue"]["remote_file"] = self._get_full_queue(
            engine.get_queue_manager().get_remote_file_queue(), engine.get_dao()
        )
        result["queue"]["remote_folder"] = self._get_full_queue(
            engine.get_queue_manager().get_remote_folder_queue(), engine.get_dao()
        )
        result["queue"]["local_folder"] = self._get_full_queue(
            engine.get_queue_manager().get_local_folder_queue(), engine.get_dao()
        )
        result["queue"]["local_file"] = self._get_full_queue(
            engine.get_queue_manager().get_local_file_queue(), engine.get_dao()
        )
        result["local_watcher"] = self._export_worker(engine._local_watcher)
        result["remote_watcher"] = self._export_worker(engine._remote_watcher)
        try:
            result["logs"] = self._get_logs()
        except:
            # Dont fail on logs extraction
            result["logs"] = []
        return result

    def _export_log_record(self, record):
        rec = dict()
        rec["severity"] = record.levelname
        rec["message"] = record.getMessage()
        rec["thread"] = record.thread
        rec["name"] = record.name
        rec["funcName"] = record.funcName
        rec["time"] = time.strftime("%H:%M:%S,", time.localtime(record.created)) + str(
            round(record.msecs)
        )
        return rec

    def _get_logs(self, limit=MAX_LOG_DISPLAYED):
        logs = []
        handler = get_handler(getLogger(), "memory")
        log_buffer = handler.get_buffer(limit)
        for record in log_buffer:
            logs.append(self._export_log_record(record))
            limit = limit - 1
            if limit == 0:
                return logs
        return logs

    def _export_worker(self, worker):
        result = super(DebugDriveApi, self)._export_worker(worker)
        result["metrics"] = worker.get_metrics()
        if "action" in result["metrics"]:
            result["metrics"]["action"] = self._export_action(
                result["metrics"]["action"]
            )
        return result

    @pyqtSlot(str, str, str, str, str, int, str)
    def send_notification(
        self, notification_type, engine_uid, level, title, description, flags, action
    ):
        from ...notification import Notification

        try:
            notification = Notification(
                uid=str(notification_type),
                engine_uid=engine_uid or None,
                flags=flags,
                level=level,
                action=action,
                description=description,
                title=title,
            )
        except RuntimeError:
            log.exception("Notification error")
        else:
            center = self._manager.notification_service
            center.send_notification(notification)

    @pyqtSlot(str, result=str)
    def get_engine(self, uid):
        result = []
        engine = self._get_engine(uid)
        if engine:
            result = self._export_engine(engine)
        return self._json(result)

    @pyqtSlot(str)
    def resume_remote_watcher(self, uid):
        engine = self._get_engine(uid)
        if engine:
            engine._remote_watcher.resume()

    @pyqtSlot(str)
    def resume_local_watcher(self, uid):
        engine = self._get_engine(uid)
        if engine:
            engine._local_watcher.resume()

    @pyqtSlot(str)
    def suspend_remote_watcher(self, uid):
        engine = self._get_engine(str(uid))
        if engine:
            engine._remote_watcher.suspend()

    @pyqtSlot(str)
    def suspend_local_watcher(self, uid):
        engine = self._get_engine(uid)
        if engine:
            engine._local_watcher.suspend()

    @pyqtSlot(str)
    def resume_engine(self, uid):
        engine = self._get_engine(uid)
        if engine:
            engine.resume()

    @pyqtSlot(str)
    def suspend_engine(self, uid):
        engine = self._get_engine(uid)
        if engine:
            engine.suspend()

    @pyqtSlot(str)
    def direct_edit(self, url):
        try:
            self._manager.direct_edit.handle_url(url)
        except OSError:
            log.exception("Direct Edit error")

    @pyqtSlot(str, str)
    def set_app_update(self, status, version):
        self._manager.updater.force_status(status, version)

    @pyqtSlot(str, str)
    def resume_queue(self, uid, queue):
        engine = self._get_engine(uid)
        if engine:
            if queue == "local_file_queue":
                engine.get_queue_manager().enable_local_file_queue(value=True)
            elif queue == "local_folder_queue":
                engine.get_queue_manager().enable_local_folder_queue(value=True)
            elif queue == "remote_folder_queue":
                engine.get_queue_manager().enable_remote_folder_queue(value=True)
            elif queue == "remote_file_queue":
                engine.get_queue_manager().enable_remote_file_queue(value=True)

    @pyqtSlot(str, str)
    def suspend_queue(self, uid, queue):
        engine = self._get_engine(uid)
        if engine:
            if queue == "local_file_queue":
                engine.get_queue_manager().enable_local_file_queue(value=False)
            elif queue == "local_folder_queue":
                engine.get_queue_manager().enable_local_folder_queue(value=False)
            elif queue == "remote_folder_queue":
                engine.get_queue_manager().enable_remote_folder_queue(value=False)
            elif queue == "remote_file_queue":
                engine.get_queue_manager().enable_remote_file_queue(value=False)
