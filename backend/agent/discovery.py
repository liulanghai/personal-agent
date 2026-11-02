"""Conventional instruction/skill discovery, independent of model providers."""
import hashlib
import os
import re
from pathlib import Path
import yaml

LIMIT = 60000


def text_file(path):
    if path.stat().st_size > LIMIT:
        raise ValueError("Context file exceeds 60KB: " + str(path))
    return path.read_text(encoding="utf-8")


class Discovery:
    def __init__(self, workspace, bundled, home=None):
        self.workspace = Path(workspace).resolve()
        self.bundled = Path(bundled)
        self.home = Path(home) if home is not None else Path.home()
        self.codex_home = Path(os.getenv("CODEX_HOME", self.home / ".codex")) if home is None else self.home / ".codex"
        self.warnings = []

    def instructions(self, mode="auto"):
        """One file per scope; auto prefers Codex names, reports alternatives."""
        result, warnings = [], []
        scopes = [
            ("user", [self.codex_home / "AGENTS.override.md", self.codex_home / "AGENTS.md"], [self.home / ".claude/CLAUDE.md"]),
            ("project", [self.workspace / "AGENTS.override.md", self.workspace / "AGENTS.md"], [self.workspace / "CLAUDE.md", self.workspace / ".claude/CLAUDE.md"]),
        ]
        for scope, codex, claude in scopes:
            candidates = codex if mode == "codex" else claude if mode == "claude" else codex + claude
            existing = [p for p in candidates if p.is_file()]
            chosen = None
            for path in existing:
                try:
                    text = text_file(path)
                    if text.strip():
                        chosen = path
                        result.append({"scope": scope, "path": str(path), "content": text, "sha256": hashlib.sha256(text.encode()).hexdigest()})
                        break
                except (OSError, UnicodeError, ValueError) as exc:
                    raise ValueError("无法加载规则文件：" + str(path)) from exc
            if chosen:
                warnings.extend("规则未合并（同层优先文件为 " + str(chosen) + "）：" + str(p) for p in existing if p != chosen)
        return result, warnings

    def skills(self):
        roots = [
            ("project", "agents", self.workspace / ".agents/skills"),
            ("project", "claude", self.workspace / ".claude/skills"),
            ("user", "agents", self.home / ".agents/skills"),
            ("user", "claude", self.home / ".claude/skills"),
            ("user", "codex-legacy", self.codex_home / "skills"),
            ("builtin", "bundled", self.bundled),
        ]
        result, seen, warnings = [], set(), []
        for scope, source, root in roots:
            if not root.is_dir():
                continue
            try:
                paths = sorted(root.glob("*/SKILL.md"))
                # Codex stores some bundled legacy skills below .system/.
                if source == "codex-legacy":
                    paths += sorted((root / ".system").glob("*/SKILL.md"))
            except OSError:
                warnings.append("无法扫描技能目录：" + str(root))
                continue
            for path in paths:
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    text = text_file(path)
                    header = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
                    if not header:
                        raise ValueError("Missing YAML frontmatter")
                    metadata = yaml.safe_load(header.group(1))
                    if not isinstance(metadata, dict):
                        raise ValueError("Invalid metadata")
                    name, description = metadata.get("name"), metadata.get("description")
                    if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not description.strip():
                        raise ValueError("name and description are required")
                    result.append({"id": name, "name": name, "description": description, "scope": scope, "source": source, "path": str(path), "directory": str(resolved.parent), "unsupported_fields": sorted(str(k) for k in metadata if k not in ("name", "description"))})
                except (OSError, UnicodeError, ValueError, yaml.YAMLError):
                    warnings.append("技能未加载，请检查 UTF-8、大小和 name/description：" + str(path))
        counts = {}
        for skill in result:
            counts[skill["id"]] = counts.get(skill["id"], 0) + 1
        for skill in result:
            if counts[skill["id"]] > 1:
                skill["id"] += "--" + hashlib.sha256(skill["path"].encode()).hexdigest()[:12]
        self.warnings = warnings
        return result

    def skill(self, skill_id):
        found = next((s for s in self.skills() if s["id"] == skill_id), None)
        if not found:
            raise ValueError("Unknown skill")
        return {**found, "content": text_file(Path(found["path"]))}

    def resource(self, skill_id, relative_path):
        skill = self.skill(skill_id)
        directory = Path(skill["directory"])
        path = (directory / relative_path).resolve()
        if directory not in path.parents:
            raise ValueError("Skill resource must stay inside its directory")
        return {"path": relative_path, "content": text_file(path)}
