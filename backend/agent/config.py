"""Model and runtime settings: load from data/settings.json or environment, validate, save.

Security rules (unchanged from P0):
- The API key is never returned to clients; only ``has_api_key`` is exposed.
- Changing ``base_url`` while a key exists requires re-entering the key, so an
  old key is never sent to a new service.
- The settings file is written atomically with mode 0600.
"""

import json
import os
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

InstructionMode = Literal["auto", "codex", "claude"]

DEFAULTS = {"timezone": "Asia/Shanghai", "instruction_mode": "auto"}


class Settings(TypedDict):
    base_url: str
    model: str
    api_key: NotRequired[str]
    timezone: str
    instruction_mode: InstructionMode


class SettingsUpdate(TypedDict):
    base_url: str
    model: str
    api_key: str | None
    timezone: str | None
    instruction_mode: InstructionMode | None


class SettingsError(ValueError):
    """User-facing validation error; the message is shown verbatim."""


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Settings:
        if self.path.exists():
            # Unknown legacy keys (e.g. "mode") are kept on disk and ignored by readers.
            return cast(Settings, {**DEFAULTS, **json.loads(self.path.read_text())})
        return cast(
            Settings,
            {
                **DEFAULTS,
                "base_url": os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1"),
                "model": os.getenv("MODEL_NAME", ""),
                "api_key": os.getenv("MODEL_API_KEY", ""),
            },
        )

    def update(self, update: SettingsUpdate) -> Settings:
        """Validate an update against the current settings and persist it."""
        url = urlparse(update["base_url"])
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise SettingsError("模型地址必须为不含凭证、查询参数的 HTTP(S) URL")
        if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise SettingsError("远程模型服务必须使用 HTTPS")
        previous = self.load()
        value: dict[str, object] = dict(update)
        if value["timezone"] is None:
            value["timezone"] = previous["timezone"]
        if value["instruction_mode"] is None:
            value["instruction_mode"] = previous["instruction_mode"]
        try:
            ZoneInfo(str(value["timezone"]))
        except (ZoneInfoNotFoundError, ValueError):
            raise SettingsError("无效时区，请填写 Asia/Shanghai 等 IANA 时区") from None
        if update["api_key"] is None:
            base_changed = update["base_url"].rstrip("/") != previous["base_url"].rstrip("/")
            if base_changed and previous.get("api_key"):
                raise SettingsError("更换模型地址时请重新输入密钥，避免将旧密钥发送给新服务")
            value["api_key"] = previous.get("api_key", "")
        if not update["model"].strip():
            raise SettingsError("请填写模型名称")
        self._write(value)
        return self.load()

    def _write(self, value: dict[str, object]) -> None:
        temp = self.path.with_suffix(".tmp")
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
        temp.replace(self.path)
