from app.services import whatsnew

SAMPLE = """# Changelog

## 2026.01.16

- Fixed a race
- Added a thing
  - nested detail

## 2026.01.09

## 2025.12.29

- Older change
"""


def test_parse_headings_and_bullets():
    entries = whatsnew.parse_changelog(SAMPLE)
    assert entries[0][0] == "2026.01.16"
    assert entries[0][1] == ["Fixed a race", "Added a thing", "nested detail"]
    assert entries[-1] == ("2025.12.29", ["Older change"])


def test_current_version_is_first_heading():
    entries = whatsnew.parse_changelog(SAMPLE)
    assert whatsnew.current_version(entries) == "2026.01.16"


def test_unseen_filters_older_and_empty():
    entries = whatsnew.parse_changelog(SAMPLE)
    unseen = whatsnew.unseen_entries(entries, "2026.01.09")
    assert unseen == [("2026.01.16", ["Fixed a race", "Added a thing", "nested detail"])]
    assert whatsnew.unseen_entries(entries, "2026.01.16") == []
    assert whatsnew.unseen_entries([], "") == []


def test_changelog_path_finds_repo_root():
    path = whatsnew.changelog_path()
    assert path is not None and path.name == "CHANGELOG.md"
    assert path.read_text(encoding="utf-8").lstrip().startswith("# Changelog")
