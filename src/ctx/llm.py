"""LLM client interface with Anthropic and OpenAI implementations.

The LLMClient protocol defines two methods:
- summarize_file(): given a file path and its content, return a one-line summary.
- summarize_directory(): given a directory path and child summaries, return a structured
  markdown body for the CONTEXT.md.

Both implementations should handle token counting and accumulate usage stats.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import click
from anthropic import Anthropic
from openai import OpenAI

from ctx.config import Config


@dataclass
class LLMResult:
    """Result from an LLM call."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FileSummary:
    """Summary info for a single file, used as input to summarize_directory."""

    name: str
    summary: str  # One-line summary or "[binary: type, size]"
    is_binary: bool = False


@dataclass
class SubdirSummary:
    """Summary info for a subdirectory, used as input to summarize_directory."""

    name: str
    summary: str  # One-line purpose from child CONTEXT.md


class LLMClient(Protocol):
    """Protocol for LLM provider implementations."""

    def summarize_files(
        self,
        dir_path: Path,
        files: list[tuple[str, str]],
    ) -> list[LLMResult]:
        """Summarize multiple files in a single LLM call.

        Args:
            dir_path: Path to the directory containing these files.
            files: List of (filename, content) tuples. Content is already
                   truncated to max_file_tokens. Binary files are excluded
                   (handled separately by the generator).

        Returns:
            List of LLMResult, one per file, in the same order as input.

        Prompt guidance:
            Send all files in one message. Ask for a JSON array of one-line
            summaries, one per file, in input order. Parse the response.
            If a file is too short or trivial (e.g., __init__.py with just
            a version string), the summary can be very brief.
        """
        ...

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        """Generate the markdown body for a directory's CONTEXT.md.

        Args:
            dir_path: Absolute path to the directory.
            file_summaries: Summaries for each file in this directory.
            subdir_summaries: Summaries for each subdirectory.

        Returns:
            LLMResult whose text is the full markdown body:
                # /relative/path
                One-line purpose.
                ## Files
                - **name** — summary
                ## Subdirectories
                - **name/** — summary
                ## Notes (optional)

        Prompt guidance:
            Provide the dir path, file summaries, and subdir summaries.
            Ask the LLM to write the markdown body following the exact format.
            The LLM should infer the directory's purpose from its contents.
        """
        ...


def _collapse_to_one_line(text: str) -> str:
    return " ".join(text.split())


def _extract_json_array(text: str) -> list[str]:
    payload: object
    stripped = text.strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", stripped)
        if match is None:
            raise ValueError("LLM response did not contain a JSON array.") from None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError("LLM response contained a malformed JSON array.") from e

    if not isinstance(payload, list):
        raise ValueError("LLM response was not a JSON array.")

    summaries: list[str] = []
    for item in payload:
        if isinstance(item, str):
            summaries.append(_collapse_to_one_line(item))
            continue
        if isinstance(item, dict) and isinstance(item.get("summary"), str):
            summaries.append(_collapse_to_one_line(item["summary"]))
            continue
        raise ValueError("LLM summary array must contain strings.")

    return summaries


def _extract_anthropic_text(response: object) -> str:
    content = getattr(response, "content", [])
    parts = [getattr(block, "text", "") for block in content if getattr(block, "text", "")]
    return "\n".join(parts).strip()


def _extract_openai_text(response: object) -> str:
    choices = getattr(response, "choices", [])
    if not choices:
        return ""

    content = getattr(getattr(choices[0], "message", None), "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
                continue
            text = getattr(item, "text", "")
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _format_files_prompt(dir_path: Path, files: list[tuple[str, str]]) -> str:
    lines = [
        f"Directory: {dir_path.as_posix()}",
        f"Return a JSON array of exactly {len(files)} one-line summaries in the same order as the files below.",
        "Each summary must be concise and must not include markdown bullets or numbering.",
        "",
    ]
    for index, (name, content) in enumerate(files, start=1):
        lines.extend(
            [
                f"<file index=\"{index}\" name=\"{name}\">",
                content,
                "</file>",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _format_directory_prompt(
    dir_path: Path,
    file_summaries: list[FileSummary],
    subdir_summaries: list[SubdirSummary],
) -> str:
    lines = [
        f"Write the CONTEXT.md markdown body for directory: {dir_path.as_posix()}",
        "Return only markdown.",
        "Use this exact structure:",
        f"# {dir_path.as_posix()}",
        "",
        "One-line purpose.",
        "",
        "## Files",
        "- **name** — summary",
        "",
        "## Subdirectories",
        "- **name/** — summary",
        "",
        "## Notes",
        "- optional hints",
        "",
        "If a section has no entries, include the heading and write '- None'.",
        "",
        "File summaries:",
    ]

    if file_summaries:
        lines.extend(f"- {summary.name}: {summary.summary}" for summary in file_summaries)
    else:
        lines.append("- None")

    lines.extend(["", "Subdirectory summaries:"])
    if subdir_summaries:
        lines.extend(f"- {summary.name}/: {summary.summary}" for summary in subdir_summaries)
    else:
        lines.append("- None")

    return "\n".join(lines)


def _build_batch_results(
    summaries: list[str],
    input_tokens: int,
    output_tokens: int,
) -> list[LLMResult]:
    if not summaries:
        return []

    results = [LLMResult(text=summaries[0], input_tokens=input_tokens, output_tokens=output_tokens)]
    results.extend(LLMResult(text=summary) for summary in summaries[1:])
    return results


class AnthropicClient:
    """Anthropic (Claude) implementation of LLMClient.

    Implementation:
        1. __init__(config: Config): store config, create anthropic.Anthropic(api_key=...).
        2. summarize_files(): build a message asking Claude to summarize files.
           - System prompt: "You summarize files for a directory manifest. Return a JSON
             array of one-line summaries, one per file."
           - User message: list files with their contents.
           - Parse JSON array from response.
           - Track input/output tokens from response.usage.
        3. summarize_directory(): build a message asking Claude to write the CONTEXT.md body.
           - System prompt: "You write structured directory summaries in markdown format."
           - User message: provide dir path, file summaries, subdir summaries, and the
             exact output format expected.
           - Return raw text (it IS the markdown body).
           - Track tokens.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.model = config.model.strip() or Config.__dataclass_fields__["model"].default
        self.config.model = self.model
        self.client = Anthropic(api_key=config.api_key)

    def summarize_files(
        self, dir_path: Path, files: list[tuple[str, str]]
    ) -> list[LLMResult]:
        if not files:
            return []

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=0,
            system=(
                "You summarize files for a directory manifest. "
                "Return only a JSON array of one-line summaries, one per file."
            ),
            messages=[
                {
                    "role": "user",
                    "content": _format_files_prompt(dir_path, files),
                }
            ],
        )
        text = _extract_anthropic_text(response)
        summaries = _extract_json_array(text)
        if len(summaries) != len(files):
            raise ValueError("Anthropic returned the wrong number of file summaries.")

        input_tokens = int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0)
        output_tokens = int(getattr(getattr(response, "usage", None), "output_tokens", 0) or 0)
        self.config.tokens_used += input_tokens + output_tokens
        return _build_batch_results(summaries, input_tokens, output_tokens)

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=0,
            system="You write structured directory summaries in markdown format.",
            messages=[
                {
                    "role": "user",
                    "content": _format_directory_prompt(
                        dir_path,
                        file_summaries,
                        subdir_summaries,
                    ),
                }
            ],
        )
        text = _extract_anthropic_text(response)
        input_tokens = int(getattr(getattr(response, "usage", None), "input_tokens", 0) or 0)
        output_tokens = int(getattr(getattr(response, "usage", None), "output_tokens", 0) or 0)
        self.config.tokens_used += input_tokens + output_tokens
        return LLMResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


class OpenAIClient:
    """OpenAI implementation of LLMClient.

    Implementation:
        Same as AnthropicClient but using openai.OpenAI(api_key=...).
        - Use client.chat.completions.create() with the same prompt patterns.
        - Default model: gpt-4o-mini.
        - Track tokens from response.usage.prompt_tokens / completion_tokens.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.model = config.model.strip() if config.model else ""
        if not self.model or self.model == Config.__dataclass_fields__["model"].default:
            self.model = "gpt-4o-mini"
        self.config.model = self.model
        self.client = OpenAI(api_key=config.api_key)

    def summarize_files(
        self, dir_path: Path, files: list[tuple[str, str]]
    ) -> list[LLMResult]:
        if not files:
            return []

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_completion_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize files for a directory manifest. "
                        "Return only a JSON array of one-line summaries, one per file."
                    ),
                },
                {
                    "role": "user",
                    "content": _format_files_prompt(dir_path, files),
                },
            ],
        )
        text = _extract_openai_text(response)
        summaries = _extract_json_array(text)
        if len(summaries) != len(files):
            raise ValueError("OpenAI returned the wrong number of file summaries.")

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        self.config.tokens_used += input_tokens + output_tokens
        return _build_batch_results(summaries, input_tokens, output_tokens)

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_completion_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": "You write structured directory summaries in markdown format.",
                },
                {
                    "role": "user",
                    "content": _format_directory_prompt(
                        dir_path,
                        file_summaries,
                        subdir_summaries,
                    ),
                },
            ],
        )
        text = _extract_openai_text(response)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        self.config.tokens_used += input_tokens + output_tokens
        return LLMResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


def create_client(config: Config) -> AnthropicClient | OpenAIClient:
    """Factory: return the right client based on config.provider.

    Implementation:
        if config.provider == "anthropic": return AnthropicClient(config)
        elif config.provider == "openai": return OpenAIClient(config)
        else: raise click.UsageError(f"Unknown provider: {config.provider}")
    """
    if config.provider == "anthropic":
        return AnthropicClient(config)
    if config.provider == "openai":
        return OpenAIClient(config)
    raise click.UsageError(f"Unknown provider: {config.provider}")
