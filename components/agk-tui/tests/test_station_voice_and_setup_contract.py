from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "hermes" / "plugins" / "platforms" / "discord" / "adapter.py"


def test_discord_setup_uses_ephemeral_tailnet_button_and_never_chat_secret():
    source = ADAPTER.read_text(encoding="utf-8")
    assert "_create_station_guided_setup_link" in source
    assert 'style=discord.ButtonStyle.link' in source
    assert "ephemeral=True" in source
    assert "No secret is accepted in Discord messages." in source
    assert '"station-secret"' in source


def test_discord_audio_uses_openai_primary_then_local_parakeet_failover():
    source = ADAPTER.read_text(encoding="utf-8")
    primary = source.index('transcribe_audio, wav_path, source="discord"')
    fallback = source.index("_transcribe_with_station_parakeet, wav_path")
    assert primary < fallback
    assert "/usr/local/libexec/station-parakeet-transcribe" in source
