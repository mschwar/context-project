"""LLM client interface with Anthropic and OpenAI implementations.

The LLMClient protocol defines two methods:
- summarize_file(): given a file path and its content, return a one-line summary.
- summarize_directory(): given a directory path and child summaries, return a structured
  markdown body for the CONTEXT.md.

Both implementations should handle token counting and accumulate usage stats.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
        raise NotImplementedError

    def summarize_files(
        self, dir_path: Path, files: list[tuple[str, str]]
    ) -> list[LLMResult]:
        raise NotImplementedError

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        raise NotImplementedError


class OpenAIClient:
    """OpenAI implementation of LLMClient.

    Implementation:
        Same as AnthropicClient but using openai.OpenAI(api_key=...).
        - Use client.chat.completions.create() with the same prompt patterns.
        - Default model: gpt-4o-mini.
        - Track tokens from response.usage.prompt_tokens / completion_tokens.
    """

    def __init__(self, config: Config) -> None:
        raise NotImplementedError

    def summarize_files(
        self, dir_path: Path, files: list[tuple[str, str]]
    ) -> list[LLMResult]:
        raise NotImplementedError

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        raise NotImplementedError


def create_client(config: Config) -> AnthropicClient | OpenAIClient:
    """Factory: return the right client based on config.provider.

    Implementation:
        if config.provider == "anthropic": return AnthropicClient(config)
        elif config.provider == "openai": return OpenAIClient(config)
        else: raise click.UsageError(f"Unknown provider: {config.provider}")
    """
    raise NotImplementedError
