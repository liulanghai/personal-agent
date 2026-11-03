from pathlib import Path

import pytest
from jsonschema import ValidationError

from agent.store import Store
from agent.tools.files import MAX_MATCH_TEXT, MAX_MATCHES, MAX_TEXT
from agent.tools.registry import Tools


@pytest.fixture
def tools(tmp_path: Path) -> Tools:
    return Tools(
        tmp_path / "workspace",
        tmp_path / "bundled",
        Store(tmp_path / "test.sqlite"),
        home=tmp_path / "home",
    )


def write(tools: Tools, relative: str, content: str | bytes) -> None:
    path = tools.workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def search(tools: Tools, query: str) -> list[dict[str, object]]:
    result = tools.execute("search_files", {"query": query}, "test")
    assert isinstance(result, list)
    return result


def test_search_is_case_insensitive_literal_with_line_numbers(tools: Tools) -> None:
    write(tools, "notes/a.md", "first line\nAPI design done\nnothing here\n")
    write(tools, "b.txt", "regex chars a.*b are literal\n")
    assert search(tools, "api DESIGN") == [
        {"path": "notes/a.md", "line": 2, "text": "API design done"}
    ]
    assert search(tools, "a.*b") == [
        {"path": "b.txt", "line": 1, "text": "regex chars a.*b are literal"}
    ]
    assert search(tools, "missing") == []


def test_search_skips_non_utf8_large_files_and_symlinks(tools: Tools, tmp_path: Path) -> None:
    write(tools, "binary.log", b"\xff\xfe needle")
    write(tools, "large.txt", "needle\n" + "x" * MAX_TEXT)
    outside = tmp_path / "outside.txt"
    outside.write_text("needle outside workspace")
    (tools.workspace / "link.txt").symlink_to(outside)
    write(tools, "ok.md", "needle")
    assert search(tools, "needle") == [{"path": "ok.md", "line": 1, "text": "needle"}]


def test_search_caps_matches_and_truncates_lines(tools: Tools) -> None:
    write(tools, "many.txt", "\n".join("hit " + str(i) for i in range(MAX_MATCHES + 10)))
    write(tools, "long.txt", "hit " + "y" * (MAX_MATCH_TEXT * 2))
    matches = search(tools, "hit")
    assert len(matches) == MAX_MATCHES
    long_matches = [m for m in search(tools, "hit y") if m["path"] == "long.txt"]
    assert [len(str(m["text"])) for m in long_matches] == [MAX_MATCH_TEXT]


def test_search_requires_non_empty_query(tools: Tools) -> None:
    with pytest.raises(ValidationError):
        tools.execute("search_files", {"query": ""}, "test")


def test_read_file_rejects_files_over_text_limit(tools: Tools) -> None:
    write(tools, "large.txt", "x" * (MAX_TEXT + 1))
    with pytest.raises(ValueError, match="60KB"):
        tools.execute("read_file", {"path": "large.txt"}, "test")
