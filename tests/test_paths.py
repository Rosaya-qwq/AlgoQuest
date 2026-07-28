from bot.services.paths import PROJECT_ROOT, runtime_data_dir


def test_runtime_data_dir_defaults_to_project_data(monkeypatch) -> None:
    monkeypatch.delenv("ALGOQUEST_DATA_DIR", raising=False)

    assert runtime_data_dir() == PROJECT_ROOT / "data"


def test_runtime_data_dir_can_be_overridden(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGOQUEST_DATA_DIR", str(tmp_path))

    assert runtime_data_dir() == tmp_path.resolve()
