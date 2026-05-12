from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


RELEASES_API_URL = "https://api.github.com/repos/Yunis-Lu/iTalent-Attendance/releases"
RELEASE_TIMEOUT_SECONDS = 8
DOWNLOAD_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    body: str
    published_at: str
    html_url: str
    asset_name: str
    download_url: str
    is_prerelease: bool
    is_newer: bool


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    releases: list[ReleaseInfo]

    @property
    def has_update(self) -> bool:
        return any(release.is_newer for release in self.releases)


def check_releases(current_version: str) -> UpdateCheckResult:
    response = requests.get(
        RELEASES_API_URL,
        timeout=RELEASE_TIMEOUT_SECONDS,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "iTalent-Attendance"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("GitHub 返回的版本信息格式不正确。")

    releases: list[ReleaseInfo] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        asset_name, download_url = _find_windows_asset(item.get("assets") or [])
        tag = str(item.get("tag_name") or "").strip() or _version_from_asset(asset_name)
        if not tag:
            continue
        name = str(item.get("name") or "").strip() or tag
        releases.append(
            ReleaseInfo(
                tag=tag,
                name=name,
                body=str(item.get("body") or "").strip(),
                published_at=str(item.get("published_at") or ""),
                html_url=str(item.get("html_url") or ""),
                asset_name=asset_name,
                download_url=download_url,
                is_prerelease=bool(item.get("prerelease")),
                is_newer=is_version_newer(tag, current_version),
            )
        )
    releases.sort(key=lambda release: release.published_at, reverse=True)
    return UpdateCheckResult(current_version=current_version, releases=releases)


def download_release(release: ReleaseInfo, progress: Callable[[int, int], None] | None = None) -> Path:
    if not release.download_url:
        raise RuntimeError("这个版本没有可下载的 Windows exe 文件。")

    target_dir = Path(tempfile.gettempdir()) / "iTalent-Attendance"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = _safe_asset_name(release.asset_name) or f"iTalent-Attendance.{_safe_filename(release.tag)}.exe"
    target = target_dir / target_name
    with requests.get(
        release.download_url,
        stream=True,
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        headers={"User-Agent": "iTalent-Attendance"},
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or 0)
        written = 0
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                file.write(chunk)
                written += len(chunk)
                if progress:
                    progress(written, total)
    return target


def install_downloaded_update(downloaded_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("当前是源码运行模式，只有打包后的 exe 才能自动覆盖更新。")

    current_exe = Path(sys.executable).resolve()
    if not current_exe.exists():
        raise RuntimeError("未找到当前正在运行的 exe。")

    next_exe = current_exe.with_name(downloaded_exe.name)
    if next_exe == current_exe:
        backup_exe = current_exe.with_suffix(current_exe.suffix + ".old")
    else:
        backup_exe = current_exe

    script_path = Path(tempfile.gettempdir()) / "iTalent-Attendance" / "apply_update.cmd"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        "\r\n".join(
            [
                "@echo off",
                "setlocal",
                f'set "SRC={downloaded_exe}"',
                f'set "DEST={next_exe}"',
                f'set "OLD={backup_exe}"',
                'set "COPIED="',
                "for /l %%i in (1,1,30) do (",
                '  copy /y "%SRC%" "%DEST%" >nul 2>nul && set "COPIED=1" && goto updated',
                "  timeout /t 1 /nobreak >nul",
                ")",
                "exit /b 1",
                ":updated",
                'timeout /t 2 /nobreak >nul',
                'if /i not "%OLD%"=="%DEST%" del "%OLD%" >nul 2>nul',
                'start "" "%DEST%"',
                'del "%SRC%" >nul 2>nul',
                'del "%~f0" >nul 2>nul',
            ]
        ),
        encoding="gbk",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script_path)],
        cwd=str(current_exe.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
    os._exit(0)


def is_version_newer(remote: str, current: str) -> bool:
    remote_parts = _version_parts(remote)
    current_parts = _version_parts(current)
    if not remote_parts:
        return False
    length = max(len(remote_parts), len(current_parts))
    remote_parts += [0] * (length - len(remote_parts))
    current_parts += [0] * (length - len(current_parts))
    return remote_parts > current_parts


def _version_parts(value: str) -> list[int]:
    return [int(part) for part in re.findall(r"\d+", value)]


def _find_windows_asset(assets: list[object]) -> tuple[str, str]:
    fallback: tuple[str, str] = ("", "")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not name or not url:
            continue
        lower = name.lower()
        if lower.endswith(".exe"):
            if "italent-attendance" in lower:
                return name, url
            if not fallback[0]:
                fallback = (name, url)
    return fallback


def _version_from_asset(name: str) -> str:
    match = re.search(r"v\d+(?:[._-]\d+)*", name, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).replace("_", ".").replace("-", ".")


def _safe_asset_name(value: str) -> str:
    name = Path(value).name
    if not name.lower().endswith(".exe"):
        return ""
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "release"
