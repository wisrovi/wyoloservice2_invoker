# Changelog - GPU Invoker (Hive)

## [1.7.6] - 2026-08-04
### Added
- Unified the UI by merging features of `simple_dashboard` directly into `gradio_launcher`.
- Added **🖥️ Local Worker Status** section in Gradio to display Celery status, active tasks, and queues for the local node.
- Added **📊 Optuna Study History** section in Gradio to connect directly to the PostgreSQL database, display list of studies, query trial log list, and highlight the best historical trial.
- Created `Dockerfile`, `docker-compose.yaml`, and `Makefile` inside the `UI/` folder for standalone deployment.

## [1.7.5] - 2026-08-03
### Fixed
- Corrected python command list structure inside the docker container call in `EDA` to avoid syntax errors with single quotes.

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
