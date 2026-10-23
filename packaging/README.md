# Windows x64 release build

This folder builds the per-user `TestCraft-1.1.1-windows-x64-setup.exe` installer and, optionally, a portable ZIP. The build consumes a curated source staging folder and tool distributions supplied by the release builder. It does not download or install Python, Node.js, Codex, or Inno Setup on the build machine.

The source stage must contain the approved `app/`, `tools/`, `templates/`, and `instructions/` trees. It may also include root `LICENSE`, `README.md`, and `THIRD_PARTY_NOTICES.md`; the build copies those files explicitly when present. It must include the release `app/desktop.py` entry point and `app/static/favicon.ico`. The build copies only those trees and named root files, filters local data, audit folders, credentials, caches, and private exam folders, then checks required files before packaging.

The release builder must provide:

- The official CPython 3.13 x64 embeddable ZIP.
- The CPython license text as shipped with that ZIP, or pass the official license file through `--python-license` if the ZIP does not include it.
- An extracted official Windows x64 Node.js distribution, plus a prepared `node_modules` tree containing the pinned Sharp package and Windows native dependencies. Keep `node_modules` beside the Node distribution or pass it separately.
- The extracted official OpenAI Codex CLI Windows x64 release. Its `release-info.json` must contain `version`, `url`, and `archive_sha256`; when the original ZIP is unavailable, it must also contain the original `archive_executable` path. The extracted main binary must be named `codex.exe`, with all Windows sandbox helper executables and the Apache 2.0 license text present. Supplying the original Codex ZIP enables the build to verify its hash and exact file inventory and derive the original executable path for repair downloads.
- A fully pinned `requirements-windows.lock` for CPython 3.13 / Windows x64. Exact `==` pins are required; if SHA-256 hashes are present for every requirement, pip hash-checking is enabled as well.
- The Inno Setup compiler (`ISCC.exe`). The build uses the .NET Framework x64 `csc.exe` from `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe` by default.

Example invocation from the repository root (replace paths with the verified release inputs):

```powershell
python packaging/build_windows.py `
  --source C:\release\testcraft-source `
  --python-embed C:\release\python-3.13-embed-amd64.zip `
  --python-version 3.13.17 `
  --wheel-dir C:\release\python-wheelhouse `
  --node-dir C:\release\node-v24-win-x64 `
  --node-version 24.22.1 `
  --codex-dir C:\release\codex-windows-x64 `
  --codex-archive C:\release\codex-windows-x64.zip `
  --iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' `
  --output C:\release\dist `
  --portable-zip
```

`--python-archive-sha256` and `--node-archive` / `--node-archive-sha256` can verify the official runtime archives. `--codex-version` and `--codex-archive-sha256` may be supplied explicitly; otherwise both are read from the Codex `release-info.json`. The embedded runtime layout is `dist\TestCraft\`; the final installer, optional portable ZIP, and `SHA256SUMS` are written directly under the selected output directory. Python wheels are installed into the isolated runtime using the provided host Python and the lock file's CPython 3.13 Windows x64 tags. Pass `--wheel-dir` with a prepared local wheelhouse to force an offline install using explicit pip `--no-index --find-links` options; without it pip may use its configured package index.

The installer runs without elevation and defaults to `%LOCALAPPDATA%\Programs\TestCraft`. It creates a Start Menu shortcut and offers an unchecked desktop shortcut task. App data is held separately in the user profile and is not targeted by install or uninstall rules. The same app icon is embedded in `TestCraft.exe`, shown by Setup, and used for shortcuts and the Add/Remove Programs entry.

Before an update or uninstall, Setup invokes the installed `app/desktop.py --stop` with its bundled `pythonw.exe`. This requests a graceful shutdown of that installation's server, waits for its process to exit, and refuses to interrupt a running AI job. No other Python applications are targeted. For manual troubleshooting, the same command accepts `--data-dir` to address an isolated test profile.
