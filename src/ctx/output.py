"""Structured output broker for ctx CLI commands."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import TextIO

import click

from ctx import __version__
from ctx.api import ConfirmationRequiredError
from ctx.config import MissingApiKeyError
from ctx.llm import TRANSIENT_ERROR_PREFIX
from ctx.lock import LockHeldError


def _determine_status(data: dict, errors: list[dict[str, str | None]]) -> str:
    if not errors:
        return "success"
    if not data or data == {}:
        return "error"
    return "partial"


def _classify_exception(exc: BaseException) -> tuple[str, str, str | None]:
    if isinstance(exc, ConfirmationRequiredError):
        return ("confirmation_required", str(exc), "Re-run with --yes.")
    if isinstance(exc, LockHeldError):
        return ("lock_held", str(exc), "Wait and retry, or check for stuck processes.")
    if isinstance(exc, MissingApiKeyError):
        return ("provider_not_configured", str(exc), "Run ctx refresh --setup")
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return ("provider_unreachable", str(exc), "Check network or run ctx refresh . --setup --dry-run")
    if isinstance(exc, RuntimeError) and TRANSIENT_ERROR_PREFIX in str(exc):
        return ("provider_unreachable", str(exc), "Retry the command")
    if isinstance(exc, click.UsageError):
        message = str(exc)
        if "No LLM provider" in message:
            return ("provider_not_configured", message, "Run ctx refresh --setup")
        if "Missing required environment variable" in message:
            return (
                "provider_not_configured",
                message,
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY",
            )
        return ("unknown_error", message, None)
    if isinstance(exc, Exception):
        return ("unknown_error", str(exc), None)
    return ("unknown_error", repr(exc), None)


def build_envelope(
    *,
    command: str,
    elapsed_ms: int,
    data: dict,
    errors: list[dict[str, str | None]],
    tokens_used: int = 0,
    est_cost_usd: float = 0.0,
    recommended_next: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    return {
        "status": status or _determine_status(data, errors),
        "command": command,
        "metadata": {
            "version": __version__,
            "elapsed_ms": elapsed_ms,
            "tokens_used": tokens_used,
            "est_cost_usd": est_cost_usd,
        },
        "data": data,
        "errors": errors,
        "recommended_next": recommended_next,
    }


@dataclass
class OutputBroker:
    """Context manager that captures output and emits one JSON envelope."""

    command: str
    json_mode: bool = False
    data: dict = field(default_factory=dict)
    errors: list[dict[str, str | None]] = field(default_factory=list)
    recommended_next: str | None = None
    tokens_used: int = 0
    est_cost_usd: float = 0.0
    handled_exception: bool = False
    _start_time: float = 0.0
    _real_stdout: TextIO | None = None
    _real_stderr: TextIO | None = None

    def set_data(self, data: dict) -> None:
        self.data = data

    def add_error(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        path: str | None = None,
    ) -> None:
        self.errors.append(
            {
                "code": code,
                "message": message,
                "hint": hint,
                "path": path,
            }
        )

    def set_recommended_next(self, command: str | None) -> None:
        self.recommended_next = command

    def set_tokens(self, tokens: int, cost: float) -> None:
        self.tokens_used = tokens
        self.est_cost_usd = cost

    def __enter__(self) -> "OutputBroker":
        self._start_time = time.time()
        if self.json_mode:
            self._real_stdout = sys.stdout
            self._real_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: object | None,
    ) -> bool:
        elapsed_ms = int((time.time() - self._start_time) * 1000)

        if exc is not None and self.json_mode:
            code, message, hint = _classify_exception(exc)
            self.add_error(code, message, hint=hint)
            self.handled_exception = True

        if self.json_mode:
            if self._real_stdout is not None:
                sys.stdout = self._real_stdout
            if self._real_stderr is not None:
                sys.stderr = self._real_stderr
            envelope = build_envelope(
                command=self.command,
                elapsed_ms=elapsed_ms,
                data=self.data,
                errors=self.errors,
                tokens_used=self.tokens_used,
                est_cost_usd=self.est_cost_usd,
                recommended_next=self.recommended_next,
            )
            assert self._real_stdout is not None
            self._real_stdout.write(json.dumps(envelope) + "\n")
            self._real_stdout.flush()

        if self.json_mode and exc is not None:
            return True
        return False
