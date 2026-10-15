import json
from pathlib import Path

try:
    from smart_house_scale.addon_app.integration_installer import ensure_integration
except ModuleNotFoundError:
    from addon_app.integration_installer import ensure_integration


def _source_tree(tmp_path: Path, version: str = "0.1.4") -> Path:
    source = tmp_path / "source" / "smart_house_scale"
    source.mkdir(parents=True)
    (source / "manifest.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (source / "__init__.py").write_text("DOMAIN = 'smart_house_scale'\n", encoding="utf-8")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
    return source


def test_install_is_idempotent_and_managed_updates_are_safe(tmp_path: Path):
    config = tmp_path / "homeassistant"
    config.mkdir()
    source = _source_tree(tmp_path)

    installed = ensure_integration(config_dir=config, source_dir=source, app_version="0.3.0")
    target = config / "custom_components" / "smart_house_scale"
    assert installed.status == "installed"
    assert installed.restart_required is True
    assert (target / "__init__.py").exists()
    assert not (target / "__pycache__").exists()
    assert json.loads((target / ".smart_house_scale_app_managed.json").read_text())[
        "integration_version"
    ] == "0.1.4"

    already = ensure_integration(config_dir=config, source_dir=source, app_version="0.3.0")
    assert already.status == "already_managed"
    assert already.restart_required is False

    (source / "manifest.json").write_text(json.dumps({"version": "0.1.5"}), encoding="utf-8")
    (source / "__init__.py").write_text("DOMAIN = 'smart_house_scale'\nUPDATED = True\n", encoding="utf-8")
    updated = ensure_integration(config_dir=config, source_dir=source, app_version="0.3.1")
    assert updated.status == "updated"
    assert "UPDATED = True" in (target / "__init__.py").read_text(encoding="utf-8")


def test_external_hacs_installation_is_preserved(tmp_path: Path):
    config = tmp_path / "homeassistant"
    target = config / "custom_components" / "smart_house_scale"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("# managed elsewhere\n", encoding="utf-8")
    source = _source_tree(tmp_path)

    result = ensure_integration(config_dir=config, source_dir=source, app_version="0.3.0")

    assert result.status == "external_existing"
    assert result.restart_required is False
    assert (target / "__init__.py").read_text(encoding="utf-8") == "# managed elsewhere\n"


def test_missing_home_assistant_mount_is_non_fatal(tmp_path: Path):
    source = _source_tree(tmp_path)
    result = ensure_integration(config_dir=tmp_path / "not-mounted", source_dir=source)

    assert result.status == "config_unavailable"
    assert result.restart_required is False
