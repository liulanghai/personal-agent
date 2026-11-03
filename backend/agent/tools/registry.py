"""Tool definitions (OpenAI function schema), argument validation and dispatch.

``Tools`` is the single object the runtime and API use to reach the workspace,
skills and tool execution.
"""

from pathlib import Path
from typing import Any

from jsonschema import validate

from ..context.discovery import Discovery, SkillContent, SkillInfo
from ..store import Store
from .files import MAX_TEXT, FileTools
from .paths import Workspace
from .skills import SkillTools

ToolDefinition = dict[str, Any]


def schema(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> ToolDefinition:
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
DEFINITIONS: list[ToolDefinition] = [
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


def definition(name: str) -> ToolDefinition | None:
    return next((d for d in DEFINITIONS if d["function"]["name"] == name), None)


class Tools:
    def __init__(
        self,
        workspace: str | Path,
        skills: str | Path,
        store: Store,
        home: str | Path | None = None,
    ) -> None:
        self.store = store
        self._workspace = Workspace(workspace)
        self.discovery = Discovery(self._workspace.root, skills, home)
        self.files = FileTools(self._workspace, store)
        self.skill_tools = SkillTools(self.discovery)

    @property
    def workspace(self) -> Path:
        return self._workspace.root

    def path(self, relative: str) -> Path:
        return self._workspace.path(relative)

    def skills(self) -> list[SkillInfo]:
        return self.skill_tools.list_skills()

    def skill(self, skill_id: str) -> SkillContent:
        return self.skill_tools.read_skill(skill_id)

    def execute(self, name: str, args: dict[str, Any], run_id: str) -> Any:
        """Validate ``args`` against the tool schema and run the tool.

        Raises on unknown tools, invalid arguments or tool failures; the runtime
        turns exceptions into structured tool errors for the model.
        """
        found = definition(name)
        if not found:
            raise ValueError("Unknown tool")
        validate(args, found["function"]["parameters"])
        match name:
            case "read_skill_resource":
                return self.skill_tools.read_skill_resource(args["skill_id"], args["path"])
            case "list_skills":
                return self.skill_tools.list_skills()
            case "read_skill":
                return self.skill_tools.read_skill(args["skill_id"])
            case "list_files":
                return self.files.list_files()
            case "read_file":
                return self.files.read_file(args["path"])
            case "search_files":
                return self.files.search_files(args["query"])
            case "write_file":
                return self.files.write_file(args["path"], args["content"], run_id)
        raise ValueError("Unknown tool")
