import stat

from steam_playtime.config import load_settings


def test_creates_private_toml_configuration(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("STEAM_PLAYTIME_CONFIG", str(path))
    monkeypatch.setenv("STEAM_PLAYTIME_DATA_DIR", str(tmp_path / "data"))

    settings = load_settings()

    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert settings.device_id
    assert settings.api_token
    assert "[agent]" in path.read_text()
