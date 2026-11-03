from pathlib import Path

from jsonschema import validate

from .discovery import Discovery
from .store import now, uid

MAX_TEXT = 60000


def schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


STR = {"type": "string", "minLength": 1}
DEFINITIONS = [
    schema(
        "read_skill_resource",
        "Read a UTF-8 reference or template within a discovered skill; does not execute scripts.",
        {"skill_id": STR, "path": STR},
        ["skill_id", "path"],
    ),
    schema("list_files", "List up to 100 files in the workspace.", {}, []),
    schema(
        "read_file", "Read a UTF-8 text file in workspace (up to 60KB).", {"path": STR}, ["path"]
    ),
    schema("search_files", "Search UTF-8 files using a literal query.", {"query": STR}, ["query"]),
    schema(
        "write_file",
        "Create a new UTF-8 artifact under reports/. Existing files cannot be overwritten.",
        {"path": STR, "content": {"type": "string", "maxLength": MAX_TEXT}},
        ["path", "content"],
    ),
    schema("list_skills", "List available skills and their descriptions.", {}, []),
    schema("read_skill", "Load full instructions for a skill.", {"skill_id": STR}, ["skill_id"]),
]


class Tools:
    def __init__(self, workspace, skills, store, home=None):
        self.workspace, self.skills_dir, self.store = Path(workspace).resolve(), Path(skills), store
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.discovery = Discovery(self.workspace, skills, home)

    def path(self, value):
        path = (self.workspace / value).resolve()
        if path == self.workspace or self.workspace not in path.parents:
            raise ValueError("Path must be a file inside workspace")
        return path

    def skills(self):
        return self.discovery.skills()

    def skill(self, skill_id):
        return self.discovery.skill(skill_id)

    def execute(self, name, args, run_id):
        definition = next((d for d in DEFINITIONS if d["function"]["name"] == name), None)
        if not definition:
            raise ValueError("Unknown tool")
        validate(args, definition["function"]["parameters"])
        if name == "read_skill_resource":
            return self.discovery.resource(args["skill_id"], args["path"])
        if name == "list_skills":
            return self.skills()
        if name == "read_skill":
            return self.skill(args["skill_id"])
        if name == "list_files":
            return [
                str(p.relative_to(self.workspace))
                for p in self.workspace.rglob("*")
                if p.is_file() and not p.is_symlink()
            ][:100]
        if name == "read_file":
            path = self.path(args["path"])
            if path.stat().st_size > MAX_TEXT:
                raise ValueError("File exceeds 60KB text limit")
            return {"path": args["path"], "content": path.read_text(encoding="utf-8")}
        if name == "search_files":
            matches = []
            for relative in self.execute("list_files", {}, run_id):
                path = self.path(relative)
                if path.stat().st_size > MAX_TEXT:
                    continue
                try:
                    for index, line in enumerate(path.read_text().splitlines(), 1):
                        if args["query"].casefold() in line.casefold():
                            matches.append({"path": relative, "line": index, "text": line[:400]})
                        if len(matches) >= 50:
                            return matches
                except UnicodeError:
                    continue
            return matches
        path = self.path(args["path"])
        if (self.workspace / "reports").resolve() not in path.parents:
            raise ValueError("Artifacts must be created under reports/")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(args["content"])
        file_id = uid("file")
        size = path.stat().st_size
        self.store.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?)",
            (
                file_id,
                path.name,
                str(path.relative_to(self.workspace)),
                "artifact",
                run_id,
                size,
                now(),
            ),
        )
        artifact = {
            "id": file_id,
            "name": path.name,
            "path": str(path.relative_to(self.workspace)),
            "size": size,
        }
        self.store.event(run_id, "artifact.created", artifact)
        return artifact
