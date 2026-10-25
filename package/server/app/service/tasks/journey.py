"""Run journey matching outside the ticket/photo save path."""
import asyncio

from app.db.models.task import TaskType
from app.service.task_strategy import BaseTaskStrategy, TaskStrategyFactory


def _run(bind, owner_id):
    from sqlalchemy.orm import Session
    from app.db.models.trip import TrainTicket
    from app.service.tasks.ai_runtime import AIBatchSession
    from app.service.journey import discover, load_stations, _station
    # Do reference database I/O before reserving SQLite's writer. The matching
    # transaction reloads source tickets; concurrent changes leave another task.
    with Session(bind=bind) as source:
        names = {name for row in source.query(TrainTicket.departure_station, TrainTicket.arrival_station)
                 .filter(TrainTicket.owner_id == owner_id) for name in row}
    places = load_stations({_station(name) for name in names}) if names else {}
    with AIBatchSession(bind=bind, autoflush=False) as db:
        db.begin_write()
        rows = discover(db, owner_id, _stations=places)
        ids = [str(row.id) for row in rows]
        if len(ids) >= 200:
            from app.service.journey_queue import enqueue
            enqueue(db, owner_id)
        db.commit()
        return {"created": len(ids), "memory_ids": ids}


@TaskStrategyFactory.register(TaskType.ASSOCIATE_JOURNEYS)
class AssociateJourneysStrategy(BaseTaskStrategy):
    @property
    def task_category(self):
        return "CPU"

    @property
    def resource_key(self):
        return "journey"

    async def process(self, worker, task, db):
        if task.owner_id is None:
            raise ValueError("行程关联任务缺少所有者")
        return await asyncio.to_thread(_run, db.get_bind(), task.owner_id)
