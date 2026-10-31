from app.services import whatsnew

SAMPLE = """# Changelog

## [Unreleased]

### Added

- unreleased work in progress

## [v26.10.31.1] - 2026-10-31

### Fixed

- Fixed a race
- Added a thing
  - nested detail

## [v26.10.30.2] - 2026-10-30

## [v26.10.30.1] - 2026-10-30

### Added

- Older change
"""


def test_parse_headings_and_bullets():
    entries = whatsnew.parse_changelog(SAMPLE)
    assert [v for v, _ in entries] == ["v26.10.31.1", "v26.10.30.2", "v26.10.30.1"]
    assert entries[0][1] == ["Fixed a race", "Added a thing", "nested detail"]
    assert entries[-1] == ("v26.10.30.1", ["Older change"])


def test_unreleased_is_not_a_version():
    entries = whatsnew.parse_changelog(SAMPLE)
    assert whatsnew.current_version(entries) == "v26.10.31.1"


def test_unseen_filters_older_and_empty():
    entries = whatsnew.parse_changelog(SAMPLE)
    unseen = whatsnew.unseen_entries(entries, "v26.10.30.2")
    assert unseen == [
        ("v26.10.31.1", ["Fixed a race", "Added a thing", "nested detail"])
    ]
    assert whatsnew.unseen_entries(entries, "v26.10.31.1") == []
    assert whatsnew.unseen_entries([], "") == []


def test_version_compare_is_numeric_per_segment():
    entries = [("v26.10.31.10", ["ten"]), ("v26.10.31.2", ["two"])]
    assert whatsnew.unseen_entries(entries, "v26.10.31.2") == [
        ("v26.10.31.10", ["ten"])
    ]


def test_changelog_path_finds_repo_root_and_parses():
    path = whatsnew.changelog_path()
    assert path is not None and path.name == "CHANGELOG.md"
    entries = whatsnew.parse_changelog(path.read_text(encoding="utf-8"))
    assert entries, "the real CHANGELOG.md must yield at least one entry"
    assert all(v.startswith("v") for v, _ in entries)
