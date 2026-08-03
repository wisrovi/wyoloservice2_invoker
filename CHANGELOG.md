# Changelog - GPU Invoker (Hive)

## [1.7.1] - 2026-08-03
### Fixed
- Fixed default executor container timeout inconsistency, changing the container wait timeout from 1 hour to 12 hours (43200 seconds) and adding the `executor_timeout_seconds` configuration option in config.yaml.

## [1.1.0] - 2026-05-27
### Added
- Robust Samba (CIFS) mounting logic with auto-retry.
- Improved Docker resource cleaning after trial failure.
- New marketing landing page.
