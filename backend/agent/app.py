import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import schemas as api
from .runtime import Runtime
from .store import Store, now, uid
from .tools import DEFINITIONS, Tools

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class ConversationInput(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=120)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=30000)
    skill_id: str | None = None
    file_ids: list[str] = Field(default_factory=list, max_length=10)


class SettingsInput(BaseModel):
    base_url: str = Field(max_length=500)
    model: str = Field(max_length=200)
    api_key: str | None = Field(default=None, max_length=4000)
    timezone: str | None = Field(default=None, max_length=100)
    instruction_mode: Literal["auto", "codex", "claude"] | None = None


def create_app(data_dir=None):
    data = Path(data_dir or os.getenv("AGENT_DATA_DIR", ROOT / "data")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    config_path = data / "settings.json"
    store = Store(data / "agent.sqlite")
    tools = Tools(os.getenv("AGENT_WORKSPACE", data / "workspace"), ROOT / "skills", store)

    def settings():
        if config_path.exists():
            return {
                "timezone": "Asia/Shanghai",
                "instruction_mode": "auto",
                **json.loads(config_path.read_text()),
            }
        return {
            "timezone": "Asia/Shanghai",
            "instruction_mode": "auto",
            "base_url": os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("MODEL_NAME", ""),
            "api_key": os.getenv("MODEL_API_KEY", ""),
        }

    runtime = Runtime(store, tools, settings)

    @asynccontextmanager
    async def lifespan(app):
        for run in store.rows("SELECT id FROM runs WHERE status IN ('queued','running')"):
            store.status(
                run["id"],
                "failed",
                "服务重启导致执行中断，请重新提交；首版不会自动重放有副作用的工具",
            )
            store.event(run["id"], "run.failed", {"error": "服务重启，执行中断"})
        yield
        tasks = list(runtime.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Personal Agent API", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.runtime = store, runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def security(request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            allowed = {
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                str(request.base_url).rstrip("/"),
            }
            if origin and origin not in allowed:
                return JSONResponse(
                    {"error": {"code": "origin_forbidden", "message": "Origin not allowed"}},
                    status_code=403,
                )
            token = os.getenv("AGENT_API_TOKEN", "")
            if (
                token
                and request.method != "OPTIONS"
                and not hmac.compare_digest(
                    request.headers.get("authorization", ""), "Bearer " + token
                )
            ):
                return JSONResponse(
                    {"error": {"code": "unauthorized", "message": "API token required"}},
                    status_code=401,
                )
            if (
                not token
                and request.client
                and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient")
            ):
                return JSONResponse(
                    {
                        "error": {
                            "code": "token_required",
                            "message": "Remote access requires AGENT_API_TOKEN",
                        }
                    },
                    status_code=403,
                )
            # Block DNS rebinding against an unauthenticated loopback server.
            if not token and request.url.hostname not in (
                "127.0.0.1",
                "localhost",
                "::1",
                "testserver",
            ):
                return JSONResponse(
                    {"error": {"code": "host_forbidden", "message": "Loopback host required"}},
                    status_code=403,
                )
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": "http_" + str(exc.status_code), "message": str(exc.detail)}},
            status_code=exc.status_code,
        )

    def require(table, item_id):
        row = store.one("SELECT * FROM " + table + " WHERE id=?", (item_id,))
        if not row:
            raise HTTPException(404, "Resource not found")
        return row

    def public_run(row):
        return {**row, "file_ids": json.loads(row["file_ids"])}

    @app.get("/api/v1/health", response_model=api.Health)
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/settings", response_model=api.Settings)
    async def get_settings():
        config = settings()
        return {k: config[k] for k in ("base_url", "model", "timezone", "instruction_mode")} | {
            "has_api_key": bool(config.get("api_key")),
            "workspace_path": str(tools.workspace),
        }

    @app.put("/api/v1/settings", response_model=api.Settings)
    async def put_settings(body: SettingsInput):
        url = urlparse(body.base_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise HTTPException(422, "模型地址必须为不含凭证、查询参数的 HTTP(S) URL")
        if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise HTTPException(422, "远程模型服务必须使用 HTTPS")
        previous = settings()
        value = body.model_dump()
        for field in ("timezone", "instruction_mode"):
            if value[field] is None:
                value[field] = previous[field]
        try:
            ZoneInfo(value["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "无效时区，请填写 Asia/Shanghai 等 IANA 时区") from None
        if body.api_key is None:
            if body.base_url.rstrip("/") != previous["base_url"].rstrip("/") and previous.get(
                "api_key"
            ):
                raise HTTPException(422, "更换模型地址时请重新输入密钥，避免将旧密钥发送给新服务")
            value["api_key"] = previous.get("api_key", "")
        if not body.model.strip():
            raise HTTPException(422, "请填写模型名称")
        temp = config_path.with_suffix(".tmp")
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
        temp.replace(config_path)
        return await get_settings()

    @app.get("/api/v1/conversations", response_model=api.Conversations)
    async def conversations():
        return {"items": store.rows("SELECT * FROM conversations ORDER BY created_at DESC")}

    @app.post("/api/v1/conversations", status_code=201, response_model=api.Conversation)
    async def create_conversation(body: ConversationInput):
        cid = uid("conv")
        store.execute("INSERT INTO conversations VALUES (?,?,?)", (cid, body.title, now()))
        return require("conversations", cid)

    @app.get("/api/v1/conversations/{cid}/messages", response_model=api.Messages)
    async def messages(cid: str):
        require("conversations", cid)
        return {
            "items": store.rows(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid", (cid,)
            )
        }

    @app.post("/api/v1/conversations/{cid}/messages", status_code=202, response_model=api.Run)
    async def send_message(
        cid: str,
        body: MessageInput,
        idempotency_key: str | None = Header(default=None, max_length=200),
    ):
        require("conversations", cid)
        digest = hashlib.sha256((cid + body.model_dump_json()).encode()).hexdigest()
        if idempotency_key:
            previous = store.one("SELECT * FROM runs WHERE request_key=?", (idempotency_key,))
            if previous:
                if previous["request_hash"] != digest:
                    raise HTTPException(409, "Idempotency key reused with different input")
                return public_run(previous)
        if not body.content.strip():
            raise HTTPException(422, "Message must not be blank")
        if body.skill_id and body.skill_id not in [s["id"] for s in tools.skills()]:
            raise HTTPException(422, "Unknown skill")
        for file_id in body.file_ids:
            file = require("files", file_id)
            if file["kind"] != "upload":
                raise HTTPException(422, "Only uploaded source files can be attached")
        rid, timestamp = uid("run"), now()
        try:
            with store.connect() as db:
                db.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        cid,
                        "queued",
                        body.skill_id,
                        json.dumps(body.file_ids),
                        None,
                        timestamp,
                        timestamp,
                        idempotency_key,
                        digest,
                    ),
                )
                db.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                    (uid("msg"), cid, "user", body.content, rid, timestamp),
                )
                db.execute(
                    "UPDATE conversations SET title=? WHERE id=? AND title='新对话'",
                    (body.content[:32], cid),
                )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Conversation already has an active run") from None
        runtime.launch(rid)
        return public_run(require("runs", rid))

    @app.get("/api/v1/runs", response_model=api.Runs)
    async def runs(conversation_id: str | None = None):
        rows = (
            store.rows(
                "SELECT * FROM runs WHERE conversation_id=? ORDER BY created_at DESC LIMIT 100",
                (conversation_id,),
            )
            if conversation_id
            else store.rows("SELECT * FROM runs ORDER BY created_at DESC LIMIT 100")
        )
        return {"items": [public_run(row) for row in rows]}

    @app.get("/api/v1/runs/{rid}/context", response_model=api.ContextManifest)
    async def run_context(rid: str):
        require("runs", rid)
        event = store.one(
            "SELECT data FROM events WHERE run_id=? AND type='context.built' "
            "ORDER BY sequence DESC LIMIT 1",
            (rid,),
        )
        if not event:
            raise HTTPException(404, "此任务暂无上下文记录")
        return json.loads(event["data"])

    @app.get("/api/v1/discovery", response_model=api.DiscoveryResult)
    async def discovery():
        skills = tools.skills()
        rules, warnings = tools.discovery.instructions(settings()["instruction_mode"])
        return {
            "workspace_path": str(tools.workspace),
            "instructions": [{k: r[k] for k in ("scope", "path", "sha256")} for r in rules],
            "skills": skills,
            "warnings": warnings + tools.discovery.warnings,
        }

    @app.get("/api/v1/runs/{rid}", response_model=api.Run)
    async def run(rid: str):
        return public_run(require("runs", rid))

    @app.post("/api/v1/runs/{rid}/cancel", response_model=api.Run)
    async def cancel(rid: str):
        current = require("runs", rid)
        if current["status"] in ("queued", "running"):
            task = runtime.tasks.get(rid)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            # A task cancelled before its first instruction cannot run its handler.
            if require("runs", rid)["status"] in ("queued", "running"):
                store.status(rid, "cancelled")
                store.event(rid, "run.cancelled", {})
        return public_run(require("runs", rid))

    @app.get("/api/v1/runs/{rid}/events")
    async def events(
        rid: str,
        request: Request,
        after: int = 0,
        last_event_id: str | None = Header(default=None),
    ):
        require("runs", rid)
        if last_event_id:
            event = store.one(
                "SELECT sequence FROM events WHERE id=? AND run_id=?", (last_event_id, rid)
            )
            if not event:
                raise HTTPException(400, "Invalid event cursor")
            after = event["sequence"]

        async def stream():
            cursor = after
            ticks = 0
            while not await request.is_disconnected():
                batch = store.events(rid, cursor)
                for event in batch:
                    yield (
                        "id: "
                        + event["id"]
                        + "\ndata: "
                        + json.dumps(event, ensure_ascii=False)
                        + "\n\n"
                    )
                    cursor = event["sequence"]
                if not batch and require("runs", rid)["status"] not in ("queued", "running"):
                    break
                ticks += 1
                if ticks % 40 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/skills", response_model=api.Skills)
    async def skills():
        return {"items": tools.skills()}

    @app.get("/api/v1/skills/{skill_id}", response_model=api.SkillContent)
    async def skill(skill_id: str):
        try:
            return tools.skill(skill_id)
        except ValueError:
            raise HTTPException(404, "Unknown skill") from None

    @app.get("/api/v1/tools", response_model=api.ToolList)
    async def tool_definitions():
        return {"items": DEFINITIONS}

    @app.post("/api/v1/files", status_code=201, response_model=api.AgentFile)
    async def upload(file: UploadFile = File(...)):
        content = await file.read(60001)
        if len(content) > 60000:
            raise HTTPException(413, "首版支持最大 60KB 的 UTF-8 文本文件")
        try:
            content.decode("utf-8")
        except UnicodeError:
            raise HTTPException(
                422, "首版支持 UTF-8 文本和 Markdown；暂不支持 PDF、Word 或图片"
            ) from None
        file_id = uid("file")
        name = Path(file.filename or "document.txt").name[:180]
        if Path(name).suffix.lower() not in (".md", ".txt", ".csv", ".json", ".log"):
            raise HTTPException(422, "支持 .md .txt .csv .json .log")
        relative = "uploads/" + file_id + "/" + name
        path = tools.path(relative)
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        store.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?)",
            (file_id, name, relative, "upload", None, len(content), now()),
        )
        return require("files", file_id)

    @app.get("/api/v1/artifacts", response_model=api.Files)
    async def artifacts(run_id: str | None = None):
        return {
            "items": store.rows(
                "SELECT * FROM files WHERE kind='artifact' AND run_id=? ORDER BY created_at DESC",
                (run_id,),
            )
            if run_id
            else store.rows(
                "SELECT * FROM files WHERE kind='artifact' ORDER BY created_at DESC LIMIT 100"
            )
        }

    @app.get("/api/v1/files/{fid}/content")
    async def file_content(fid: str):
        file = require("files", fid)
        return FileResponse(
            tools.path(file["path"]), filename=file["name"], media_type="text/plain; charset=utf-8"
        )

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
