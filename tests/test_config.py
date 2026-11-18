"""Settings load from defaults and from a .env file without needing secrets."""

from repo_doctor.config import Settings


def test_settings_have_sane_defaults():
    settings = Settings(_env_file=None)

    assert isinstance(settings.max_steps, int) and settings.max_steps > 0
    assert isinstance(settings.max_context_tokens, int) and settings.max_context_tokens > 0
    assert settings.workspace_dir


def test_settings_read_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MAX_STEPS=3\nMAX_CONTEXT_TOKENS=1234\n", encoding="utf-8")

    settings = Settings(_env_file=str(env_file))

    assert settings.max_steps == 3
    assert settings.max_context_tokens == 1234
