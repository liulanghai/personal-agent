"""Application assembly: settings, store, tools, runtime, middleware, routes, static files.

No business logic lives here; see api/routes/* for endpoints and runtime/* for runs.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import security
from .api import errors
from .api.deps import Services
from .api.routes import conversations, files, runs, settings, skills, system
from .config import SettingsStore
from .runtime.runtime import Runtime
from .store import Store
from .tools.registry import Tools

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

API_PREFIX = "/api/v1"


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    data = Path(data_dir or os.getenv("AGENT_DATA_DIR") or ROOT / "data").resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    store = Store(data / "agent.sqlite")
    tools = Tools(os.getenv("AGENT_WORKSPACE", data / "workspace"), ROOT / "skills", store)
    config = SettingsStore(data / "settings.json")
    runtime = Runtime(store, tools, config.load)
    services = Services(store=store, tools=tools, settings=config, runtime=runtime)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime.recover_interrupted()
        yield
        await runtime.shutdown()

    app = FastAPI(title="Personal Agent API", version=system.VERSION, lifespan=lifespan)
    app.state.store, app.state.runtime = store, runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(security.DEV_ORIGINS),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )
    security.install(app)
    errors.install(app)

    app.include_router(system.build(), prefix=API_PREFIX)
    for module in (settings, conversations, runs, skills, files):
        app.include_router(module.build(services), prefix=API_PREFIX)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
