import re
from pathlib import Path

from ..errors import SpecParseError
from ..models import ExpectedScope, SpecModel

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(?P<item>.+?)\s*$")
_SECTION_ALIASES = {
    "goal": "goal",
    "goals": "goal",
    "acceptancecriteria": "acceptance_criteria",
    "acceptancecriterion": "acceptance_criteria",
    "criteria": "acceptance_criteria",
    "criterion": "acceptance_criteria",
    "outofscope": "out_of_scope",
    "riskareas": "risk_areas",
    "riskarea": "risk_areas",
    "risks": "risk_areas",
    "risk": "risk_areas",
    "expectedscope": "expected_scope",
    "scope": "expected_scope",
}
_SCOPE_ALIASES = {
    "smallbugfix": ExpectedScope.SMALL_BUGFIX,
    "bugfix": ExpectedScope.SMALL_BUGFIX,
    "mediumchange": ExpectedScope.MEDIUM_CHANGE,
    "largechange": ExpectedScope.LARGE_CHANGE,
    "unknown": ExpectedScope.UNKNOWN,
}


def parse_spec_text(text: str, source_path: str | None = None) -> SpecModel:
    sections = _split_sections(text)
    return SpecModel(
        source_path=source_path,
        goal=_paragraph(sections.get("goal", [])),
        acceptance_criteria=_items(sections.get("acceptance_criteria", [])),
        out_of_scope=_items(sections.get("out_of_scope", [])),
        risk_areas=_items(sections.get("risk_areas", [])),
        expected_scope=_expected_scope(sections.get("expected_scope", [])),
    )


def parse_spec_file(path: str | Path) -> SpecModel:
    spec_path = Path(path)
    try:
        return parse_spec_text(spec_path.read_text(encoding="utf-8"), source_path=str(spec_path))
    except OSError as exc:
        raise SpecParseError(f"Unable to read spec file: {spec_path}") from exc


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _heading_key(line)
        if heading is not None:
            current = heading
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def _heading_key(line: str) -> str | None:
    match = _HEADING_RE.match(line)
    if not match:
        return None
    return _SECTION_ALIASES.get(re.sub(r"[^a-z0-9]", "", match.group("title").lower()))


def _items(lines: list[str]) -> list[str]:
    bullet_items = [
        match.group("item").strip() for line in lines if (match := _BULLET_RE.match(line))
    ]
    if bullet_items:
        return [item for item in bullet_items if item]
    return [line.strip() for line in lines if line.strip()]


def _paragraph(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            match = _BULLET_RE.match(stripped)
            parts.append(match.group("item") if match else stripped)
    return " ".join(parts).strip()


def _expected_scope(lines: list[str]) -> ExpectedScope:
    key = re.sub(r"[^a-z0-9]", "", " ".join(_items(lines)).strip().lower())
    return _SCOPE_ALIASES.get(key, ExpectedScope.UNKNOWN)
