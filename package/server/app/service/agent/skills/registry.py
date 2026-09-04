"""Small, allow-listed SKILL.md registry for the in-process LangGraph agent."""

from functools import lru_cache
from pathlib import Path
import re

_ROOT = Path(__file__).resolve().parent
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MAX_BYTES = 32 * 1024


def _parse(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Skill file is too large")
    name = path.parent.name
    description = ""
    if raw.startswith("---"):
        _, header, body = raw.split("---", 2)
        for line in header.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip() == "name":
                name = value.strip().strip('"\'')
            elif sep and key.strip() == "description":
                description = value.strip().strip('"\'')
    else:
        body = raw
    if not _NAME_RE.fullmatch(name):
        raise ValueError("Invalid skill name")
    return {"name": name, "description": description, "instructions": body.strip()}


@lru_cache(maxsize=1)
def _skills() -> dict[str, dict]:
    result = {}
    for path in sorted(_ROOT.glob("*/SKILL.md")):
        parsed = _parse(path)
        result[parsed["name"]] = parsed
    return result


def get_skill_catalog() -> list[dict[str, str]]:
    return [{"name": item["name"], "description": item["description"]} for item in _skills().values()]


def load_skill(name: str) -> dict:
    if not _NAME_RE.fullmatch(name):
        raise ValueError("Invalid skill name")
    skill = _skills().get(name)
    if not skill:
        raise ValueError(f"Unknown skill: {name}")
    return dict(skill)
