import pytest

from pluck import config


@pytest.mark.parametrize("legacy_name", config.LEGACY_NAMES)
def test_legacy_data_moves_to_new_name(tmp_path, monkeypatch, legacy_name):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    legacy = tmp_path / legacy_name
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"hotkey": "ctrl+alt+c"}', encoding="utf-8")

    path = config.data_dir()

    assert path == tmp_path / config.APP_NAME
    assert not legacy.exists()
    assert config.Settings.load().hotkey == "ctrl+alt+c"


def test_newest_legacy_name_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    newest, oldest = config.LEGACY_NAMES[0], config.LEGACY_NAMES[-1]
    (tmp_path / newest).mkdir()
    (tmp_path / oldest).mkdir()
    config.data_dir()
    assert not (tmp_path / newest).exists()
    assert (tmp_path / oldest).exists()


def test_new_data_wins_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    for name in config.LEGACY_NAMES:
        (tmp_path / name).mkdir()
    (tmp_path / config.APP_NAME).mkdir()
    config.data_dir()
    for name in config.LEGACY_NAMES:
        assert (tmp_path / name).exists()  # left alone, nothing overwritten
