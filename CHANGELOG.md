# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Placeholder for upcoming changes. When you ship, move items under a dated version section and bump `APP_VERSION` in `app_version.py`.

## [0.2.2] - 2026-04-01

### Changed

- `scripts/install.sh`: expanded macOS support — Homebrew on Apple Silicon (`/opt/homebrew`) and Intel (`/usr/local`), MacPorts (`python312` + `port select`), discovery of python.org Framework installs when not on `PATH`, and clearer manual install hints.

## [0.2.1] - 2026-04-01

### Added

- `scripts/install.sh`: detects OS and CPU architecture, installs Python when needed, creates `.venv`, installs `requirements.txt`, and generates `scripts/run.sh` to launch the app from the venv.

## [0.2.0] - 2026-03-30

### Added

- Application version in window title and About dialog (`app_version.py`).
- Libraries and folder tags (registry, marker file `.tcc_library_root.json`, Libraries sidebar tab, tag assignment).
- This changelog and versioning workflow for the project.
