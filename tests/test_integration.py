"""End-to-end CLI coverage on the sample fixture project."""

from __future__ import annotations

import shutil
from importlib import import_module
from pathlib import Path

from click.testing import CliRunner

from ctx.llm import FileSummary, LLMResult, SubdirSummary
from ctx.manifest import read_manifest


def _placeholder(label: str) -> str:
    return f"{label}-value"


class _EndToEndFakeClient:
    model = "e2e-llm-model"

    def summarize_files(self, dir_path: Path, files: list[dict]) -> list[LLMResult]:
        return [
            LLMResult(
                text=f"Summary for {f['name']}",
                input_tokens=3 if index == 0 else 0,
                output_tokens=1 if index == 0 else 0,
            )
            for index, f in enumerate(files)
        ]

    def summarize_directory(
        self,
        dir_path: Path,
        file_summaries: list[FileSummary],
        subdir_summaries: list[SubdirSummary],
    ) -> LLMResult:
        body_lines = [
            f"# {dir_path.as_posix()}",
            "",
            f"Summary for {dir_path.name or 'root'}.",
            "",
            "## Files",
        ]
        if file_summaries:
            body_lines.extend(f"- **{summary.name}** — {summary.summary}" for summary in file_summaries)
        else:
            body_lines.append("- None")

        body_lines.extend(["", "## Subdirectories"])
        if subdir_summaries:
            body_lines.extend(f"- **{summary.name}/** — {summary.summary}" for summary in subdir_summaries)
        else:
            body_lines.append("- None")

        body_lines.extend(["", "## Notes", "- Generated during end-to-end test"])
        return LLMResult(text="\n".join(body_lines) + "\n", input_tokens=5, output_tokens=2)


def _copy_sample_project(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "sample_project"
    destination = tmp_path / "sample_project"
    shutil.copytree(source, destination)
    return destination


def test_ctx_refresh_end_to_end_creates_manifests(monkeypatch, tmp_path) -> None:
    api_module = import_module("ctx.api")
    cli_module = import_module("ctx.cli")
    runner = CliRunner()
    root = _copy_sample_project(tmp_path)

    monkeypatch.setattr(api_module, "create_client", lambda config: _EndToEndFakeClient())
    monkeypatch.setattr(api_module, "probe_provider_connectivity", lambda *a, **kw: (True, None))

    result = runner.invoke(
        cli_module.cli,
        ["refresh", str(root), "--force"],
        env={"ANTHROPIC_API_KEY": _placeholder("anthropic")},
    )

    assert result.exit_code == 0, result.output
    assert "Directories refreshed:" in result.output
    assert "Files processed:" in result.output
    assert "Errors: 0" in result.output

    for directory in (root, root / "docs", root / "src"):
        manifest = read_manifest(directory)
        assert manifest is not None
        assert manifest.frontmatter.model == "e2e-llm-model"
        assert manifest.body.startswith(f"# {directory.as_posix()}")
