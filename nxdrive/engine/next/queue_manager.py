# coding: utf-8
import time
from logging import getLogger

from ..queue_manager import QueueManager as OldQueueManager
from ...objects import NuxeoDocumentInfo

__all__ = ("QueueManager",)

log = getLogger(__name__)


class QueueManager(OldQueueManager):
    def __init__(
        self, engine: "Engine", dao: "EngineDAO", max_file_processors: int = 5
    ) -> None:
        super().__init__(engine, dao, max_file_processors=max_file_processors)

    def postpone_pair(self, doc_pair: NuxeoDocumentInfo, interval: int = 60) -> None:
        doc_pair.error_next_try = interval + int(time.time())
        log.debug("Blacklisting pair for %ds: %r", interval, doc_pair)
        with self._error_lock:
            self._on_error_queue[doc_pair.id] = doc_pair
            if not self._error_timer.isActive():
                self.newError.emit(doc_pair.id)
