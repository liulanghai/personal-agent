"""Public response contracts shared with generated desktop/web clients."""
from typing import Any, Literal, Optional
from pydantic import BaseModel


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str


class Conversations(BaseModel):
    items: list[Conversation]


class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    run_id: str
    created_at: str


class Messages(BaseModel):
    items: list[Message]


class Run(BaseModel):
    id: str
    conversation_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    skill_id: Optional[str]
    file_ids: list[str]
    error: Optional[str]
    created_at: str
    updated_at: str


class Runs(BaseModel):
    items: list[Run]


class Skill(BaseModel):
    id: str
    name: str
    description: str
    scope: str
    source: str
    path: str
    directory: str
    unsupported_fields: list[str]


class Skills(BaseModel):
    items: list[Skill]


class SkillContent(BaseModel):
    id: str
    content: str


class AgentFile(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["upload", "artifact"]
    run_id: Optional[str]
    size: int
    created_at: str


class Files(BaseModel):
    items: list[AgentFile]


class Settings(BaseModel):
    base_url: str
    model: str
    has_api_key: bool
    timezone: str
    instruction_mode: Literal["auto", "codex", "claude"]
    workspace_path: str


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class ToolList(BaseModel):
    items: list[dict[str, Any]]


class RuleSource(BaseModel):
    scope: str
    path: str
    sha256: str


class DiscoveryResult(BaseModel):
    workspace_path: str
    instructions: list[RuleSource]
    skills: list[Skill]
    warnings: list[str]


class ContextManifest(BaseModel):
    sections: list[dict[str, Any]]
    total_characters: int
    limit_characters: int
