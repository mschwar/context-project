"""Tests for ctx.output OutputBroker."""

from __future__ import annotations

import json
import time

import click

from ctx import __version__
from ctx.output import OutputBroker


def _parse_single_envelope(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    return json.loads(lines[0])


def test_output_broker_passthrough_in_human_mode(capsys) -> None:
    with OutputBroker(command="check", json_mode=False):
        click.echo("hello")

    captured = capsys.readouterr()
    assert captured.out == "hello\n"


def test_output_broker_captures_stdout_in_json_mode(capsys) -> None:
    with OutputBroker(command="check", json_mode=True):
        click.echo("hello")

    captured = capsys.readouterr()
    envelope = _parse_single_envelope(captured.out)
    assert "hello" not in captured.out
    assert envelope["command"] == "check"


def test_output_broker_emits_valid_envelope(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.set_data({"mode": "health"})

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert set(envelope.keys()) == {
        "status",
        "command",
        "metadata",
        "data",
        "errors",
        "recommended_next",
    }
    assert isinstance(envelope["errors"], list)


def test_output_broker_success_status_when_no_errors(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.set_data({"ok": True})

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["status"] == "success"


def test_output_broker_error_status_when_errors_and_no_data(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.add_error("unknown_error", "boom")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["status"] == "error"


def test_output_broker_partial_status_with_data_and_errors(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.set_data({"mode": "health"})
        broker.add_error("stale_manifests", "stale")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["status"] == "partial"


def test_output_broker_handles_usage_error_exception(capsys) -> None:
    with OutputBroker(command="refresh", json_mode=True):
        raise click.UsageError("No LLM provider configured")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["status"] == "error"
    assert envelope["errors"][0]["code"] == "provider_not_configured"


def test_output_broker_handles_generic_runtime_exception(capsys) -> None:
    with OutputBroker(command="refresh", json_mode=True):
        raise RuntimeError("boom")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["status"] == "error"
    assert envelope["errors"][0]["code"] == "unknown_error"


def test_output_broker_metadata_fields(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.set_data({"ok": True})
        time.sleep(0.01)

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["metadata"]["version"] == __version__
    assert envelope["metadata"]["elapsed_ms"] > 0


def test_output_broker_set_tokens_sets_metadata(capsys) -> None:
    with OutputBroker(command="refresh", json_mode=True) as broker:
        broker.set_data({"dirs_processed": 1})
        broker.set_tokens(123, 0.456)

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["metadata"]["tokens_used"] == 123
    assert envelope["metadata"]["est_cost_usd"] == 0.456


def test_output_broker_supports_multiple_errors(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.add_error("unknown_error", "one")
        broker.add_error("unknown_error", "two")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert len(envelope["errors"]) == 2


def test_output_broker_recommended_next(capsys) -> None:
    with OutputBroker(command="check", json_mode=True) as broker:
        broker.set_data({"ok": True})
        broker.set_recommended_next("ctx check .")

    envelope = _parse_single_envelope(capsys.readouterr().out)
    assert envelope["recommended_next"] == "ctx check ."
