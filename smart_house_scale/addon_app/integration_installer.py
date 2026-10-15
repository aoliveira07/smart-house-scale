"""Install the bundled Home Assistant integration during App bootstrap.

The App and the Home Assistant integration have different runtimes.  The App
is installed by Supervisor, while the integration must live in Home
Assistant's ``custom_components`` directory.  Home Assistant has no supported
Supervisor endpoint for installing an arbitrary HACS repository, so the App
ships the reviewed integration and performs an idempotent bootstrap copy.

An existing integration that was installed by HACS is never overwritten.  A
marker is written only for copies managed by this App; future App upgrades can
then update those copies safely.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

_LOGGER = logging.getLogger(__name__)

DOMAIN = "smart_house_scale"
MARKER_FILENAME = ".smart_house_scale_app_managed.json"
DEFAULT_CONFIG_DIR = "/homeassistant"
DEFAULT_SOURCE_DIR = "/opt/smart_house_scale/custom_components/smart_house_scale"


@dataclass(frozen=True)
class IntegrationInstallResult:
    status: str
    version: str | None
    target: str
    restart_required: bool
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "version": self.version,
            "target": self.target,
            "restart_required": self.restart_required,
            "message": self.message,
        }


def _read_version(source_dir: Path) -> str | None:
    manifest = source_dir / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        _LOGGER.error("Smart House Scale integration manifest is unavailable: %s", type(exc).__name__)
        return None
    version = data.get("version")
    return str(version) if version else None


def _read_marker(target_dir: Path) -> dict[str, object] | None:
    try:
        value = json.loads((target_dir / MARKER_FILENAME).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _copy_integration(source_dir: Path, target_dir: Path, *, version: str, app_version: str) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = target_dir.parent / f".{DOMAIN}.install-{uuid4().hex}"
    backup_dir: Path | None = None
    try:
        shutil.copytree(
            source_dir,
            staging_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", MARKER_FILENAME),
        )
        marker = {
            "managed_by": "smart-house-scale-app",
            "app_version": app_version,
            "integration_version": version,
        }
        (staging_dir / MARKER_FILENAME).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if target_dir.exists():
            backup_dir = target_dir.parent / f".{DOMAIN}.backup-{uuid4().hex}"
            target_dir.rename(backup_dir)
        staging_dir.rename(target_dir)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        if backup_dir and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def ensure_integration(
    *,
    config_dir: str | os.PathLike[str] = DEFAULT_CONFIG_DIR,
    source_dir: str | os.PathLike[str] = DEFAULT_SOURCE_DIR,
    app_version: str = "unknown",
) -> IntegrationInstallResult:
    """Ensure the bundled integration is available to Home Assistant.

    The function is deliberately synchronous so it can be unit tested without
    Home Assistant or Docker.  It never overwrites a directory that does not
    carry the App-managed marker, which preserves an existing HACS/manual
    installation.
    """

    source = Path(source_dir)
    config = Path(config_dir)
    target = config / "custom_components" / DOMAIN
    target_string = str(target)

    if not source.is_dir():
        return IntegrationInstallResult(
            status="source_unavailable",
            version=None,
            target=target_string,
            restart_required=False,
            message="A integração embutida não está disponível nesta imagem.",
        )
    if not config.is_dir():
        return IntegrationInstallResult(
            status="config_unavailable",
            version=None,
            target=target_string,
            restart_required=False,
            message="O diretório de configuração do Home Assistant não está montado.",
        )

    version = _read_version(source)
    if not version:
        return IntegrationInstallResult(
            status="invalid_source",
            version=None,
            target=target_string,
            restart_required=False,
            message="O manifesto da integração não contém uma versão válida.",
        )

    if target.exists():
        marker = _read_marker(target)
        if marker is None:
            _LOGGER.info("Preserving external Smart House Scale integration at %s", target)
            return IntegrationInstallResult(
                status="external_existing",
                version=version,
                target=target_string,
                restart_required=False,
                message="Uma instalação externa já existe; nenhuma alteração foi feita.",
            )
        if marker.get("integration_version") == version:
            return IntegrationInstallResult(
                status="already_managed",
                version=version,
                target=target_string,
                restart_required=False,
                message="A integração já está instalada e gerenciada pelo App.",
            )
        status = "updated"
    else:
        status = "installed"

    try:
        _copy_integration(source, target, version=version, app_version=app_version)
    except (OSError, shutil.Error) as exc:
        _LOGGER.error("Could not install Smart House Scale integration: %s", type(exc).__name__)
        return IntegrationInstallResult(
            status="install_failed",
            version=version,
            target=target_string,
            restart_required=False,
            message="Não foi possível instalar a integração no Home Assistant.",
        )

    _LOGGER.info("Smart House Scale integration %s at %s", status, target)
    return IntegrationInstallResult(
        status=status,
        version=version,
        target=target_string,
        restart_required=True,
        message="A integração foi instalada; o Core do Home Assistant precisa recarregar os componentes.",
    )


def ensure_integration_from_environment() -> IntegrationInstallResult:
    return ensure_integration(
        config_dir=os.getenv("SMART_HOUSE_SCALE_HA_CONFIG_DIR", DEFAULT_CONFIG_DIR),
        source_dir=os.getenv("SMART_HOUSE_SCALE_INTEGRATION_SOURCE", DEFAULT_SOURCE_DIR),
        app_version=os.getenv("APP_VERSION", "unknown"),
    )
