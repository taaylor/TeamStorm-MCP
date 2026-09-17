"""Standalone polling process; suitable for supervision by systemd."""

import asyncio
import logging
import signal

from teamstorm_mcp.adapters.config import Settings
from teamstorm_mcp.adapters.sqlite_closures import SQLiteClosureRepository
from teamstorm_mcp.adapters.teamstorm.client import TeamStormClient
from teamstorm_mcp.adapters.workflow import load_workflow
from teamstorm_mcp.application.services.closure_worker import ClosureWorker
from teamstorm_mcp.application.services.teamstorm import TeamStormService


async def run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    workflow = load_workflow(settings.teamstorm_workflow_path)
    repository = SQLiteClosureRepository(settings.teamstorm_queue_path.expanduser())
    await repository.initialize()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with TeamStormClient(
            base_url=str(settings.teamstorm_url),
            token=settings.teamstorm_token,
            timeout=settings.teamstorm_timeout,
        ) as client:
            service = TeamStormService(client, workflow=workflow)
            worker = ClosureWorker(
                repository, service, workflow_service=service if workflow else None
            )
            logging.getLogger(__name__).info(
                "Daemon started in %s mode", "workflow" if workflow else "context-only"
            )
            await worker.run(stop, interval=settings.teamstorm_daemon_interval)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
