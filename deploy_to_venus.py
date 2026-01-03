#!/usr/bin/env python3
"""
Package and deploy the local dbus-serialbattery folder to a Venus OS target.

Default target: root@10.1.87.45:/data/apps/dbus-serialbattery
Prereqs: ssh + scp available on the host.
Usage (from repo root):
    python deploy_to_venus.py
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
import shlex
import sys


DEFAULT_HOST = "root@10.1.87.45"
DEFAULT_REMOTE_PATH = "/data/apps/dbus-serialbattery"
SOURCE_DIR = "dbus-serialbattery"

IGNORE_NAMES = {
    ".git",
    ".github",
    ".vscode",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "terminals",
}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".pdb"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy dbus-serialbattery to Venus OS")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"SSH target (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--remote-path",
        default=DEFAULT_REMOTE_PATH,
        help=f"Remote install path (default: {DEFAULT_REMOTE_PATH})",
    )
    parser.add_argument(
        "--source",
        default=SOURCE_DIR,
        help=f"Local source directory (default: {SOURCE_DIR})",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Do not create a backup tarball on the target before replacing",
    )
    return parser.parse_args()


def ensure_tools() -> None:
    missing = [cmd for cmd in ("ssh", "scp") if shutil.which(cmd) is None]
    if missing:
        sys.exit(f"Missing required commands: {', '.join(missing)}")


def tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    path_parts = Path(tarinfo.name).parts
    if any(part in IGNORE_NAMES for part in path_parts):
        return None
    if any(Path(tarinfo.name).name.endswith(suffix) for suffix in IGNORE_SUFFIXES):
        return None
    return tarinfo


def build_archive(source: Path) -> Path:
    if not source.is_dir():
        sys.exit(f"Source directory not found: {source}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    archive_path = Path(tmp.name)
    tmp.close()

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source, arcname=source.name, filter=tar_filter)

    return archive_path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def deploy(host: str, remote_path: Path, archive_path: Path, skip_backup: bool) -> None:
    remote_tmp = f"/tmp/{remote_path.name}-deploy.tar.gz"
    remote_base = str(remote_path.parent)

    print(f"[1/3] Uploading archive to {host}:{remote_tmp}")
    run(["scp", str(archive_path), f"{host}:{remote_tmp}"])

    backup_cmd = ""
    if not skip_backup:
        backup_cmd = (
            f'if [ -d {shlex.quote(remote_path.name)} ]; then '
            f'TS=$(date +%Y%m%d%H%M%S); '
            f'tar czf {shlex.quote(remote_path.name)}-backup-$TS.tar.gz '
            f'{shlex.quote(remote_path.name)}; '
            f'fi;'
        )

    remote_cmd = (
        "set -euo pipefail; "
        f"mkdir -p {shlex.quote(remote_base)}; "
        f"cd {shlex.quote(remote_base)}; "
        f"{backup_cmd}"
        f"rm -rf {shlex.quote(remote_path.name)}; "
        f"tar xzf {shlex.quote(remote_tmp)} -C {shlex.quote(remote_base)}; "
        f"rm -f {shlex.quote(remote_tmp)}"
    )

    print(f"[2/3] Deploying to {host}:{remote_path}")
    run(["ssh", host, remote_cmd])

    print("[3/3] Done. Previous install backed up with timestamp suffix." if not skip_backup else "[3/3] Done.")


def main() -> None:
    args = parse_args()
    ensure_tools()

    source_dir = Path(args.source).resolve()
    remote_path = Path(args.remote_path)

    archive_path = build_archive(source_dir)
    try:
        deploy(args.host, remote_path, archive_path, args.skip_backup)
    finally:
        archive_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

