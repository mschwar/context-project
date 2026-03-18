"""Regression tests for DEFAULT_PROMPT_TEMPLATES.

Smoke-tests that each template (a) exists, (b) is a non-empty string, and
(c) contains the core instructions that downstream parsing relies on.
Tests use a FakeLLMClient so no real API calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ctx.llm import DEFAULT_PROMPT_TEMPLATES


# ---------------------------------------------------------------------------
# Template existence and structure
# ---------------------------------------------------------------------------

REQUIRED_TEMPLATES = [
    "file_summary",
    "file_summary_system",
    "single_file_summary",
    "single_file_system",
    "directory_summary",
    "directory_summary_system",
]


@pytest.mark.parametrize("key", REQUIRED_TEMPLATES)
def test_template_exists_and_is_nonempty(key: str) -> None:
    assert key in DEFAULT_PROMPT_TEMPLATES
    assert isinstance(DEFAULT_PROMPT_TEMPLATES[key], str)
    assert len(DEFAULT_PROMPT_TEMPLATES[key].strip()) > 0


def test_file_summary_contains_json_payload_placeholder() -> None:
    assert "{json_payload}" in DEFAULT_PROMPT_TEMPLATES["file_summary"]


def test_directory_summary_contains_json_payload_placeholder() -> None:
    assert "{json_payload}" in DEFAULT_PROMPT_TEMPLATES["directory_summary"]


def test_single_file_summary_contains_json_payload_placeholder() -> None:
    assert "{json_payload}" in DEFAULT_PROMPT_TEMPLATES["single_file_summary"]


def test_file_summary_system_mentions_json_array() -> None:
    # The system prompt must instruct the model to return a JSON array
    template = DEFAULT_PROMPT_TEMPLATES["file_summary_system"]
    assert "JSON array" in template


def test_directory_summary_system_describes_fragment_contract() -> None:
    template = DEFAULT_PROMPT_TEMPLATES["directory_summary_system"]
    assert "ctx renders the ## Files and ## Subdirectories sections deterministically" in template
    assert "do not write those sections yourself" in template
    assert "## Notes" in template


def test_prompt_templates_discourage_boilerplate_directory_language() -> None:
    template = DEFAULT_PROMPT_TEMPLATES["directory_summary_system"]
    assert "Avoid boilerplate phrases like" in template
    assert "SKILL.md" in template


def test_all_templates_contain_injection_defence() -> None:
    # Every template should instruct the model to treat content as untrusted
    for key, template in DEFAULT_PROMPT_TEMPLATES.items():
        assert "untrusted" in template.lower(), (
            f"Template '{key}' is missing injection-defence language"
        )


# ---------------------------------------------------------------------------
# Smoke-test: templates render without error and produce valid placeholders
# ---------------------------------------------------------------------------

def test_file_summary_template_renders_with_payload() -> None:
    payload = json.dumps([{"name": "foo.py", "content": "x = 1", "language": "Python", "metadata": {}}])
    rendered = DEFAULT_PROMPT_TEMPLATES["file_summary"].format(json_payload=payload)
    assert "foo.py" in rendered


def test_directory_summary_template_renders_with_payload() -> None:
    payload = json.dumps({"path": "src", "files": [], "subdirs": []})
    rendered = DEFAULT_PROMPT_TEMPLATES["directory_summary"].format(json_payload=payload)
    assert "src" in rendered
