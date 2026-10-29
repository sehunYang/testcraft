#!/usr/bin/env python3
"""Build the portable runtime tree and per-user Windows x64 installer.

All executable inputs are supplied by the release builder. This script does not
download or install Python, Node, Codex, or Inno Setup on the build machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


VERSION = "1.1.2"
PRODUCT = "TestCraft"
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_ROOT = Path(__file__).resolve().parent
REQUIREMENTS_LOCK = PACKAGING_ROOT / "requirements-windows.lock"
SOURCE_ROOTS = ("app", "tools", "templates", "instructions")
PIP_PYTHON_TARGET = "3.13"
PIP_ABI = "cp313"
PIP_PLATFORM = "win_amd64"
PYTHON_DLL = "python313.dll"
PYTHON_PTH = "python313._pth"
LICENSE_PREFIXES = ("license", "licence", "copying", "notice", "third-party")
FORBIDDEN_PARTS = {
    ".agents",
    ".aws",
    ".codex",
    ".git",
    ".runtime",
    ".venv",
    "__pycache__",
    "auth",
    "authdata",
    "exams",
    "lessons",
    "local-data",
    "local_data",
    "localdata",
    "node_modules",
    "private",
    "private-data",
    "private_data",
    "private-exams",
    "private_exams",
    "reference",
}


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file()
    }


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def normalized_component(part: str) -> str:
    return part.casefold().replace("\\", "/")


def excluded_relative(path: Path, source_root: Path) -> bool:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return True
    parts = [normalized_component(part) for part in relative.parts]
    if any(part in FORBIDDEN_PARTS for part in parts):
        return True
    if any("audit" in part for part in parts):
        return True
    if any(part.endswith((".pyc", ".pyo", ".log", ".sqlite", ".sqlite3", ".db", ".pem", ".key")) for part in parts):
        return True
    if any(part in {"auth.json", "credentials.json", "token.json", "secrets.json"} for part in parts):
        return True
    return False


def copy_curated_source(source: Path, destination: Path) -> None:
    source = source.resolve()
    if not source.is_dir():
        raise BuildError(f"Source staging directory does not exist: {source}")
    if path_is_within(destination, source):
        raise BuildError("Output stage must not be inside the source staging directory.")
    missing = [name for name in SOURCE_ROOTS if not (source / name).is_dir()]
    if missing:
        raise BuildError("Source stage is missing approved directories: " + ", ".join(missing))

    def ignore(source_dir: str, names: list[str]) -> set[str]:
        current = Path(source_dir)
        ignored: set[str] = set()
        for name in names:
            child = current / name
            if excluded_relative(child, source):
                ignored.add(name)
            elif child.is_file() and child.suffix.casefold() in {".pyc", ".pyo", ".log", ".sqlite", ".sqlite3", ".db", ".pem", ".key"}:
                ignored.add(name)
        return ignored

    destination.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_ROOTS:
        shutil.copytree(source / name, destination / name, ignore=ignore, symlinks=False)
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        file = source / name
        if file.is_file():
            shutil.copy2(file, destination / name)

    required = (
        destination / "app" / "desktop.py",
        destination / "app" / "static" / "favicon.ico",
        destination / "instructions" / "00-작업-흐름.md",
    )
    missing_files = [str(path.relative_to(destination)) for path in required if not path.is_file()]
    if missing_files:
        raise BuildError("Curated source stage lacks required files: " + ", ".join(missing_files))

    for path in destination.rglob("*"):
        if excluded_relative(path, destination):
            raise BuildError(f"Filtered release source still contains a prohibited path: {path}")


def safe_extract_zip(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            raw_name = item.filename.replace("\\", "/")
            relative = PurePosixPath(raw_name)
            if relative.is_absolute() or ".." in relative.parts or ":" in raw_name:
                raise BuildError(f"Unsafe path in archive {archive.name}: {item.filename}")
            target = destination.joinpath(*relative.parts)
            if not path_is_within(target, root):
                raise BuildError(f"Archive entry escapes destination: {item.filename}")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def exact_lock_is_hashed(lock: Path) -> bool:
    text = lock.read_text(encoding="utf-8-sig")
    requirement_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--hash="):
            continue
        if line.startswith("-"):
            raise BuildError(f"Lock file cannot contain pip options: {line}")
        requirement = line.split(";", 1)[0].strip()
        requirement = requirement.split(" --hash=", 1)[0].strip().rstrip("\\").strip()
        if not requirement:
            continue
        if not re.match(r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s;\\]+$", requirement):
            raise BuildError(
                f"Every Windows runtime requirement must pin an exact version with ==: {raw}"
            )
        requirement_lines.append(line)
    if not requirement_lines:
        raise BuildError(f"Runtime lock is empty: {lock}")
    return "--hash=sha256:" in text


def build_python_runtime(
    embed_zip: Path,
    stage: Path,
    lock: Path,
    host_python: str,
    expected_version: str | None,
    expected_sha256: str | None,
    license_file: Path | None,
    wheel_dir: Path | None,
) -> tuple[str, str]:
    if not embed_zip.is_file():
        raise BuildError(f"Embedded Python zip does not exist: {embed_zip}")
    archive_hash = sha256_file(embed_zip)
    if expected_sha256:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise BuildError("--python-archive-sha256 must contain 64 hexadecimal characters.")
        if archive_hash != expected_sha256.casefold():
            raise BuildError(f"Python archive SHA-256 mismatch: expected {expected_sha256}, got {archive_hash}")
    if not lock.is_file():
        raise BuildError(f"Pinned Windows dependency lock is required: {lock}")
    if wheel_dir is not None and not wheel_dir.is_dir():
        raise BuildError(f"Offline wheel directory does not exist: {wheel_dir}")
    require_hashes = exact_lock_is_hashed(lock)
    runtime = stage / "runtime" / "python"
    runtime.mkdir(parents=True)
    safe_extract_zip(embed_zip, runtime)

    required = (runtime / PYTHON_PTH, runtime / PYTHON_DLL, runtime / "pythonw.exe", runtime / "python.exe")
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise BuildError("Not a CPython 3.13 x64 embeddable distribution; missing: " + ", ".join(missing))

    python = runtime / "python.exe"
    version_result = subprocess.run(
        [str(python), "-I", "--version"], check=True, capture_output=True, text=True
    )
    python_version = version_result.stdout.strip() or version_result.stderr.strip()
    match = re.search(r"Python\s+(\d+\.\d+\.\d+)", python_version)
    if not match or not match.group(1).startswith("3.13."):
        raise BuildError(f"Expected CPython 3.13.x, got: {python_version}")
    actual_version = match.group(1)
    if expected_version and expected_version.removeprefix("v") != actual_version:
        raise BuildError(f"Embedded Python version mismatch: expected {expected_version}, got {actual_version}")

    pth = runtime / PYTHON_PTH
    pth.write_text("python313.zip\n.\nLib/site-packages\nimport site\n", encoding="ascii", newline="\n")
    site_packages = runtime / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)

    pip_args = [
        host_python,
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--no-compile",
        "--upgrade",
        "--only-binary=:all:",
        "--platform",
        PIP_PLATFORM,
        "--implementation",
        "cp",
        "--python-version",
        PIP_PYTHON_TARGET,
        "--abi",
        PIP_ABI,
        "--target",
        str(site_packages),
    ]
    if require_hashes:
        pip_args.append("--require-hashes")
    if wheel_dir is not None:
        # `--isolated` intentionally ignores pip's environment variables, so
        # make offline behavior explicit in the command line itself.
        pip_args.extend(("--no-index", "--find-links", str(wheel_dir.resolve())))
    pip_args.extend(("-r", str(lock.resolve())))
    subprocess.run(pip_args, check=True)

    # Pywin32 places extension DLLs outside the interpreter's DLL search path.
    # Keeping a handle alive makes them loadable in an embeddable interpreter.
    (site_packages / "sitecustomize.py").write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "_question_studio_dll_handles = []\n"
        "_question_studio_pywin32 = Path(__file__).resolve().parent / 'pywin32_system32'\n"
        "if os.name == 'nt' and _question_studio_pywin32.is_dir():\n"
        "    _question_studio_dll_handles.append(os.add_dll_directory(str(_question_studio_pywin32)))\n"
        "_question_studio_app_root = Path(__file__).resolve().parents[4]\n"
        "if str(_question_studio_app_root) not in sys.path:\n"
        "    sys.path.insert(0, str(_question_studio_app_root))\n",
        encoding="utf-8",
        newline="\n",
    )
    python_notice = stage / "notices" / "python-runtime"
    python_notice.mkdir(parents=True, exist_ok=True)
    runtime_licenses = [path for path in runtime.iterdir() if path.is_file() and license_name(path)]
    if license_file is not None:
        if not license_file.is_file():
            raise BuildError(f"CPython license file does not exist: {license_file}")
        runtime_licenses.append(license_file)
    if not runtime_licenses:
        raise BuildError("CPython distribution did not include its license; pass --python-license from the official distribution.")
    for index, path in enumerate(runtime_licenses):
        filename = path.name if path.parent == runtime else f"{index + 1}-{path.name}"
        shutil.copy2(path, python_notice / filename)
    return actual_version, archive_hash


def license_name(path: Path) -> bool:
    name = path.name.casefold()
    return any(name.startswith(prefix) for prefix in LICENSE_PREFIXES)


def copy_matching_licenses(source: Path, destination: Path, *, required: bool = False) -> list[str]:
    found = [path for path in source.rglob("*") if path.is_file() and license_name(path)]
    if required and not found:
        raise BuildError(f"No license or notice files found under {source}")
    copied: list[str] = []
    for path in found:
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(relative.as_posix())
    return copied


def package_location(modules: Path, package_name: str, importer: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if importer is not None:
        candidates.append(importer / "node_modules" / Path(*package_name.split("/")))
        for ancestor in importer.parents:
            if ancestor.name == "node_modules":
                candidates.append(ancestor / Path(*package_name.split("/")))
    candidates.append(modules / Path(*package_name.split("/")))
    for candidate in candidates:
        if candidate.is_dir() and path_is_within(candidate, modules):
            return candidate
    return None


def collect_sharp_packages(modules_source: Path, stage: Path) -> tuple[list[dict[str, str]], list[Path]]:
    modules_source = modules_source.resolve()
    if not (modules_source / "sharp" / "package.json").is_file():
        raise BuildError(f"Node module tree must contain sharp/package.json: {modules_source}")
    modules_target = stage / "node_modules"
    modules_target.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[str, Path | None]] = [("sharp", None)]
    copied: dict[str, Path] = {}

    while pending:
        name, importer = pending.pop(0)
        location = package_location(modules_source, name, importer)
        if location is None:
            # npm leaves platform-inapplicable optional dependencies out of the tree.
            if importer is not None:
                importer_manifest = json.loads((importer / "package.json").read_text(encoding="utf-8"))
                if name in importer_manifest.get("optionalDependencies", {}):
                    continue
            raise BuildError(f"Required Sharp dependency {name!r} is missing from {modules_source}")
        relative = location.relative_to(modules_source)
        if not relative.parts or any(part in {".bin", ".cache"} for part in relative.parts):
            raise BuildError(f"Unexpected Sharp package location: {location}")
        key = relative.as_posix()
        if key in copied:
            continue
        target = modules_target / relative
        shutil.copytree(location, target, symlinks=False)
        copied[key] = target

        manifest = json.loads((location / "package.json").read_text(encoding="utf-8"))
        dependencies = manifest.get("dependencies", {})
        optional_dependencies = manifest.get("optionalDependencies", {})
        for dependency in sorted(set(dependencies) | set(optional_dependencies)):
            pending.append((dependency, location))

    records: list[dict[str, str]] = []
    license_targets: list[Path] = []
    for relative, target in sorted(copied.items()):
        manifest = json.loads((target / "package.json").read_text(encoding="utf-8"))
        records.append(
            {
                "name": str(manifest.get("name", relative)),
                "version": str(manifest.get("version", "unknown")),
                "license": str(manifest.get("license", "see package metadata")),
            }
        )
        license_targets.extend(path for path in target.rglob("*") if path.is_file() and license_name(path))
    if not any(path.name.casefold().startswith("license") for path in license_targets):
        raise BuildError("Sharp dependency tree has no license file to include in the release notices.")
    return records, license_targets


def build_node_runtime(
    node_dir: Path,
    node_modules: Path | None,
    stage: Path,
    expected_version: str | None,
    node_archive: Path | None,
    node_archive_sha256: str | None,
) -> tuple[str, list[dict[str, str]], list[Path], str | None]:
    node_dir = node_dir.resolve()
    node_exe = node_dir / "node.exe"
    if not node_exe.is_file():
        raise BuildError(f"Node distribution directory must contain node.exe: {node_dir}")
    result = subprocess.run([str(node_exe), "--version"], check=True, capture_output=True, text=True)
    version = result.stdout.strip()
    if expected_version and expected_version.removeprefix("v") != version.removeprefix("v"):
        raise BuildError(f"Node version mismatch: expected {expected_version}, got {version}")
    actual_archive_hash = None
    if node_archive is not None or node_archive_sha256:
        if node_archive is None or not node_archive_sha256:
            raise BuildError("Supply both --node-archive and --node-archive-sha256 when verifying the official Node archive.")
        if not node_archive.is_file() or not re.fullmatch(r"[0-9a-fA-F]{64}", node_archive_sha256):
            raise BuildError("The Node archive must exist and its expected SHA-256 must contain 64 hexadecimal characters.")
        actual_archive_hash = sha256_file(node_archive)
        if actual_archive_hash != node_archive_sha256.casefold():
            raise BuildError(f"Node archive SHA-256 mismatch: expected {node_archive_sha256}, got {actual_archive_hash}")

    runtime_node = stage / "runtime" / "node"
    runtime_node.mkdir(parents=True)
    shutil.copy2(node_exe, runtime_node / "node.exe")
    node_licenses = [path for path in node_dir.iterdir() if path.is_file() and license_name(path)]
    if not node_licenses:
        raise BuildError(f"Official Node distribution license file is missing from {node_dir}")
    notices = stage / "notices" / "node"
    notices.mkdir(parents=True, exist_ok=True)
    for license_file in node_licenses:
        shutil.copy2(license_file, notices / f"Node-{license_file.name}")

    modules_source = node_modules.resolve() if node_modules else (node_dir / "node_modules").resolve()
    records, dependency_licenses = collect_sharp_packages(modules_source, stage)
    package_notices = stage / "notices" / "node-modules"
    package_notices.mkdir(parents=True, exist_ok=True)
    for license_file in dependency_licenses:
        package_root = next((root for root in (stage / "node_modules").rglob("package.json") if license_file.is_relative_to(root.parent)), None)
        if package_root is None:
            continue
        package_name = json.loads(package_root.read_text(encoding="utf-8")).get("name", package_root.parent.name)
        relative_name = license_file.relative_to(package_root.parent)
        target = package_notices / str(package_name).replace("/", "_") / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_file, target)

    # This is consumed by app startup so the bundled provider can be found without PATH.
    return version, records, [*node_licenses, *dependency_licenses], actual_archive_hash


def verify_codex_archive_contents(
    codex_dir: Path, archive: Path, requested_executable: str | None = None,
) -> tuple[str, set[str]]:
    """Verify an extracted Codex tree, allowing its root CLI to be renamed.

    The application always deploys the primary binary as ``codex.exe``. The
    official ZIP may use a target-specific filename, so map that archive member
    to the renamed extracted file by its digest and retain the archive path for
    repair downloads.
    """
    def safe_archive_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (not normalized or normalized.startswith("/") or ":" in normalized
                or "\x00" in normalized or any(part in {"", ".", ".."} for part in path.parts)):
            raise BuildError(f"Unsafe Codex archive executable path: {value!r}")
        return path.as_posix()

    with zipfile.ZipFile(archive) as package:
        entries = [item.filename.replace("\\", "/").rstrip("/") for item in package.infolist() if not item.is_dir()]
        entries = [entry for entry in entries if entry and not entry.startswith("__MACOSX/")]
        for entry in entries:
            safe_archive_path(entry)
        first_parts = {entry.split("/", 1)[0] for entry in entries}
        if entries and len(first_parts) == 1 and all("/" in entry for entry in entries):
            common = next(iter(first_parts))
            entries = [entry.split("/", 1)[1] for entry in entries]
        else:
            common = None
        archive_files = {entry for entry in entries}
        raw_to_normalized = {
            item.filename.replace("\\", "/"): (
                item.filename.replace("\\", "/").split("/", 1)[1]
                if common and "/" in item.filename.replace("\\", "/")
                else item.filename.replace("\\", "/")
            )
            for item in package.infolist()
            if not item.is_dir()
        }
        normalized_to_raw = {normalized: raw for raw, normalized in raw_to_normalized.items()}
        extracted = {
            path.relative_to(codex_dir).as_posix()
            for path in codex_dir.rglob("*")
            if path.is_file()
        }
        if "release-info.json" not in archive_files:
            extracted.discard("release-info.json")
        if "manifest.json" not in archive_files:
            extracted.discard("manifest.json")

        local_cli = codex_dir / "codex.exe"
        if not local_cli.is_file():
            raise BuildError("The extracted Codex release must expose its primary binary as root codex.exe.")
        local_cli_hash = sha256_file(local_cli)
        executable = safe_archive_path(requested_executable) if requested_executable else None
        if executable and common and executable.startswith(common + "/"):
            executable = executable[len(common) + 1:]
        if executable is None:
            candidates = []
            for relative in archive_files:
                if not relative.casefold().endswith(".exe"):
                    continue
                member = package.getinfo(normalized_to_raw[relative])
                with package.open(member, "r") as stream:
                    if hashlib.sha256(stream.read()).hexdigest() == local_cli_hash:
                        candidates.append(relative)
            if len(candidates) != 1:
                raise BuildError("Could not uniquely identify the renamed Codex CLI in the official archive; set archive_executable in release-info.json.")
            executable = candidates[0]
        if executable not in archive_files:
            raise BuildError(f"Official Codex archive is missing its primary executable: {executable}")
        local_as_archive = set(extracted)
        if executable != "codex.exe":
            local_as_archive.discard("codex.exe")
            local_as_archive.add(executable)
        if archive_files != local_as_archive:
            missing = sorted(archive_files - local_as_archive)
            extra = sorted(local_as_archive - archive_files)
            raise BuildError(
                "Extracted Codex files do not match the official archive"
                + (f"; missing: {', '.join(missing[:8])}" if missing else "")
                + (f"; extra: {', '.join(extra[:8])}" if extra else "")
            )
        for relative in archive_files:
            member = package.getinfo(normalized_to_raw[relative])
            if member is None:
                raise BuildError(f"Codex archive is missing an expected file entry: {relative}")
            with package.open(member, "r") as source:
                digest = hashlib.sha256(source.read()).hexdigest()
            local_relative = "codex.exe" if relative == executable else relative
            if digest != sha256_file(codex_dir / Path(*local_relative.split("/"))):
                raise BuildError(f"Extracted Codex file does not match its archive entry: {relative}")
        return executable, archive_files


def build_codex_runtime(
    codex_dir: Path,
    stage: Path,
    archive_sha256: str | None,
    expected_version: str | None,
    archive: Path | None,
    license_file: Path | None,
) -> tuple[str, str, str, list[str]]:
    codex_dir = codex_dir.resolve()
    if not codex_dir.is_dir():
        raise BuildError(f"Extracted official Codex release directory does not exist: {codex_dir}")
    info_path = codex_dir / "release-info.json"
    if not info_path.is_file():
        raise BuildError("The extracted Codex release must include release-info.json with version, url, and archive_sha256.")
    try:
        release_info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"Could not read Codex release-info.json: {error}") from error
    info_version = str(release_info.get("version", "")).strip().removeprefix("v")
    download_url = str(release_info.get("url", "")).strip()
    info_hash = str(release_info.get("archive_sha256", "")).strip().casefold()
    if not info_version or not download_url.startswith("https://") or not re.fullmatch(r"[0-9a-f]{64}", info_hash):
        raise BuildError("Codex release-info.json must contain an exact version, an HTTPS url, and a 64-character archive_sha256.")
    if expected_version and expected_version.removeprefix("v") != info_version:
        raise BuildError(f"Codex version mismatch: expected {expected_version}, release-info.json says {info_version}")
    if archive_sha256 and archive_sha256.casefold() != info_hash:
        raise BuildError(f"Codex SHA-256 mismatch: release-info.json says {info_hash}, argument says {archive_sha256}")
    archive_sha256 = info_hash
    requested_archive_executable = release_info.get("archive_executable")
    if requested_archive_executable is not None and not isinstance(requested_archive_executable, str):
        raise BuildError("Codex release-info.json archive_executable must be a relative path string.")
    if requested_archive_executable:
        normalized_executable = requested_archive_executable.replace("\\", "/")
        executable_path = PurePosixPath(normalized_executable)
        if (normalized_executable.startswith("/") or ":" in normalized_executable
                or "\x00" in normalized_executable
                or any(part in {"", ".", ".."} for part in executable_path.parts)):
            raise BuildError("Codex release-info.json archive_executable must be a safe relative archive path.")
    archive_executable = requested_archive_executable or "codex.exe"
    archive_files: set[str] | None = None
    if archive is not None:
        if not archive.is_file():
            raise BuildError(f"Codex release archive does not exist: {archive}")
        actual_archive_hash = sha256_file(archive)
        if actual_archive_hash != archive_sha256:
            raise BuildError(f"Codex release archive SHA-256 mismatch: expected {archive_sha256}, got {actual_archive_hash}")
        archive_executable, archive_files = verify_codex_archive_contents(
            codex_dir, archive, requested_archive_executable,
        )
    elif not requested_archive_executable:
        raise BuildError("Pass --codex-archive or set archive_executable in release-info.json so Codex repair can find the renamed binary.")

    runtime_codex = stage / "runtime" / "codex"
    runtime_codex.mkdir(parents=True)
    shutil.copytree(codex_dir, runtime_codex, dirs_exist_ok=True, symlinks=False)
    executables = sorted(path for path in runtime_codex.rglob("*.exe") if path.is_file())
    cli = runtime_codex / "codex.exe"
    if not cli.is_file():
        raise BuildError("Official Codex release must include its primary binary as root codex.exe.")
    helper_names = [path for path in executables if "sandbox" in path.name.casefold()]
    if not helper_names:
        raise BuildError("Official Codex release must include its Windows sandbox helper executable(s).")
    codex_licenses = copy_matching_licenses(codex_dir, stage / "notices" / "codex")
    codex_notice = stage / "notices" / "codex"
    if license_file is not None:
        if not license_file.is_file():
            raise BuildError(f"Codex license file does not exist: {license_file}")
        codex_notice.mkdir(parents=True, exist_ok=True)
        target = codex_notice / license_file.name
        if license_file.resolve() != target.resolve():
            shutil.copy2(license_file, target)
        codex_licenses.append(target.name)
    if not codex_licenses:
        raise BuildError("Codex release must include its Apache-2.0 license; pass --codex-license if the archive omits it.")

    # The manifest gives startup code an explicit path and lets it detect damaged or
    # missing bundled files before offering a repair. The release zip hash is kept
    # alongside per-file hashes for provenance and local integrity checks.
    if archive_files is None:
        # release-info.json is build metadata, not part of the upstream repair ZIP.
        archive_files = {
            path.relative_to(codex_dir).as_posix()
            for path in codex_dir.rglob("*")
            if path.is_file() and path.name.casefold() not in {"release-info.json", "manifest.json"}
        }
    files: dict[str, str] = {}
    for archive_path in sorted(archive_files):
        deployed_path = "codex.exe" if archive_path == archive_executable else archive_path
        if deployed_path in files:
            raise BuildError(f"Codex archive contains multiple files that map to the same deployed path: {deployed_path}")
        source_path = runtime_codex / Path(*deployed_path.split("/"))
        if not source_path.is_file():
            raise BuildError(f"A Codex archive file is missing from the packaged runtime: {archive_path}")
        files[deployed_path] = sha256_file(source_path)
    executable_relative = "codex.exe"
    helper_relative = [path.relative_to(runtime_codex).as_posix() for path in helper_names]
    version = info_version
    if not re.fullmatch(r"[A-Za-z0-9.+_-]+", version):
        raise BuildError(f"Invalid Codex version value: {version!r}")

    manifest = {
        "schema_version": 1,
        "provider": "openai-codex",
        "version": version,
        "platform": "win32-x64",
        "url": download_url,
        "archive_sha256": archive_sha256,
        "executable": executable_relative,
        "archive_executable": archive_executable,
        "executables": [path.relative_to(runtime_codex).as_posix() for path in executables],
        "sandbox_helpers": helper_relative,
        "files_sha256": files,
    }
    (runtime_codex / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return version, download_url, archive_sha256, codex_licenses


def collect_python_notices(site_packages: Path, stage: Path) -> list[dict[str, str]]:
    destination = stage / "notices" / "python"
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for dist_info in sorted(site_packages.glob("*.dist-info"), key=lambda item: item.name.casefold()):
        metadata = dist_info / "METADATA"
        if not metadata.is_file():
            continue
        fields: dict[str, list[str]] = {}
        for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key in {"Name", "Version", "License", "License-Expression"}:
                fields.setdefault(key, []).append(value.strip())
        name = (fields.get("Name") or [dist_info.name])[0]
        record = {
            "name": name,
            "version": (fields.get("Version") or ["unknown"])[0],
            "license": (fields.get("License-Expression") or fields.get("License") or ["see bundled license files"])[0],
        }
        records.append(record)
        licenses = [path for path in dist_info.rglob("*") if path.is_file() and license_name(path)]
        for license_file in licenses:
            relative = license_file.relative_to(dist_info)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
            target = destination / safe_name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(license_file, target)
    return records


def write_third_party_notice(stage: Path, python_records: list[dict[str, str]], node_records: list[dict[str, str]], codex_version: str) -> None:
    rows = [
        "# Third-party notices",
        "",
        "This release bundles the following runtimes and libraries. License text files are included in this directory and in the corresponding source-package directories where available.",
        "",
        f"- OpenAI Codex CLI for Windows x64: {codex_version} (see `codex/` and `runtime/codex/manifest.json`).",
        "- Node.js and Sharp dependency licenses: see `node/` and `node-modules/`.",
        "- Python package licenses: see `python/`.",
        "- Font and SVG editor licenses: see `fonts/` and `svg-edit/`.",
        "",
        "## Python runtime packages",
        "",
        "| Package | Version | License metadata |",
        "|---|---:|---|",
    ]
    for item in sorted(python_records, key=lambda value: value["name"].casefold()):
        license_text = item["license"].replace("|", "\\|")
        rows.append(f"| {item['name']} | {item['version']} | {license_text} |")
    rows.extend(("", "## Sharp and Node modules", "", "| Package | Version | License metadata |", "|---|---:|---|"))
    for item in sorted(node_records, key=lambda value: value["name"].casefold()):
        license_text = item["license"].replace("|", "\\|")
        rows.append(f"| {item['name']} | {item['version']} | {license_text} |")
    rows.append("")
    (stage / "notices" / "THIRD_PARTY_NOTICES.md").write_text("\n".join(rows), encoding="utf-8", newline="\n")


def build_launcher(stage: Path, csc: Path) -> None:
    if not csc.is_file():
        raise BuildError(f"Framework C# compiler was not found: {csc}")
    launcher_source = PACKAGING_ROOT / "TestCraftLauncher.cs"
    icon = stage / "app" / "static" / "favicon.ico"
    if not launcher_source.is_file() or not icon.is_file():
        raise BuildError("Launcher source or app icon is missing from packaging inputs.")
    command = [
        str(csc),
        "/nologo",
        "/target:winexe",
        f"/out:{stage / 'TestCraft.exe'}",
        f"/win32icon:{icon}",
        "/reference:System.Windows.Forms.dll",
        str(launcher_source),
    ]
    subprocess.run(command, check=True, cwd=str(PACKAGING_ROOT))


def deterministic_portable_zip(stage: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        files = sorted(stage.rglob("*"), key=lambda item: item.as_posix().casefold())
        for path in files:
            relative = Path(PRODUCT.replace(" ", "")) / path.relative_to(stage)
            name = relative.as_posix()
            if path.is_dir():
                item = zipfile.ZipInfo(name.rstrip("/") + "/", date_time=(1980, 1, 1, 0, 0, 0))
                item.external_attr = 0o40755 << 16
                item.compress_type = zipfile.ZIP_STORED
                output.writestr(item, b"")
                continue
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(item, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def find_csc(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return windows_dir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"


def compile_inno(installer: Path, stage: Path, output: Path) -> None:
    env = os.environ.copy()
    env["QUESTION_STUDIO_RELEASE_STAGE"] = str(stage.resolve())
    env["QUESTION_STUDIO_RELEASE_OUTPUT"] = str(output.resolve())
    subprocess.run([str(installer.resolve()), str(PACKAGING_ROOT / "TestCraft.iss")], check=True, env=env)


def clean_stage(stage: Path, output: Path, source: Path) -> None:
    stage_resolved = stage.resolve()
    output_resolved = output.resolve()
    source_resolved = source.resolve()
    if stage_resolved == output_resolved or stage_resolved == source_resolved:
        raise BuildError("The staged application path must be a child of the output directory.")
    if not path_is_within(stage_resolved, output_resolved):
        raise BuildError("The staged application must be output/TestCraft.")
    if path_is_within(output_resolved, source_resolved) or path_is_within(source_resolved, output_resolved):
        raise BuildError("Source and output directories must be separate.")
    if stage.exists():
        if stage.is_symlink():
            raise BuildError(f"Refusing to replace a symbolic-link build stage: {stage}")
        shutil.rmtree(stage)


def write_build_manifest(
    stage: Path,
    *,
    python_version: str,
    python_hash: str,
    node_version: str,
    node_dir: Path,
    node_hash: str | None,
    node_packages: list[dict[str, str]],
    codex_version: str,
    codex_url: str,
    codex_hash: str,
    lock: Path,
    csc: Path,
    iscc: Path,
) -> None:
    python_files = sha256_tree(stage)
    manifest_path = stage / "BUILD-MANIFEST.json"
    manifest = {
        "schema_version": 1,
        "product": "testcraft",
        "version": VERSION,
        "platform": "windows-x64",
        "python": {"version": python_version, "archive_sha256": python_hash},
        "node": {
            "version": node_version,
            "node_exe_sha256": sha256_file(node_dir / "node.exe"),
            "archive_sha256": node_hash,
            "packages": node_packages,
        },
        "codex": {
            "version": codex_version,
            "platform": "win32-x64",
            "url": codex_url,
            "archive_sha256": codex_hash,
            "manifest": "runtime/codex/manifest.json",
        },
        "requirements_lock_sha256": sha256_file(lock),
        "build_tools": {"framework_csc_sha256": sha256_file(csc), "inno_iscc_sha256": sha256_file(iscc)},
        "files_sha256": python_files,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_sha256sums(paths: Iterable[Path], output_dir: Path) -> Path:
    sums = output_dir / "SHA256SUMS"
    lines = [f"{sha256_file(path)}  {path.name}" for path in sorted(paths, key=lambda item: item.name.casefold())]
    sums.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return sums


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Curated source staging root containing app/, tools/, templates/, instructions/.")
    parser.add_argument("--python-embed", type=Path, required=True, help="Official CPython 3.13 x64 embeddable zip supplied by the release builder.")
    parser.add_argument("--python-version", help="Optional exact expected CPython patch version, such as 3.13.x.")
    parser.add_argument("--python-archive-sha256", help="Optional expected official CPython archive SHA-256; the archive is always hashed into the build manifest.")
    parser.add_argument("--python-license", type=Path, help="Optional official CPython license text if it is not included in the embeddable zip.")
    parser.add_argument("--node-dir", type=Path, required=True, help="Extracted official Windows x64 Node.js distribution directory.")
    parser.add_argument("--node-modules", type=Path, help="Prepared node_modules directory containing sharp and its Windows dependency closure; defaults to --node-dir/node_modules.")
    parser.add_argument("--node-version", help="Optional exact expected Node.js version, such as 24.x.y.")
    parser.add_argument("--node-archive", type=Path, help="Optional official Node.js archive used to verify its published checksum.")
    parser.add_argument("--node-archive-sha256", help="Expected SHA-256 for --node-archive.")
    parser.add_argument("--codex-dir", type=Path, required=True, help="Extracted official Codex CLI Windows x64 release directory.")
    parser.add_argument("--codex-version", help="Optional Codex CLI version; otherwise read from release-info.json.")
    parser.add_argument("--codex-archive-sha256", help="Optional SHA-256 of the official Codex release zip; otherwise read from release-info.json.")
    parser.add_argument("--codex-archive", type=Path, help="Optional official Codex zip; when supplied, its SHA-256 is verified.")
    parser.add_argument("--codex-license", type=Path, help="Optional official Apache-2.0 license text if it is not included in the Codex release directory.")
    parser.add_argument("--iscc", type=Path, required=True, help="Path to Inno Setup's ISCC.exe supplied by the release builder.")
    parser.add_argument("--csc", type=Path, help="Optional path to .NET Framework 4.x csc.exe; defaults to the Windows x64 Framework64 compiler.")
    parser.add_argument("--host-python", default=sys.executable, help="Host Python used only to install pinned CPython 3.13 Windows wheels.")
    parser.add_argument("--requirements-lock", type=Path, default=REQUIREMENTS_LOCK, help="Fully pinned Windows wheel requirements lock.")
    parser.add_argument("--wheel-dir", type=Path, help="Optional local wheelhouse; when supplied, pip uses --no-index and --find-links for an offline install.")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist", help="Output directory; contains TestCraft/ and release artifacts.")
    parser.add_argument("--portable-zip", action="store_true", help="Also create a deterministic portable ZIP of TestCraft/.")
    return parser.parse_args()


def preflight_inputs(args: argparse.Namespace) -> tuple[Path, Path]:
    source = args.source.resolve()
    if not source.is_dir():
        raise BuildError(f"Source staging directory does not exist: {source}")
    missing_roots = [name for name in SOURCE_ROOTS if not (source / name).is_dir()]
    if missing_roots:
        raise BuildError("Source stage is missing approved directories: " + ", ".join(missing_roots))
    required_files = {
        "CPython embeddable archive": args.python_embed,
        "Windows requirements lock": args.requirements_lock,
        "Node executable": args.node_dir / "node.exe",
        "Codex release metadata": args.codex_dir / "release-info.json",
        "Inno Setup compiler": args.iscc,
    }
    modules = args.node_modules.resolve() if args.node_modules else (args.node_dir.resolve() / "node_modules")
    required_files["Sharp package manifest"] = modules / "sharp" / "package.json"
    if args.csc:
        csc = args.csc.resolve()
    else:
        csc = find_csc(None)
    required_files[".NET Framework x64 C# compiler"] = csc
    for label, path in required_files.items():
        if not path.is_file():
            raise BuildError(f"Required {label} is missing: {path}")
    for optional_label, optional_path in (
        ("Codex archive", args.codex_archive),
        ("Node archive", args.node_archive),
        ("Python license", args.python_license),
        ("Codex license", args.codex_license),
    ):
        if optional_path is not None and not optional_path.is_file():
            raise BuildError(f"{optional_label} does not exist: {optional_path}")
    if args.wheel_dir is not None and not args.wheel_dir.is_dir():
        raise BuildError(f"Offline wheel directory does not exist: {args.wheel_dir}")
    if args.node_archive is not None and not args.node_archive_sha256:
        raise BuildError("--node-archive requires --node-archive-sha256.")
    if args.node_archive_sha256 and args.node_archive is None:
        raise BuildError("--node-archive-sha256 requires --node-archive.")
    return source, csc


def main() -> int:
    if os.name != "nt":
        raise BuildError("The final installer must be built on Windows (Framework csc and Inno Setup are required).")
    args = parse_args()
    source, csc = preflight_inputs(args)
    output = args.output.resolve()
    stage = output / "TestCraft"
    clean_stage(stage, output, source)
    output.mkdir(parents=True, exist_ok=True)
    for stale_name in (
        f"TestCraft-{VERSION}-windows-x64-setup.exe",
        f"TestCraft-{VERSION}-windows-x64-portable.zip",
        "SHA256SUMS",
    ):
        stale = output / stale_name
        if stale.is_file() and not stale.is_symlink():
            stale.unlink()

    copy_curated_source(source, stage)
    python_version, python_hash = build_python_runtime(
        args.python_embed.resolve(),
        stage,
        args.requirements_lock.resolve(),
        args.host_python,
        args.python_version,
        args.python_archive_sha256,
        args.python_license,
        args.wheel_dir,
    )
    node_version, node_packages, _, node_hash = build_node_runtime(
        args.node_dir,
        args.node_modules,
        stage,
        args.node_version,
        args.node_archive,
        args.node_archive_sha256,
    )
    codex_version, codex_url, codex_hash, _ = build_codex_runtime(
        args.codex_dir,
        stage,
        args.codex_archive_sha256,
        args.codex_version,
        args.codex_archive,
        args.codex_license,
    )

    # Retain the upstream font/SVG editor licenses in a prominent notice directory.
    fonts_source = stage / "app" / "fonts"
    if fonts_source.is_dir():
        copy_matching_licenses(fonts_source, stage / "notices" / "fonts", required=True)
    vendor_license = stage / "app" / "static" / "vendor" / "svg-edit" / "LICENSE-MIT.txt"
    if not vendor_license.is_file():
        raise BuildError("Bundled SVG-Edit license is missing from app/static/vendor/svg-edit.")
    vendor_notice = stage / "notices" / "svg-edit"
    vendor_notice.mkdir(parents=True, exist_ok=True)
    shutil.copy2(vendor_license, vendor_notice / vendor_license.name)

    python_records = collect_python_notices(stage / "runtime" / "python" / "Lib" / "site-packages", stage)
    write_third_party_notice(stage, python_records, node_packages, codex_version)
    build_launcher(stage, csc)
    write_build_manifest(
        stage,
        python_version=python_version,
        python_hash=python_hash,
        node_version=node_version,
        node_dir=args.node_dir.resolve(),
        node_hash=node_hash,
        node_packages=node_packages,
        codex_version=codex_version,
        codex_url=codex_url,
        codex_hash=codex_hash,
        lock=args.requirements_lock.resolve(),
        csc=csc,
        iscc=args.iscc.resolve(),
    )

    compile_inno(args.iscc, stage, output)
    installer = output / f"TestCraft-{VERSION}-windows-x64-setup.exe"
    if not installer.is_file():
        raise BuildError(f"Inno Setup completed without producing the expected installer: {installer}")
    artifacts = [installer]
    if args.portable_zip:
        portable = output / f"TestCraft-{VERSION}-windows-x64-portable.zip"
        deterministic_portable_zip(stage, portable)
        artifacts.append(portable)
    write_sha256sums(artifacts, output)
    print(f"Built: {installer}")
    if args.portable_zip:
        print(f"Built: {output / f'TestCraft-{VERSION}-windows-x64-portable.zip'}")
    print(f"Checksums: {output / 'SHA256SUMS'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"build_windows: error: {error}", file=sys.stderr)
        raise SystemExit(2)
