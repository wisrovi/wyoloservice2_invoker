# Changelog - GPU Invoker (Hive)

## [1.9.2] - 2026-08-24
### Fixed
- **Optuna storage DB:** `optuna_search` now connects to the dedicated `optuna_db` instead of the shared `wyoloservice` PostgreSQL database. MLflow's Alembic migrations on the shared DB overwrite the generic `alembic_version` table, causing every `create_study` to fail with "The runtime optuna version 4.8.0 is no longer compatible with the table schema". Aligns the invoker with the manager's existing convention.
- **Gradio launcher DB:** default study-listing URL in `UI/gradio_launcher/db.py` moved to `optuna_db`.
- **EDA path translation:** `/datasets/...` paths are now translated to `/wyolo/control_server/datasets/...` before running `DatasetAnalyzer` inside the temporary executor container (which has no root `/datasets`), fixing `FileNotFoundError` during EDA.

### Version Update
- Bumped invoker version to `v1.9.2`.

## [1.7.5] - 2026-08-03
### Fixed
- Corrected python command list structure inside the docker container call in `EDA` to avoid syntax errors with single quotes.

### Gradio UI Launcher Changes:
#### [v1.1.0] - 2026-08-04
- **Redis Templates Refactor:** Moved shared templates to `invoker:shared_templates` hash in central Redis, and local saved config template to `invoker:<ip>:template_invoker`.
- **Destination Queue Prominence:** Added a prominent, highly styled target queue banner at the top of the UI to display the resolved private worker queue (derived from host's IP/hostname).
- **Execution Mode Clarifications:** Added markdown text explaining the exact functional difference between Simple Training (direct) and Full Pipeline execution modes.
- **Glassmorphic Cockpit Style:** Styled the UI with a beautiful, high-contrast dark theme.
- **Standalone UI deployment:** Added `Dockerfile`, `docker-compose.yaml`, and `Makefile` under the `UI/` folder.

## [1.7.4] - 2026-08-03
### Added
- Implemented Option A (Temporary Container execution) for the `EDA` state dataset analysis.

## [1.7.3] - 2026-08-03
### Changed
- Configured `TrainingReportAnalyzer` to explicitly use `opencode/deepseek-v4-flash-free` LLM model.
- Added diagnostics stdout/stderr logging outputs for OpenCode execution.

## [1.7.2] - 2026-08-03
### Added
- Integrated Dataset Imbalance and Type Detector (`DatasetAnalyzer`) in `EDA` state.
- Integrated OpenCode AI report generation (`TrainingReportAnalyzer`) in `LlmAnalizer` state.
- Added background thread resource utilization telemetry monitoring (CPU, RAM, GPU, current epoch).
- Restructured Gradio UI to include Live Telemetry metrics and Task Status check panel.

## [1.7.1] - 2026-08-03
### Fixed
- Fixed default executor container timeout inconsistency, changing the container wait timeout from 1 hour to 12 hours (43200 seconds) and adding the `executor_timeout_seconds` configuration option in config.yaml.

## [1.1.0] - 2026-05-27
### Added
- Robust Samba (CIFS) mounting logic with auto-retry.
- Improved Docker resource cleaning after trial failure.
- New marketing landing page.
