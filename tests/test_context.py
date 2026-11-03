import json
from datetime import UTC, datetime

import pytest

from agent.context import ContextBuilder
from agent.store import Store
from agent.tools import Tools


@pytest.fixture
def tools(tmp_path):
    return Tools(
        tmp_path / "workspace",
        tmp_path / "bundled",
        Store(tmp_path / "test.sqlite"),
        home=tmp_path / "home",
    )


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def skill(path, name="example", extra=""):
    write(
        path / "SKILL.md",
        "---\nname: "
        + name
        + "\ndescription: |\n  A reusable workflow\n"
        + extra
        + "---\nPrivate body not loaded in catalog",
    )


def test_timezone_midnight_and_manifest_without_secrets(tools):
    builder = ContextBuilder(tools, clock=lambda: datetime(2026, 11, 2, 16, 1, tzinfo=UTC))
    run = {"id": "run_test", "conversation_id": "conv_test", "skill_id": None}
    messages, manifest = builder.build(
        {"timezone": "Asia/Shanghai", "api_key": "never-in-context"}, run, [], []
    )
    env = manifest["sections"][0]["environment"]
    assert env["current_date"] == "2026-11-03" and env["weekday"] == "星期二"
    assert env["current_datetime"].endswith("+08:00")
    assert "never-in-context" not in json.dumps([messages, manifest])
    _, other = builder.build({"timezone": "America/Los_Angeles"}, run, [], [])
    assert other["sections"][0]["environment"]["current_date"] == "2026-11-02"


def test_rule_scope_precedence_fallback_and_no_source_repo_leak(tools):
    write(tools.discovery.codex_home / "AGENTS.md", "User preference")
    write(tools.workspace / "AGENTS.md", "Project preference")
    write(tools.workspace / "CLAUDE.md", "Claude preference")
    write(tools.workspace.parent / "AGENTS.md", "Must not escape workspace")
    rules, warnings = tools.discovery.instructions()
    assert [r["content"] for r in rules] == ["User preference", "Project preference"]
    assert warnings
    write(tools.workspace / "AGENTS.override.md", "Override")
    assert tools.discovery.instructions()[0][-1]["content"] == "Override"
    assert tools.discovery.instructions("claude")[0][-1]["content"] == "Claude preference"
    (tools.workspace / "AGENTS.override.md").unlink()
    (tools.workspace / "AGENTS.md").unlink()
    assert tools.discovery.instructions()[0][-1]["content"] == "Claude preference"


def test_skill_roots_duplicates_symlinks_and_lazy_loading(tools):
    skill(tools.workspace / ".agents/skills/example")
    skill(tools.discovery.home / ".claude/skills/example", extra="allowed-tools: Bash\n")
    skill(tools.discovery.codex_home / "skills/legacy")
    skill(tools.discovery.bundled / "builtin")
    (tools.workspace / ".agents/skills/alias").symlink_to(
        tools.workspace / ".agents/skills/example", target_is_directory=True
    )
    items = tools.skills()
    assert len(items) == 4
    assert len({s["id"] for s in items}) == 4
    assert all("Private body" not in json.dumps(s) for s in items)
    assert any(s["unsupported_fields"] == ["allowed-tools"] for s in items)
    for item in items:
        assert "Private body" in tools.skill(item["id"])["content"]
    skill(tools.workspace / ".claude/skills/new-skill")
    assert len(tools.skills()) == 5


def test_skill_resources_and_boundaries(tools):
    root = tools.workspace / ".agents/skills/example"
    skill(root)
    write(root / "references/template.md", "Reference text")
    assert (
        tools.execute(
            "read_skill_resource", {"skill_id": "example", "path": "references/template.md"}, "test"
        )["content"]
        == "Reference text"
    )
    with pytest.raises(ValueError):
        tools.discovery.resource("example", "../outside.txt")
    outside = tools.workspace / "secret.txt"
    outside.write_text("secret")
    (root / "escape.txt").symlink_to(outside)
    with pytest.raises(ValueError):
        tools.discovery.resource("example", "escape.txt")


def test_context_budget_and_extension_provider(tools):
    run = {"id": "run", "conversation_id": "conv"}

    def provider(config, run):
        return {"name": "test_extension", "data": {"version": 1}}

    messages, manifest = ContextBuilder(tools, providers=[provider]).build({}, run, [], [])
    assert "test_extension" in messages[0]["content"]
    assert manifest["sections"][0]["name"] == "test_extension"
    with pytest.raises(ValueError, match="长度预算"):
        ContextBuilder(tools, max_chars=10).build({}, run, [], [])


def test_invalid_skill_is_reported_without_breaking_catalog(tools):
    write(tools.workspace / ".agents/skills/broken/SKILL.md", "not metadata")
    assert tools.skills() == []
    assert tools.discovery.warnings
