"""Uploaded source files, generated artifacts and file content download."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ...store import FileRow, uid
from .. import schemas as api
from ..deps import Services, require_file

MAX_UPLOAD = 60000
UPLOAD_SUFFIXES = (".md", ".txt", ".csv", ".json", ".log")


def build(services: Services) -> APIRouter:
    router = APIRouter()
    store, tools = services.store, services.tools

    @router.post("/files", status_code=201, response_model=api.AgentFile)
    async def upload(file: UploadFile = File(...)) -> FileRow:
        content = await file.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "首版支持最大 60KB 的 UTF-8 文本文件")
        try:
            content.decode("utf-8")
        except UnicodeError:
            raise HTTPException(
                422, "首版支持 UTF-8 文本和 Markdown；暂不支持 PDF、Word 或图片"
            ) from None
        file_id = uid("file")
        name = Path(file.filename or "document.txt").name[:180]
        if Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
            raise HTTPException(422, "支持 .md .txt .csv .json .log")
        relative = "uploads/" + file_id + "/" + name
        path = tools.path(relative)
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        store.create_file(
            file_id=file_id,
            name=name,
            path=relative,
            kind="upload",
            run_id=None,
            size=len(content),
        )
        return require_file(store, file_id)

    @router.get("/artifacts", response_model=api.Files)
    async def artifacts(run_id: str | None = None) -> dict[str, Any]:
        return {"items": store.list_artifacts(run_id)}

    @router.get("/files/{fid}/content")
    async def file_content(fid: str) -> FileResponse:
        file = require_file(store, fid)
        return FileResponse(
            tools.path(file["path"]), filename=file["name"], media_type="text/plain; charset=utf-8"
        )

    return router
