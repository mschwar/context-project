"""Zero-dependency stdlib documentation hygiene gate (UNSLOP anti-slop guardrails)."""

from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]

MAX_REPO_DOC_SENTENCE_WORDS: int = 45
MAX_README_TLDR_WORDS: int = 60

BANNED_JARGON_AND_FILLER: dict[str, str] = {
    "and/or": "state 'A or B' or 'A, B, or both'",
    "as appropriate": "state the exact condition",
    "if applicable": "state the exact condition",
    "etc.": "list all required items or state the exact category",
    "leverage": "use 'use'",
    "utilize": "use 'use'",
    "synergy": "state the specific interaction",
    "hopefully": "state the expected result or verification check",
    "more or less": "give the exact range or tolerance",
    "could possibly": "use 'can' or state the condition",
    "delve": "state the specific analysis action",
    "delve into": "use 'examine' or 'analyze'",
    "tapestry": "use literal domain nouns",
    "testament to": "state the concrete evidence directly",
    "it is important to note": "delete throat-clearing filler and state the point",
    "in today's fast-paced": "delete generic AI preamble",
    "paradigm shift": "describe the specific architectural or methodological change",
    "holistic approach": "name the concrete dimensions covered",
    "seamless integration": "specify the interface contract",
    "game-changer": "state the measurable effect",
    "cutting-edge": "state the specific technical capability",
}

COMMON_ACRONYMS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "API",
        "ASCII",
        "CLI",
        "CMS",
        "CPU",
        "CSS",
        "CSV",
        "DAG",
        "DNS",
        "DOCX",
        "DOM",
        "DPI",
        "FAQ",
        "GIT",
        "GPU",
        "GUI",
        "HTML",
        "HTTP",
        "HTTPS",
        "IDE",
        "IEC",
        "IETF",
        "ISBN",
        "ISO",
        "JSON",
        "JUNIT",
        "JWT",
        "LLM",
        "MAC",
        "MIT",
        "NIST",
        "OCR",
        "PDF",
        "PNG",
        "RAM",
        "REST",
        "RFC",
        "RGB",
        "SDK",
        "SHA",
        "SLO",
        "SOP",
        "SQL",
        "SSH",
        "SSL",
        "SVG",
        "TCP",
        "TLS",
        "TOML",
        "TSV",
        "UDP",
        "URI",
        "URL",
        "USA",
        "USB",
        "USD",
        "UTC",
        "UTF",
        "UUID",
        "WCAG",
        "WWW",
        "XML",
        "XSS",
        "YAML",
        "ZIP",
        "AGENTS",
        "BLOCKER",
        "DEMO",
        "DOCTYPE",
        "ERROR",
        "EST",
        "FAIL",
        "FALSE",
        "III",
        "INFO",
        "LICENSE",
        "MAJOR",
        "MAY",
        "MINOR",
        "MST",
        "MUST",
        "NEVER",
        "NONE",
        "NOT",
        "NOTE",
        "ONLY",
        "PASS",
        "PATCH",
        "PDT",
        "PST",
        "README",
        "REQUIRED",
        "SHALL",
        "SHOULD",
        "TBD",
        "TLDR",
        "TODO",
        "TRUE",
        "VII",
        "VIII",
        "WARN",
        "AAAS",
        "ADR",
        "APA",
        "ARES",
        "ASD",
        "ASES",
        "BMJ",
        "CDC",
        "DTCG",
        "FKGL",
        "GAO",
        "HAS",
        "JAMA",
        "JARS",
        "NAS",
        "NIH",
        "NNG",
        "PNAS",
        "SGCS",
        "STE",
        "SWCS",
        "UNSLOP",
    }
)

HUMAN_FACING_DOC_GLOBS: tuple[str, ...] = (
    "README.md",
    "CONTRIBUTING.md",
    "RUNBOOK.md",
    "architecture.md",
    "rules.md",
    "docs/benchmarks/*.md",
)

OPERATIONAL_DOC_GLOBS: tuple[str, ...] = (
    "AGENTS.md",
    "CLAUDE.md",
)

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]+\)")
_MD_LINK_TARGET_RE = re.compile(r"!?\[([^\]]*)\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://\S+")
_FILE_URI_RE = re.compile(r"\bfile://\S+", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_ACRONYM_TOKEN_RE = re.compile(r"\b([A-Z]{3,10})s?\b")
_RULE_ID_RE = re.compile(r"\b[A-Z]{2,12}-[A-Z0-9][A-Z0-9._-]*\b")
_FILENAME_TOKEN_RE = re.compile(
    r"\b[A-Za-z0-9_.-]+\.(?:md|markdown|txt|json|jsonl|yml|yaml|toml|rst|svg|html|css|py|sh|xml|pdf)\b"
)
_DOMAIN_BRAND_RE = re.compile(r"\bGOV\.UK\b")
_TLDR_HEADING_RE = re.compile(
    r"^(#{1,4})\s+(?:TL;DR|TLDR)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_code_and_links(text: str, *, code_placeholder: str = "code") -> str:
    s = _FENCED_CODE_RE.sub("\n", text)
    s = _HTML_COMMENT_RE.sub("\n", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _URL_RE.sub("", s)
    return _INLINE_CODE_RE.sub(code_placeholder, s)


def _count_prose_words(text: str) -> int:
    s = _strip_code_and_links(text, code_placeholder="code")
    total = 0
    for raw_line in s.splitlines():
        line = raw_line.strip()
        if not line or re.fullmatch(r"[\|\s:\-]+", line):
            continue
        line = re.sub(r"^(?:#{1,6}|>|\*|-|\+|\d+\.)\s+", "", line)
        line = line.replace("**", "").replace("*", "").replace("|", ". ")
        for chunk in re.split(r"[.!?]+(?:\s+|$)", line):
            total += len(_WORD_RE.findall(chunk))
    return total


def max_prose_sentence_words(text: str) -> int:
    s = _strip_code_and_links(text, code_placeholder="item")
    max_words = 0
    for raw_line in s.splitlines():
        line = raw_line.strip()
        if not line or re.fullmatch(r"[\|\s:\-]+", line) or line.startswith("|"):
            continue
        cleaned = re.sub(r"^(?:#{1,6}|>|\*|-|\+|\d+\.)\s+", "", line)
        cleaned = cleaned.replace("**", "").replace("*", "")
        for chunk in re.split(r"[.!?]+(?:\s+|$)", cleaned):
            words = _WORD_RE.findall(chunk)
            if words:
                max_words = max(max_words, len(words))
    return max_words


def check_banned_jargon(text: str, *, context: str = "prose") -> list[str]:
    s = _strip_code_and_links(text, code_placeholder="item")
    lowered = s.lower()
    errors: list[str] = []
    for term, guidance in BANNED_JARGON_AND_FILLER.items():
        if term.endswith("."):
            pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?=\s|$|[)\],;:])", re.IGNORECASE)
        else:
            pattern = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
        if pattern.search(lowered):
            errors.append(f"[LAN-009:JARGON] {context}: banned filler/ambiguous term {term!r} ({guidance})")
    return errors


def check_undefined_acronyms(
    text: str,
    *,
    context: str = "prose",
    extra_allowed: set[str] | None = None,
) -> list[str]:
    s = _strip_code_and_links(text, code_placeholder=" ")
    s = _FILENAME_TOKEN_RE.sub(" ", s)
    s = _DOMAIN_BRAND_RE.sub(" ", s)
    s = _RULE_ID_RE.sub(" ", s)

    allowed = set(COMMON_ACRONYMS_ALLOWLIST)
    if extra_allowed:
        allowed.update(extra_allowed)

    defined: set[str] = set()
    for m in re.finditer(r"[A-Za-z][A-Za-z\s/-]{2,}\(\s*([A-Z]{3,10})s?\s*\)", s):
        defined.add(m.group(1))
    for m in re.finditer(r"\b([A-Z]{3,10})\s*\([A-Za-z][A-Za-z\s/-]{3,}\)", s):
        defined.add(m.group(1))
    for m in re.finditer(r"(?:^|[\*\-\s])([A-Z]{3,10})\s*(?::|—|--)\s+[A-Za-z]", s, re.MULTILINE):
        defined.add(m.group(1))

    undefined_seen: list[str] = []
    for raw_line in s.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        alpha_chars = [ch for ch in stripped if ch.isalpha()]
        if alpha_chars and all(ch.isupper() for ch in alpha_chars) and len(alpha_chars) >= 8:
            continue
        for match in _ACRONYM_TOKEN_RE.finditer(stripped):
            acr = match.group(1)
            if acr in allowed or acr in defined or acr in undefined_seen:
                continue
            undefined_seen.append(acr)

    return [
        f"[LAN-003:ACRONYM] {context}: undefined acronym {acr!r}; expand at first use or replace with plain terms"
        for acr in undefined_seen
    ]


def extract_tldr_sections(markdown_text: str) -> list[str]:
    stripped = _FENCED_CODE_RE.sub("\n", markdown_text)
    matches = list(_TLDR_HEADING_RE.finditer(stripped))
    if not matches:
        return []
    sections: list[str] = []
    for m in matches:
        level = len(m.group(1))
        start = m.end()
        next_heading = re.search(rf"^#{{1,{level}}}\s+\S", stripped[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(stripped)
        body = stripped[start:end].strip()
        if body:
            sections.append(body)
    return sections


def markdown_heading_slugs(text: str) -> set[str]:
    stripped = _FENCED_CODE_RE.sub("\n", text)
    slugs: set[str] = set()
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", stripped, re.MULTILINE):
        raw = re.sub(r"[`*_~]", "", match.group(1)).strip().lower()
        collapsed = re.sub(r"\s+", "-", re.sub(r"[^a-z0-9\s-]", "", raw)).strip("-")
        gfm = re.sub(r"[^a-z0-9 -]", "", raw).replace(" ", "-").strip("-")
        if collapsed:
            slugs.add(collapsed)
        if gfm:
            slugs.add(gfm)
    return slugs


def check_markdown_links(markdown_text: str, *, source_file: Path, repo_root: Path = REPO_ROOT) -> list[str]:
    stripped = _FENCED_CODE_RE.sub("\n", markdown_text)
    stripped = _HTML_COMMENT_RE.sub("\n", stripped)
    stripped = _INLINE_CODE_RE.sub("code", stripped)

    errors: list[str] = []
    resolved_root = repo_root.resolve()
    rel_label = (
        str(source_file.resolve().relative_to(resolved_root))
        if source_file.resolve().is_relative_to(resolved_root)
        else str(source_file)
    )

    for _, raw_target in _MD_LINK_TARGET_RE.findall(stripped):
        target = raw_target.strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.lower().startswith("file://"):
            errors.append(f"[DOC-003:LINK] {rel_label}: machine-local file:// link {raw_target!r} is forbidden")
            continue
        if ' "' in target or " '" in target:
            target = target.split()[0]
        file_part, sep, fragment = target.partition("#")
        clean_file = unquote(file_part.split("?", 1)[0])
        dest = source_file.resolve() if not clean_file else (source_file.resolve().parent / clean_file).resolve()
        if not dest.is_relative_to(resolved_root):
            errors.append(f"[DOC-003:LINK] {rel_label}: link {raw_target!r} escapes repository root")
            continue
        if not dest.exists():
            errors.append(f"[DOC-003:LINK] {rel_label}: broken relative link {raw_target!r}")
            continue
        if sep == "#" and fragment and dest.is_file() and dest.suffix.lower() in (".md", ".markdown"):
            slugs = markdown_heading_slugs(dest.read_text(encoding="utf-8"))
            if unquote(fragment).lower() not in slugs:
                errors.append(
                    f"[DOC-003:LINK] {rel_label}: broken Markdown heading anchor #{fragment} in {raw_target!r}"
                )

    prose_without_links = _MD_LINK_RE.sub(" ", stripped)
    for file_uri in _FILE_URI_RE.findall(prose_without_links):
        errors.append(f"[DOC-003:LINK] {rel_label}: machine-local file:// link {file_uri!r} is forbidden")

    return errors


def _expand_doc_globs(repo_root: Path, patterns: tuple[str, ...]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for pat in patterns:
        for match in sorted(repo_root.glob(pat)):
            if not match.is_file() or match in seen:
                continue
            rel_parts = match.relative_to(repo_root).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            seen.add(match)
            ordered.append(match)
    return ordered


def audit_repo_docs(
    repo_root: Path = REPO_ROOT,
    *,
    human_globs: tuple[str, ...] = HUMAN_FACING_DOC_GLOBS,
    operational_globs: tuple[str, ...] = OPERATIONAL_DOC_GLOBS,
) -> list[str]:
    errors: list[str] = []
    readme_path = repo_root / "README.md"
    if not readme_path.is_file():
        errors.append("[DOC-001:TLDR] Missing repository README.md")
    else:
        raw_bytes = readme_path.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            errors.append("[DOC-001:TLDR] README.md must not start with a UTF-8 BOM")
        readme_text = raw_bytes.decode("utf-8-sig")
        tldrs = extract_tldr_sections(readme_text)
        if not tldrs:
            errors.append("[DOC-001:TLDR] README.md must include a '## TL;DR' section for human readers")
        else:
            tldr_words = _count_prose_words(tldrs[0])
            if tldr_words < 1 or tldr_words > MAX_README_TLDR_WORDS:
                errors.append(
                    f"[DOC-001:TLDR] README.md TL;DR has {tldr_words} words (must be 1..{MAX_README_TLDR_WORDS})"
                )

    human_docs = _expand_doc_globs(repo_root, human_globs)
    operational_docs = [p for p in _expand_doc_globs(repo_root, operational_globs) if p not in set(human_docs)]

    for doc_path in human_docs:
        rel = str(doc_path.relative_to(repo_root))
        text = doc_path.read_text(encoding="utf-8")
        errors.extend(check_banned_jargon(text, context=rel))
        errors.extend(check_undefined_acronyms(text, context=rel))
        longest = max_prose_sentence_words(text)
        if longest > MAX_REPO_DOC_SENTENCE_WORDS:
            errors.append(
                f"[DOC-002:RUNON] {rel}: longest sentence has {longest} words "
                f"(repository documentation max is {MAX_REPO_DOC_SENTENCE_WORDS})"
            )
        errors.extend(check_markdown_links(text, source_file=doc_path, repo_root=repo_root))

    for doc_path in operational_docs:
        rel = str(doc_path.relative_to(repo_root))
        text = doc_path.read_text(encoding="utf-8")
        errors.extend(check_banned_jargon(text, context=rel))
        errors.extend(check_markdown_links(text, source_file=doc_path, repo_root=repo_root))

    return errors


class TestDocHygiene(unittest.TestCase):
    """Enforce UNSLOP documentation hygiene across repository guides and adversarial fixtures."""

    def test_repository_docs_pass_hygiene_gate(self) -> None:
        errors = audit_repo_docs(REPO_ROOT)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_missing_or_oversized_tldr_and_bom_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo\n\nPlain body without summary.\n", encoding="utf-8")
            errs = audit_repo_docs(root)
            self.assertTrue(any("[DOC-001:TLDR]" in e for e in errs), errs)

            long_tldr = " ".join(["word"] * 65) + "."
            (root / "README.md").write_text(f"# Demo\n\n## TL;DR\n\n{long_tldr}\n", encoding="utf-8")
            errs_long = audit_repo_docs(root)
            self.assertTrue(any("[DOC-001:TLDR]" in e and "65 words" in e for e in errs_long), errs_long)

            (root / "README.md").write_bytes(b"\xef\xbb\xbf# Demo\n\n## TL;DR\n\nShort summary.\n")
            errs_bom = audit_repo_docs(root)
            self.assertTrue(any("[DOC-001:TLDR]" in e and "BOM" in e for e in errs_bom), errs_bom)

    def test_runon_sentence_over_45_words_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runon = " ".join(["clear"] * 47) + "."
            (root / "README.md").write_text(
                f"# Demo\n\n## TL;DR\n\nShort summary.\n\n## Details\n\n{runon}\n",
                encoding="utf-8",
            )
            errs = audit_repo_docs(root)
            self.assertTrue(any("[DOC-002:RUNON]" in e for e in errs), errs)

    def test_banned_jargon_fails_in_human_and_agent_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Demo\n\n## TL;DR\n\nWe leverage seamless integration to delve into data, etc.\n",
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "# AGENTS\n\nRun checks as appropriate and/or if applicable.\n",
                encoding="utf-8",
            )
            errs = audit_repo_docs(root)
            self.assertTrue(any("[LAN-009:JARGON] README.md" in e for e in errs), errs)
            self.assertTrue(any("[LAN-009:JARGON] AGENTS.md" in e for e in errs), errs)

    def test_undefined_acronym_fails_until_expanded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Demo\n\n## TL;DR\n\nParses AST nodes and serves MCP tools.\n",
                encoding="utf-8",
            )
            errs = audit_repo_docs(root)
            self.assertTrue(any("[LAN-003:ACRONYM]" in e and "'AST'" in e for e in errs), errs)
            self.assertTrue(any("[LAN-003:ACRONYM]" in e and "'MCP'" in e for e in errs), errs)

            (root / "README.md").write_text(
                "# Demo\n\n## TL;DR\n\nParses Abstract Syntax Tree (AST) nodes and serves Model Context Protocol (MCP) tools.\n",
                encoding="utf-8",
            )
            self.assertEqual(audit_repo_docs(root), [])

    def test_broken_links_anchors_and_file_uris_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONTRIBUTING.md").write_text(
                "# Contributing\n\n## Setup Steps\n\nRun tests locally.\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "# Demo\n\n## TL;DR\n\nShort summary.\n\n"
                "- [Missing](./missing.md)\n"
                "- [Bad Anchor](./CONTRIBUTING.md#nonexistent-heading)\n"
                "- [Escape](../outside.md)\n"
                "- [Local](file:///etc/passwd)\n",
                encoding="utf-8",
            )
            errs = audit_repo_docs(root)
            link_errs = [e for e in errs if "[DOC-003:LINK]" in e]
            self.assertEqual(len(link_errs), 4, link_errs)

            (root / "README.md").write_text(
                "# Demo\n\n## TL;DR\n\nShort summary.\n\n"
                "See [Setup Steps](./CONTRIBUTING.md#setup-steps).\n",
                encoding="utf-8",
            )
            self.assertEqual(audit_repo_docs(root), [])


if __name__ == "__main__":
    unittest.main()
