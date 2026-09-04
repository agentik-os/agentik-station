from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installer_keeps_the_user_agk_launcher_authoritative():
    source = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "expose_agk_launcher" in source
    assert ".agk-shadowed" in source
    assert 'ln -s "$installed" "$shadow"' in source


def test_doctor_only_requires_nous_auth_when_nous_is_selected():
    source = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")

    assert "portal_ready_for_selected_provider" in source
    assert '[ "$provider" != nous ] || portal_authenticated' in source


def test_shared_hermes_install_preserves_required_provider_extras():
    source = (ROOT / "scripts" / "install-shared-hermes.sh").read_text(
        encoding="utf-8"
    )

    assert "'anthropic==0.87.0'" in source
    assert "'discord.py[voice]==2.7.1'" in source


def test_discord_model_picker_paginates_beyond_the_first_25_models():
    source = (
        ROOT / "hermes/plugins/platforms/discord/adapter.py"
    ).read_text(encoding="utf-8")

    assert "self._model_page" in source
    assert 'custom_id="model_page_next"' in source
    assert "models[start:start + page_size]" in source
