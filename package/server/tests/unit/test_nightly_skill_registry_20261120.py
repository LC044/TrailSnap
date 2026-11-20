"""SKILL.md registry parsing and catalog exposure."""
import pytest

from app.service.agent.skills import registry

pytestmark = [pytest.mark.smoke, pytest.mark.module_agent]


def _write_skill(root, folder, content):
    directory = root / folder
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_reads_front_matter(tmp_path):
    path = _write_skill(
        tmp_path,
        "photo-tools",
        '---\nname: photo-tools\ndescription: "Photo tools"\n---\nBody text\n',
    )
    parsed = registry._parse(path)
    assert parsed["name"] == "photo-tools"
    assert parsed["description"] == "Photo tools"
    assert parsed["instructions"] == "Body text"


def test_parse_falls_back_to_directory_name(tmp_path):
    path = _write_skill(tmp_path, "plain-skill", "just body")
    parsed = registry._parse(path)
    assert parsed["name"] == "plain-skill"
    assert parsed["description"] == ""


def test_parse_rejects_invalid_skill_names(tmp_path):
    path = _write_skill(tmp_path, "Bad Name", "body")
    with pytest.raises(ValueError):
        registry._parse(path)


def test_parse_rejects_oversized_skill_files(tmp_path):
    path = _write_skill(tmp_path, "big", "x" * (registry._MAX_BYTES + 1))
    with pytest.raises(ValueError):
        registry._parse(path)


def test_catalog_lists_parsed_skills(tmp_path, monkeypatch):
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A\n---\nbody\n")
    _write_skill(tmp_path, "beta", "---\nname: beta\ndescription: B\n---\nbody\n")
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    registry._skills.cache_clear()
    try:
        catalog = registry.get_skill_catalog()
        assert {item["name"] for item in catalog} == {"alpha", "beta"}
        assert registry.load_skill("alpha")["description"] == "A"
        with pytest.raises(ValueError):
            registry.load_skill("missing")
    finally:
        registry._skills.cache_clear()


def test_load_skill_rejects_invalid_names():
    with pytest.raises(ValueError):
        registry.load_skill("Not A Name")
