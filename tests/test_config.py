from snapcode import config


def test_legacy_data_moves_to_new_name(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    legacy = tmp_path / config.LEGACY_NAME
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"hotkey": "ctrl+alt+c"}', encoding="utf-8")

    path = config.data_dir()

    assert path == tmp_path / config.APP_NAME
    assert not legacy.exists()
    assert config.Settings.load().hotkey == "ctrl+alt+c"


def test_new_data_wins_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / config.LEGACY_NAME).mkdir()
    (tmp_path / config.APP_NAME).mkdir()
    config.data_dir()
    assert (tmp_path / config.LEGACY_NAME).exists()  # left alone, nothing overwritten
