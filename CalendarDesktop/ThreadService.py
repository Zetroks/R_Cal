from PyQt5.QtCore import QThread, pyqtSignal, QObject, pyqtSlot

import time

from CalendarService import models, service
from CalendarService.dto_models import EventUpsertDTO


class WorkerExistException(Exception):
    pass


class InitWorker(QObject):
    finished = pyqtSignal(object, object)  # groups, access
    failed = pyqtSignal(str)

    def run(self):
        try:
            repo = service.EventRepository.get()
            groups = repo.get_all_type_colors()
            access = repo.get_my_access()
        except Exception as exc:
            self.failed.emit(str(exc))  # type: ignore
            return
        self.finished.emit(groups, access)  # type: ignore


class PollWorker(QObject):
    finished = pyqtSignal(object)  # response dict
    failed = pyqtSignal(str)

    def __init__(self, since: str, year: int):
        super().__init__()
        self.since = since
        self.year = year

    def run(self):
        try:
            data = service.EventRepository.get().get_updates(self.since, self.year)
        except Exception as exc:
            self.failed.emit(str(exc))  # type: ignore
            return
        self.finished.emit(data)  # type: ignore


class CollectYearWorker(QObject):
    __instance__ = None

    # throws WorkerExistException
    @classmethod
    def get(cls, year):
        if cls.__instance__ is None:
            cls.__instance__ = cls(year)
            return cls.__instance__
        raise WorkerExistException

    finished = pyqtSignal(models.YearEvents)

    def __init__(self, year):
        self.year = year
        super().__init__()

    def run(self):
        year = service.EventRepository.get().get_events_for_year(self.year)
        self.finished.emit(year)  # type: ignore
        CollectYearWorker.__instance__ = None


class PostWorker(QObject):
    finished = pyqtSignal(object)  # response

    def __init__(self):
        super().__init__()

    @pyqtSlot(str, object)
    def post(self, endpoint, json_data):
        response = service.EventRepository.get().POST(endpoint, json=json_data)
        self.finished.emit(response)  # type: ignore


class UploadWorker(QObject):
    __instance__ = None

    @classmethod
    def get(cls):
        if cls.__instance__ is None:
            cls.__instance__ = cls()
            return cls.__instance__
        return cls.__instance__

    response_signal = pyqtSignal(object, dict)

    def __init__(self):
        super().__init__()
        self.response_signal.connect(self.on_response)  # type: ignore
        self._sync_counter = 0

        self.pending: dict[int, models.EventModel] = {}
        self.in_flight: set[int] = set()

    def enqueue_delete(self, event: models.EventModel):
        event.is_deleted = True
        self.enqueue(event)

    def enqueue(self, event: models.EventModel):
        if event.sync_id is None:
            event.sync_id = self._sync_counter
            self._sync_counter += 1

        if event.sync_id in self.pending:
            return
        event.version += 1
        self.pending[event.sync_id] = event
        self.try_send()

    def try_send(self):
        for sync_id, event in list(self.pending.items()):

            if sync_id in self.in_flight:
                continue

            self.in_flight.add(sync_id)
            self.pending.pop(sync_id)

            self.send_async(event)

    def send_async(self, event: models.EventModel):
        # payload = deepcopy(event)  # 💥 КРИТИЧНО
        if event.is_deleted and event.id is None:
            return

        action = "delete" if event.is_deleted else "upsert"
        kind = event.event_type
        data = event.model_dump()

        if data.get("start_date"):
            data["start_date"] = data["start_date"].isoformat()
        if data.get("end_date"):
            data["end_date"] = data["end_date"].isoformat()

        dto = EventUpsertDTO(action=action, kind=kind, **data)
        endpoint = f"/event"
        thread = QThread()
        worker = PostWorker()

        worker.moveToThread(thread)

        def on_finished(response):
            self.response_signal.emit(event, response)  # type: ignore
            worker.deleteLater()
            thread.quit()
            thread.wait()
            thread.deleteLater()

        worker.finished.connect(on_finished)  # type: ignore
        thread.started.connect(lambda: worker.post(endpoint, dto.model_dump(mode="json")))  # type: ignore

        thread.start()

    @pyqtSlot(object, dict)
    def on_response(self, old_event: models.EventModel, response: dict):
        status = response.get("status", "None")
        if status == "deleted":
            self.in_flight.discard(old_event.sync_id)
            self.pending.pop(old_event.sync_id, None)
            self.try_send()
            return
        elif status == "403":
            self.in_flight.discard(old_event.sync_id)
            self.try_send()
            return
        else:
            if old_event.id is None:
                old_event.id = response["id"]
            self.in_flight.discard(old_event.sync_id)

            self.try_send()


class Worker(QObject):
    def __init__(self):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            self.do_task()
            time.sleep(1)

    def do_task(self):
        pass
