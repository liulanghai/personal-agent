"""Workspace file tools: list / read / search / write."""

from typing import Any, TypedDict

from ..store import Store, uid
from .paths import Workspace, ensure_inside

MAX_TEXT = 60000
MAX_LISTED = 100
MAX_MATCHES = 50
MAX_MATCH_TEXT = 400


class SearchMatch(TypedDict):
    path: str
    line: int
    text: str


class Artifact(TypedDict):
    id: str
    name: str
    path: str
    size: int


class FileTools:
    def __init__(self, workspace: Workspace, store: Store) -> None:
        self.workspace = workspace
        self.store = store

    def list_files(self) -> list[str]:
        root = self.workspace.root
        return [
            self.workspace.relative(p)
            for p in root.rglob("*")
            if p.is_file() and not p.is_symlink()
        ][:MAX_LISTED]

    def read_file(self, relative: str) -> dict[str, Any]:
        path = self.workspace.path(relative)
        if path.stat().st_size > MAX_TEXT:
            raise ValueError("File exceeds 60KB text limit")
        return {"path": relative, "content": path.read_text(encoding="utf-8")}

    def search_files(self, query: str) -> list[SearchMatch]:
        """Case-insensitive literal search over listed files; skips large or non-UTF-8 files."""
        needle = query.casefold()
        matches: list[SearchMatch] = []
        for relative in self.list_files():
            path = self.workspace.path(relative)
            if path.stat().st_size > MAX_TEXT:
                continue
            try:
                lines = path.read_text().splitlines()
            except UnicodeError:
                continue
            for index, line in enumerate(lines, 1):
                if needle in line.casefold():
                    matches.append({"path": relative, "line": index, "text": line[:MAX_MATCH_TEXT]})
                if len(matches) >= MAX_MATCHES:
                    return matches
        return matches

    def write_file(self, relative: str, content: str, run_id: str) -> Artifact:
        """Create a new artifact under reports/; existing files are never overwritten."""
        path = self.workspace.path(relative)
        reports = (self.workspace.root / "reports").resolve()
        ensure_inside(path, reports, "Artifacts must be created under reports/")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        artifact: Artifact = {
            "id": uid("file"),
            "name": path.name,
            "path": self.workspace.relative(path),
            "size": path.stat().st_size,
        }
        self.store.create_file(
            file_id=artifact["id"],
            name=artifact["name"],
            path=artifact["path"],
            kind="artifact",
            run_id=run_id,
            size=artifact["size"],
        )
        self.store.add_event(run_id, "artifact.created", artifact)
        return artifact
