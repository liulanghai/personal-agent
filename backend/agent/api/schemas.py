"""Public request/response contracts shared with generated desktop/web clients.

Changing anything here changes docs/openapi.json and the SDK: run `make gen`.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# -- requests ---------------------------------------------------------------


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


# -- responses --------------------------------------------------------------


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
    skill_id: str | None
    file_ids: list[str]
    error: str | None
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
    run_id: str | None
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
