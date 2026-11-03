"""Run lifecycle shared by web, SDK and future desktop clients.

A run is an asyncio task inside the single server process. Status changes are
persisted together with an event so SSE consumers can replay them.
"""

import asyncio
from collections.abc import Callable

from ..config import Settings
from ..context.builder import ContextBuilder
from ..store import ACTIVE_STATUSES, FileRow, Store
from ..tools.registry import Tools
from .loop import AgentLoop

INTERRUPTED_ERROR = "服务重启导致执行中断，请重新提交；首版不会自动重放有副作用的工具"


class Runtime:
    def __init__(self, store: Store, tools: Tools, settings: Callable[[], Settings]) -> None:
        self.store = store
        self.tools = tools
        self.settings = settings
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.context = ContextBuilder(tools)
        self.loop = AgentLoop(store, tools, settings, self.context)

    def recover_interrupted(self) -> None:
        """Mark runs left active by a previous process as failed.

        Side-effecting tools are never replayed automatically.
        """
        for run_id in self.store.list_active_run_ids():
            self.store.set_run_status(run_id, "failed", INTERRUPTED_ERROR)
            self.store.add_event(run_id, "run.failed", {"error": "服务重启，执行中断"})

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def launch(self, run_id: str) -> None:
        task = asyncio.create_task(self.execute(run_id))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def cancel(self, run_id: str) -> None:
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # A task cancelled before its first instruction cannot run its handler.
        current = self.store.get_run(run_id)
        if current and current["status"] in ACTIVE_STATUSES:
            self.store.set_run_status(run_id, "cancelled")
            self.store.add_event(run_id, "run.cancelled", {})

    async def execute(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            return
        self.store.set_run_status(run_id, "running")
        self.store.add_event(run_id, "run.started", {})
        try:
            files: list[FileRow] = []
            for file_id in run["file_ids"]:
                file = self.store.get_file(file_id)
                if file is not None:
                    files.append(file)
            output = await self.loop.run(run, files)
            self.store.add_assistant_message(run["conversation_id"], output, run_id)
            self.store.set_run_status(run_id, "completed")
            self.store.add_event(run_id, "run.completed", {})
        except asyncio.CancelledError:
            self.store.set_run_status(run_id, "cancelled")
            self.store.add_event(run_id, "run.cancelled", {})
        except Exception as exc:
            error = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "执行失败（" + type(exc).__name__ + "），请检查模型连接或本地文件"
            )
            self.store.set_run_status(run_id, "failed", error)
            self.store.add_event(run_id, "run.failed", {"error": error})
