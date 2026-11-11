"""Lightweight zero-dependency SDK for .ctx/ consumers.

Provides typed read-only access to pre-compiled .ctx/ structural maps and metadata.json
without importing Click or FastAPI.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


class CtxProjectNotFoundError(FileNotFoundError):
    """Raised when no .ctx/ directory can be found for a target path."""


@dataclass(frozen=True)
class CtxMetadata:
    """Typed representation of .ctx/metadata.json."""

    schema_version: int = 1
    initialized_at: str = ""
    initialized_by: str = ""
    ctx_version: str = ""
    repo_id: str = ""
    last_refresh: str = ""
    python_executable: str = ""
    hooks_installed: list[str] = field(default_factory=list)
    mode: str = "tier2"
    structural_hash: str | None = None
    boundary_doc_hash: str | None = None


@dataclass(frozen=True)
class CtxProject:
    """Read-only handle to a repository's .ctx/ directory."""

    root: Path
    ctx_dir: Path

    @classmethod
    def load(cls, path: str | Path = ".", *, walk_parents: bool = True) -> "CtxProject":
        """Locate and load a .ctx/ directory from *path* or its ancestors."""
        target = Path(path).resolve()
        start_dir = target if target.is_dir() else target.parent
        candidates = [start_dir, *start_dir.parents] if walk_parents else [start_dir]

        for directory in candidates:
            ctx_dir = directory / ".ctx"
            if (ctx_dir / "metadata.json").is_file():
                return cls(root=directory, ctx_dir=ctx_dir)

        raise CtxProjectNotFoundError(
            f"No .ctx/ directory found for {target}. Run 'ctx init' first."
        )

    @property
    def metadata(self) -> CtxMetadata:
        meta_path = self.ctx_dir / "metadata.json"
        if not meta_path.is_file():
            return CtxMetadata()
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return CtxMetadata()
        if not isinstance(raw, dict):
            return CtxMetadata()

        hooks = raw.get("hooks_installed", [])
        return CtxMetadata(
            schema_version=int(raw.get("schema_version", 1)),
            initialized_at=str(raw.get("initialized_at", "")),
            initialized_by=str(raw.get("initialized_by", "")),
            ctx_version=str(raw.get("ctx_version", "")),
            repo_id=str(raw.get("repo_id", "")),
            last_refresh=str(raw.get("last_refresh", "")),
            python_executable=str(raw.get("python_executable", "")),
            hooks_installed=[str(h) for h in hooks] if isinstance(hooks, list) else [],
            mode=str(raw.get("mode", "tier2")),
            structural_hash=raw.get("structural_hash"),
            boundary_doc_hash=raw.get("boundary_doc_hash"),
        )

    def get_export(self, depth: int | None = None) -> str:
        """Return the pre-compiled export at *depth* (None=full, 1=depth-1, 0=root)."""
        filename_map: dict[int | None, str] = {
            None: "CONTEXT.md",
            1: "CONTEXT-1.md",
            0: "CONTEXT-0.md",
        }
        if depth not in filename_map:
            raise ValueError(f"Unsupported export depth tier: {depth}. Expected None, 1, or 0.")
        target_file = self.ctx_dir / filename_map[depth]
        if not target_file.is_file():
            raise FileNotFoundError(f"Export tier file not found: {target_file}")
        return target_file.read_text(encoding="utf-8")

    def get_context(self, depth: int | None = None) -> str:
        """Alias for get_export(depth) returning the pre-compiled export tier."""
        return self.get_export(depth)

    def is_stale(self) -> bool:
        """Return True if .ctx/ structural or boundary-doc maps are stale or missing."""
        tier_names = ("CONTEXT.md", "CONTEXT-1.md", "CONTEXT-0.md")
        for tier_name in tier_names:
            tier_path = self.ctx_dir / tier_name
            try:
                if not tier_path.is_file() or tier_path.stat().st_size == 0:
                    return True
            except OSError:
                return True

        meta = self.metadata
        if not meta.structural_hash or not meta.boundary_doc_hash:
            return True
        for tier_name in tier_names:
            try:
                content = (self.ctx_dir / tier_name).read_text(encoding="utf-8")
            except OSError:
                return True
            if meta.structural_hash not in content or meta.boundary_doc_hash not in content:
                return True
        try:
            from ctx.skeleton import extract_skeleton, should_invoke_llm
        except ImportError:
            return False

        skeleton = extract_skeleton(self.root)
        return should_invoke_llm(
            {
                "structural_hash": meta.structural_hash,
                "boundary_doc_hash": meta.boundary_doc_hash,
            },
            skeleton,
        )

    @property
    def context_full(self) -> str:
        return self.get_export(None)

    @property
    def context_depth_1(self) -> str:
        return self.get_export(1)

    @property
    def context_depth_0(self) -> str:
        return self.get_export(0)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of metadata and available tiers."""
        available_tiers: dict[str, bool] = {
            "CONTEXT.md": (self.ctx_dir / "CONTEXT.md").is_file(),
            "CONTEXT-1.md": (self.ctx_dir / "CONTEXT-1.md").is_file(),
            "CONTEXT-0.md": (self.ctx_dir / "CONTEXT-0.md").is_file(),
        }
        return {
            "root": str(self.root),
            "ctx_dir": str(self.ctx_dir),
            "metadata": asdict(self.metadata),
            "available_tiers": available_tiers,
        }
