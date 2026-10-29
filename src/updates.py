"""Release lookup, installer self-update helpers, and a prefilled problem report link."""
from i18n import tr

import hashlib
import itertools
import json
from pathlib import Path
import platform
import shutil
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from architecture import normalize_architecture

VERSION = "0.3.0"
REPOSITORY = "ParkoutV/ArcadeClip"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
NEW_ISSUE = f"https://github.com/{REPOSITORY}/issues/new"
TEMPLATE = "bug_report.md"
TIMEOUT = 10
LIMIT = 1 << 20
INSTALLER_LIMIT = 1024 * 1024 * 1024  # 1 GiB max installer download


def _numbers(tag):
    # Compare leading numeric parts only, so a suffix such as "-beta" cannot break the check.
    parts = []
    for piece in tag.strip().lstrip("vV").split("."):
        digits = "".join(itertools.takewhile(str.isdigit, piece))
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def is_newer(tag, current=VERSION):
    return bool(_numbers(tag)) and _numbers(tag) > _numbers(current)


def _read(request, timeout, context):
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        if not response.geturl().startswith("https://"):
            raise ValueError(tr('HTTPS 응답이 아닙니다.'))
        return response.read(LIMIT)


def _fetch_release_payload(timeout=TIMEOUT) -> dict | None:
    request = urllib.request.Request(RELEASES_API, headers={
        "User-Agent": f"ArcadeClip/{VERSION}",
        "Accept": "application/vnd.github+json"})

    def fetch(context):
        try:
            return _read(request, timeout, context)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    try:
        body = fetch(ssl.create_default_context())
    except urllib.error.URLError as error:
        # A machine that cannot build any chain would never see a new version at all,
        # and this lookup only reads a version number.
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        from jackets import relaxed_context
        body = fetch(relaxed_context())
    if body is None:
        return None
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(tr('공개된 버전을 찾지 못했습니다.'))
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        raise ValueError(tr('공개된 버전을 찾지 못했습니다.'))
    return data


def latest_release(timeout=TIMEOUT):
    """The newest published release tag, or None when the project has published none.

    A draft is not a published release, so GitHub answers 404 for it. That is an
    answer, not a failure, and it must not read as a connection problem.
    """
    data = _fetch_release_payload(timeout=timeout)
    if data is None:
        return None
    return str(data.get("tag_name") or "").strip()


def latest_release_info(timeout=TIMEOUT, arch: str | None = None) -> dict | None:
    """Return release metadata including matching Windows standalone installer asset if available."""
    data = _fetch_release_payload(timeout=timeout)
    if data is None:
        return None
    tag = str(data.get("tag_name") or "").strip()
    page_url = str(data.get("html_url") or RELEASES_PAGE).strip()
    if not page_url.startswith("https://"):
        page_url = RELEASES_PAGE
    machine = (arch or platform.machine() or "").lower()
    target_arch = normalize_architecture(machine)

    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    exe_candidates = []
    sha_by_name = {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("browser_download_url") or "").strip()
        if not name or not url.startswith("https://"):
            continue
        lower = name.lower()
        if lower.endswith(".sha256"):
            sha_by_name[lower[:-7]] = url
        elif lower.endswith(".exe") and ("setup" in lower or "installer" in lower or "arcadeclip" in lower):
            exe_candidates.append((name, url))

    chosen_name, chosen_url = None, None
    ranked = []
    for name, url in exe_candidates:
        lower = name.lower()
        is_arm = 'arm64' in lower or 'aarch64' in lower
        is_amd = any(token in lower for token in ('amd64', 'x64', 'x86_64'))
        universal = 'universal' in lower or (is_arm and is_amd)
        if target_arch and universal:
            ranked.append((1, name, url))
        elif target_arch == 'arm64' and is_arm:
            ranked.append((0, name, url))
        elif target_arch == 'amd64' and is_amd:
            ranked.append((0, name, url))
    if ranked:
        _, chosen_name, chosen_url = min(ranked)

    sha_url = sha_by_name.get(chosen_name.lower()) if chosen_name else None
    return {
        "tag": tag,
        "url": page_url,
        "installer_name": chosen_name,
        "installer_url": chosen_url,
        "sha256_url": sha_url,
    }


def download_installer(installer_url: str, destination_dir: Path, cancel=None, report=None, *,
                       expected_sha256: str | None = None, timeout: int = 30) -> Path:
    """Download a standalone installer (.exe) over HTTPS and optionally verify its SHA-256."""
    url = str(installer_url or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.path.lower().endswith(".exe"):
        raise ValueError(tr('유효한 HTTPS 설치 파일(.exe) 주소가 아닙니다.'))
    filename = Path(parsed.path).name or "ArcadeClip-setup.exe"
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    target_path = destination_dir / filename

    request = urllib.request.Request(url, headers={"User-Agent": f"ArcadeClip/{VERSION}"})
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(prefix=".update-", suffix=".part", dir=destination_dir, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            if not response.geturl().startswith("https://"):
                raise ValueError(tr('HTTPS 응답이 아닙니다.'))
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            with temp_path.open("wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError(tr('작업을 취소했습니다.'))
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > INSTALLER_LIMIT:
                        raise ValueError(tr('설치 파일 크기가 허용 한도를 초과했습니다.'))
                    out.write(chunk)
                    digest.update(chunk)
                    if report is not None and total > 0:
                        pct = min(99, round(received * 100 / total))
                        report(tr('업데이트 설치 파일 다운로드 중 · {percent}% ({mb:.1f} MB)',
                                  percent=pct, mb=received / (1024 * 1024)))
        header = temp_path.read_bytes()[:2] if temp_path.stat().st_size >= 2 else b""
        if header != b"MZ":
            raise ValueError(tr('다운로드한 파일이 올바른 Windows 실행 파일(.exe)이 아닙니다.'))
        if expected_sha256:
            clean_expected = expected_sha256.strip().split()[0].lower()
            if digest.hexdigest().lower() != clean_expected:
                raise ValueError(tr('다운로드한 설치 파일의 무결성(SHA-256) 검증에 실패했습니다.'))
        temp_path.replace(target_path)
        return target_path
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def installer_upgrade_args(install_dir: Path | None = None) -> list[str]:
    """Return Inno Setup flags for an in-place per-user upgrade that preserves user data."""
    args = [
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/CURRENTUSER",
        "/CLOSEAPPLICATIONS",
    ]
    if install_dir is not None:
        args.append(f"/DIR={Path(install_dir).resolve()}")
    return args


def prepare_local_update(update_file: Path, app_root: Path | None = None) -> dict:
    """Validate a local installer (.exe) or source update archive (.zip) and prepare/apply it."""
    path = Path(update_file).resolve()
    if not path.is_file():
        raise ValueError(tr('선택한 업데이트 파일을 찾을 수 없습니다.'))
    root = Path(app_root).resolve() if app_root is not None else Path(__file__).resolve().parents[1]
    suffix = path.suffix.lower()

    if suffix == ".exe":
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError(tr('올바른 Windows 설치 실행 파일(.exe)이 아닙니다.'))
        return {
            "mode": "installer",
            "path": path,
            "args": installer_upgrade_args(root),
        }

    if suffix == ".zip":
        src_dir = root / "src"
        if not src_dir.is_dir():
            raise ValueError(tr('앱 소스 폴더(src)를 찾을 수 없어 압축 업데이트를 적용할 수 없습니다.'))
        with zipfile.ZipFile(path, "r") as archive:
            if archive.testzip() is not None:
                raise ValueError(tr('손상된 ZIP 업데이트 파일입니다.'))
            entries = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                parts = Path(info.filename).parts
                if not parts or any(part in ("..", "") or ":" in part for part in parts):
                    raise ValueError(tr('안전하지 않은 경로가 포함된 압축 파일입니다.'))
                if "src" in parts:
                    idx = parts.index("src")
                    rel = Path(*parts[idx + 1:])
                else:
                    rel = Path(*parts)
                if not rel.parts or rel.parts[0] == "tests" or "__pycache__" in rel.parts or rel.suffix.lower() in (".pyc", ".pyo", ".pdb"):
                    continue
                entries.append((info, rel))
            if not entries:
                raise ValueError(tr('압축 파일에서 업데이트할 소스 항목을 찾지 못했습니다.'))
            for info, rel in entries:
                dest = (src_dir / rel).resolve()
                if not dest.is_relative_to(src_dir.resolve()):
                    raise ValueError(tr('안전하지 않은 경로가 포함된 압축 파일입니다.'))
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as src_stream, dest.open("wb") as dst_stream:
                    shutil.copyfileobj(src_stream, dst_stream)
        for cache_dir in src_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir, ignore_errors=True)
        return {
            "mode": "zip",
            "path": path,
            "updated_files": len(entries),
        }

    raise ValueError(tr('지원하는 업데이트 형식(.exe 설치 파일 또는 .zip 패키지)을 선택해 주세요.'))


def report_url():
    """A new issue on the project's own bug report form, which asks the questions."""
    return f"{NEW_ISSUE}?{urllib.parse.urlencode({'template': TEMPLATE})}"
