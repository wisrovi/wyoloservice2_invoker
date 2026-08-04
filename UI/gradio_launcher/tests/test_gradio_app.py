# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Unit tests for the Invoker Gradio launcher.

Covers queue resolution, YAML validation, Redis persistence helpers,
Celery task submission, the dry-run smoke test helper, task status
telemetry, and the train-click handler.
"""

from __future__ import annotations

import json
from unittest import mock
from unittest.mock import ANY

import pytest
import yaml

from celery_client import (
    check_redis_connection,
    launch_dry_run,
    save_template,
    validate_and_launch,
    validate_min_config,
)
from templates import load_template, load_user_template, list_user_templates, save_user_template
from ui.handlers import (
    _save_with_feedback,
    handle_train_click,
    load_selected_template,
    save_named_template_with_feedback,
    toggle_task_id_edit,
)
from telemetry import (
    check_task_status,
    get_download_state,
    get_results_zip as telemetry_get_results_zip,
    results_available,
)

_MIN_VALID_YAML: str = yaml.dump(
    {
        "model": "yolov8n.pt",
        "type": "yolo",
        "train": {"batch": -1, "data": "/d", "epochs": 2, "imgsz": 640},
        "metadata": {"author": "alice"},
        "sweeper": {"fitness": "mAP", "study_name": "test"},
    }
)


# ── validate_min_config ────────────────────────────────────────────


class TestValidateMinConfig:
    """Tests for the minimum-viable-config validator."""

    def test_valid(self) -> None:
        """Returns True for a fully valid config."""
        valid, msg = validate_min_config(_MIN_VALID_YAML)
        assert valid
        assert "válida" in msg

    def test_empty(self) -> None:
        """Returns False for empty content."""
        valid, _msg = validate_min_config("")
        assert valid is False

    def test_missing_model(self) -> None:
        """Detects missing model key."""
        cfg = yaml.dump(
            {
                "type": "yolo",
                "train": {"b": 1},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_missing_type(self) -> None:
        """Detects missing type key."""
        cfg = yaml.dump(
            {
                "model": "m",
                "train": {"b": 1},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_invalid_yaml_syntax(self) -> None:
        """Malformed YAML is rejected."""
        assert validate_min_config("{bad: yaml: }}")[0] is False

    def test_empty_data(self) -> None:
        """Empty train.data is rejected."""
        cfg = yaml.dump(
            {
                "model": "m",
                "type": "yolo",
                "train": {"data": "   "},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_zero_epochs(self) -> None:
        """train.epochs must be positive."""
        cfg = yaml.dump(
            {
                "model": "m",
                "type": "yolo",
                "train": {"data": "/d", "epochs": 0},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_non_dict_yaml(self) -> None:
        """Scalar YAML is rejected."""
        assert validate_min_config("just a string")[0] is False


# ── validate_and_launch ─────────────────────────────────────────────


class TestValidateAndLaunch:
    """Tests for the main train-submission function."""

    @mock.patch("celery_client._celery_app")
    @mock.patch("celery_client._get_hm")
    def test_valid_yaml(self, mock_get: mock.Mock, mock_celery: mock.Mock) -> None:
        """A fully-valid YAML is accepted and sent."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        mock_celery.send_task.return_value.id = "abc-123"
        result = validate_and_launch(_MIN_VALID_YAML)
        assert "Task ID" in result
        assert "abc-123" in result

    @mock.patch("celery_client._celery_app")
    @mock.patch("celery_client._get_hm")
    def test_user_id_filled_from_metadata(
        self, mock_get: mock.Mock, mock_celery: mock.Mock
    ) -> None:
        """user_id defaults to metadata.author when absent."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        mock_celery.send_task.return_value.id = "id"
        validate_and_launch(_MIN_VALID_YAML)
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["user_id"] == "alice"

    @mock.patch("celery_client._celery_app")
    @mock.patch("celery_client._get_hm")
    def test_respects_existing_user_id(
        self, mock_get: mock.Mock, mock_celery: mock.Mock
    ) -> None:
        """Existing user_id is preserved."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        mock_celery.send_task.return_value.id = "id"
        yaml_str = yaml.dump(
            {
                "model": "m",
                "type": "t",
                "train": {"batch": -1},
                "metadata": {"author": "alice"},
                "sweeper": {"fitness": "m", "study_name": "s"},
                "user_id": "bob",
            }
        )
        validate_and_launch(yaml_str)
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["user_id"] == "bob"

    def test_empty_yaml(self) -> None:
        """Empty content returns an error."""
        assert "❌" in validate_and_launch("")

    def test_missing_model(self) -> None:
        """YAML without a model field is rejected."""
        yaml_str = yaml.dump(
            {
                "type": "yolo",
                "train": {"batch": -1},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert "model" in validate_and_launch(yaml_str)

    def test_invalid_yaml_syntax(self) -> None:
        """Malformed YAML returns a generic error."""
        result = validate_and_launch("{bad: yaml: }}")
        assert "❌" in result

    @mock.patch("celery_client._celery_app")
    @mock.patch("celery_client._get_hm")
    def test_sends_to_private_queue(
        self, mock_get: mock.Mock, mock_celery: mock.Mock
    ) -> None:
        """Requests always go to the private queue, never a public one."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        mock_celery.send_task.return_value.id = "id"
        validate_and_launch(_MIN_VALID_YAML)
        assert mock_celery.send_task.call_args[1]["queue"] == "192.168.1.137"

    @mock.patch("celery_client._celery_app")
    @mock.patch("celery_client._get_hm")
    def test_celery_error(self, mock_get: mock.Mock, mock_celery: mock.Mock) -> None:
        """A Celery transport error is surfaced."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        mock_celery.send_task.side_effect = RuntimeError("Broker refused")
        result = validate_and_launch(_MIN_VALID_YAML)
        assert "Celery" in result


# ── launch_dry_run ───────────────────────────────────────────────────


class TestLaunchDryRun:
    """Tests for the smoke-test dry-run helper."""

    @mock.patch("celery_client._celery_app")
    def test_dry_run_success(self, mock_celery: mock.Mock) -> None:
        """Dry run sends the correct task and returns a success message."""
        mock_celery.send_task.return_value.id = "dry-123"
        result = launch_dry_run()
        assert "🧪" in result
        assert "dry-123" in result

    @mock.patch("celery_client._celery_app")
    def test_dry_run_payload_has_dry_run_flag(self, mock_celery: mock.Mock) -> None:
        """The payload sent includes dry_run: true."""
        mock_celery.send_task.return_value.id = "id"
        launch_dry_run()
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["dry_run"] is True

    @mock.patch("celery_client._celery_app")
    def test_dry_run_celery_error(self, mock_celery: mock.Mock) -> None:
        """A transport error is surfaced."""
        mock_celery.send_task.side_effect = RuntimeError("Timeout")
        result = launch_dry_run()
        assert "❌" in result


# ── Redis helpers ────────────────────────────────────────────────────


class TestCheckRedisConnection:
    """Tests for the Redis connectivity check."""

    @mock.patch("celery_client._get_hm")
    def test_ok(self, mock_get: mock.Mock) -> None:
        """Returns green indicator when Redis responds."""
        mock_hm = mock.Mock()
        mock_hm.exist.return_value = True
        mock_get.return_value = mock_hm
        assert "🟢" in check_redis_connection()

    @mock.patch("celery_client._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Returns red indicator when _get_hm returns None."""
        mock_get.return_value = None
        assert "🔴" in check_redis_connection()


class TestSaveTemplate:
    """Tests for the Redis template persistence helper."""

    @mock.patch("celery_client._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Returns error message when Redis is unavailable."""
        mock_get.return_value = None
        msg = save_template("content")
        assert msg is not None
        assert "offline" in msg

    @mock.patch("celery_client._get_hm")
    def test_success(self, mock_get: mock.Mock) -> None:
        """Returns None on success; stores dict directly."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        yaml_in = "model: yolov8n.pt\ntype: yolo\n"
        assert save_template(yaml_in) is None
        _, kwargs = mock_hm.create_hash.call_args
        assert kwargs["hash_name"] == mock.ANY
        assert kwargs["key"] == "template"
        assert kwargs["value"] == {"model": "yolov8n.pt", "type": "yolo"}

    @mock.patch("celery_client._get_hm")
    def test_yaml_parse_error(self, mock_get: mock.Mock) -> None:
        """Returns error on invalid YAML."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        msg = save_template("{bad: yaml: }}")
        assert msg is not None
        assert "YAML parse error" in msg

    @mock.patch("celery_client._get_hm")
    def test_redis_exception(self, mock_get: mock.Mock) -> None:
        """Returns error message on Redis exception."""
        mock_hm = mock.Mock()
        mock_hm.create_hash.side_effect = ValueError("bad")
        mock_get.return_value = mock_hm
        msg = save_template("model: x\ntype: y\n")
        assert msg is not None
        assert "Redis error" in msg

    @mock.patch("celery_client._get_hm")
    def test_non_dict_fallback(self, mock_get: mock.Mock) -> None:
        """Non-dict YAML (scalar) falls back to empty dict."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        assert save_template("just a string") is None
        _, kwargs = mock_hm.create_hash.call_args
        assert kwargs["value"] == {}


class TestSaveWithFeedback:
    """Tests for the user-facing save wrapper."""

    @mock.patch("ui.handlers.save_template")
    def test_success(self, mock_save: mock.Mock) -> None:
        """Returns a green status message on success."""
        mock_save.return_value = None
        out = _save_with_feedback("anything")
        assert "🟢" in out
        assert "saved" in out.lower()

    @mock.patch("ui.handlers.save_template")
    def test_error_passthrough(self, mock_save: mock.Mock) -> None:
        """Passes through the error message from save_template."""
        mock_save.return_value = "🔴 Redis offline"
        assert _save_with_feedback("x") == "🔴 Redis offline"


class TestLoadTemplate:
    """Tests for the Redis template loading helper."""

    @mock.patch("templates._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Falls back to the bundled classification template when Redis is down."""
        mock_get.return_value = None
        out = load_template()
        assert "yolov8n-cls.pt" in out

    @mock.patch("templates._get_hm")
    def test_new_format_dict(self, mock_get: mock.Mock) -> None:
        """Returns YAML dumped from a stored dict (new format)."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = {"model": "yolov8n.pt", "type": "yolo"}
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: yolov8n.pt" in out
        assert "type: yolo" in out

    @mock.patch("templates._get_hm")
    def test_legacy_json_string(self, mock_get: mock.Mock) -> None:
        """Returns YAML from a legacy JSON-string value."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = json.dumps({"model": "m", "type": "t"})
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: m" in out
        assert "type: t" in out

    @mock.patch("templates._get_hm")
    def test_legacy_yaml_string(self, mock_get: mock.Mock) -> None:
        """Returns raw YAML string (oldest format) as-is."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = "model: legacy\ntype: old\n"
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: legacy" in out
        assert "type: old" in out


class TestNamedUserTemplates:
    """Tests for user-saved, named templates (save/list/load)."""

    @mock.patch("templates._get_hm")
    def test_save_requires_name(self, mock_get: mock.Mock) -> None:
        """Saving without a name returns a warning."""
        err = save_user_template("  ", "model: m\ntype: yolo")
        assert "nombre" in err

    @mock.patch("templates._get_hm")
    def test_save_invalid_yaml(self, mock_get: mock.Mock) -> None:
        """Invalid YAML returns an error and does not call Redis."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        err = save_user_template("x", "{bad: yaml: }}")
        assert "🔴" in err
        mock_hm.create_hash.assert_not_called()

    @mock.patch("templates._get_hm")
    def test_save_success(self, mock_get: mock.Mock) -> None:
        """Valid YAML is persisted under the given name."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        err = save_user_template("my_tpl", "model: m\ntype: yolo")
        assert err is None
        mock_hm.create_hash.assert_called_once()
        call = mock_hm.create_hash.call_args[1]
        assert call["key"] == "my_tpl"
        assert call["value"] == {"model": "m", "type": "yolo"}

    @mock.patch("templates._get_hm")
    def test_list_saved(self, mock_get: mock.Mock) -> None:
        """list_user_templates returns sorted names."""
        mock_hm = mock.Mock()
        mock_hm.read_all_hash.return_value = {"b": 1, "a": 2, "c": 3}
        mock_get.return_value = mock_hm
        assert list_user_templates() == ["a", "b", "c"]

    @mock.patch("templates._get_hm")
    def test_list_offline(self, mock_get: mock.Mock) -> None:
        """Returns [] when Redis is offline."""
        mock_get.return_value = None
        assert list_user_templates() == []

    @mock.patch("templates._get_hm")
    def test_load_named(self, mock_get: mock.Mock) -> None:
        """load_user_template returns the stored YAML."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = {"model": "yolov8n.pt", "type": "yolo"}
        mock_get.return_value = mock_hm
        out = load_user_template("my_tpl")
        assert "model: yolov8n.pt" in out
        mock_hm.read_hash.assert_called_once_with(
            hash_name=ANY, key="my_tpl"
        )

    @mock.patch("templates._get_hm")
    def test_load_empty_name_falls_back(self, mock_get: mock.Mock) -> None:
        """Empty name loads the default last-saved template."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = {"model": "fallback", "type": "yolo"}
        mock_get.return_value = mock_hm
        out = load_user_template("")
        assert "fallback" in out

    def test_save_named_feedback_success(self) -> None:
        """The UI feedback wrapper returns success + refreshed dropdown."""
        with mock.patch(
            "ui.handlers.save_user_template", return_value=None
        ), mock.patch("ui.handlers.list_user_templates", return_value=["a"]):
            msg, dropdown = save_named_template_with_feedback("a", "model: m")
            assert "🟢" in msg
            assert dict(dropdown)["choices"] == ["a"]

    def test_load_selected(self) -> None:
        """load_selected_template delegates to load_user_template."""
        with mock.patch(
            "ui.handlers.load_user_template", return_value="model: m"
        ):
            assert load_selected_template("a") == "model: m"


class TestToggleTaskIdEdit:
    """Tests for the read-only Task ID toggle."""

    def test_locks_when_editing(self) -> None:
        """Switching from editing locks the box and restores the pencil."""
        task, btn, state = toggle_task_id_edit(True)
        assert dict(task)["interactive"] is False
        assert dict(btn)["value"] == "✏️ Editar"
        assert state is False

    def test_unlocks_when_locked(self) -> None:
        """Switching from locked enables editing and shows the lock button."""
        task, btn, state = toggle_task_id_edit(False)
        assert dict(task)["interactive"] is True
        assert dict(btn)["value"] == "🔒 Bloquear"
        assert state is True


# ── telemetry ────────────────────────────────────────────────────────


class TestTaskStatus:
    """Tests for the auto-refreshing task status helpers."""

    def test_empty_task_id_is_idle(self) -> None:
        """An empty task id returns idle placeholders, not an error."""
        status, llm = check_task_status("")
        assert "No active task" in status
        assert "Waiting for a training task" in llm

    @mock.patch("telemetry.AsyncResult")
    def test_pending_state(self, mock_async: mock.Mock) -> None:
        """PENDING tasks show a waiting LLM state."""
        mock_res = mock.Mock()
        mock_res.state = "PENDING"
        mock_res.info = None
        mock_async.return_value = mock_res
        status, llm = check_task_status("abc")
        assert "PENDING" in status
        assert "Training in progress" in llm

    @mock.patch("telemetry.AsyncResult")
    def test_success_with_report(self, mock_async: mock.Mock) -> None:
        """SUCCESS tasks surface the LLM report when present."""
        mock_res = mock.Mock()
        mock_res.state = "SUCCESS"
        mock_res.info = {"llm_report": "Great training!"}
        mock_async.return_value = mock_res
        _status, llm = check_task_status("abc")
        assert "Great training!" in llm

    @mock.patch("telemetry.AsyncResult")
    def test_failure_state(self, mock_async: mock.Mock) -> None:
        """FAILURE tasks surface the error."""
        mock_res = mock.Mock()
        mock_res.state = "FAILURE"
        mock_res.info = {"exc_type": "ValueError"}
        mock_async.return_value = mock_res
        _status, llm = check_task_status("abc")
        assert "Training failed" in llm


class TestResultsDownload:
    """Tests for the ZIP download gating."""

    def test_results_available_false_when_missing(self, tmp_path) -> None:
        """results_available returns False when nothing has been written."""
        with mock.patch("telemetry.RESULTS_DIR", str(tmp_path)):
            assert results_available() is False

    def test_get_download_state_disabled(self, tmp_path) -> None:
        """The download button is disabled while there are no results."""
        with mock.patch("telemetry.RESULTS_DIR", str(tmp_path)):
            assert get_download_state() == {"interactive": False}

    def test_get_download_state_enabled(self, tmp_path) -> None:
        """The download button is enabled once results.json exists."""
        (tmp_path / "results.json").write_text('{"accuracy": 0.7}')
        with mock.patch("telemetry.RESULTS_DIR", str(tmp_path)):
            assert get_download_state() == {"interactive": True}

    def test_get_results_zip_creates_archive(self, tmp_path) -> None:
        """get_results_zip archives the whole results directory."""
        (tmp_path / "results.json").write_text('{"accuracy": 0.7}')
        (tmp_path / "evaluation_metrics").mkdir()
        (tmp_path / "evaluation_metrics" / "results.png").write_bytes(b"png")
        with (
            mock.patch("telemetry.RESULTS_DIR", str(tmp_path)),
            mock.patch("telemetry.ZIP_PATH", str(tmp_path / "training_results.zip")),
        ):
            zip_path = telemetry_get_results_zip()
        assert zip_path is not None
        import zipfile

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any(n.endswith("results.json") for n in names)
        assert any(n.endswith("results.png") for n in names)

    def test_get_results_zip_none_when_missing(self, tmp_path) -> None:
        """get_results_zip returns None when there are no results."""
        with mock.patch("telemetry.RESULTS_DIR", str(tmp_path)):
            assert telemetry_get_results_zip() is None


# ── ui.handlers ──────────────────────────────────────────────────────


class TestHandleTrainClick:
    """Tests for the train-click handler (auto task-id + tab switch)."""

    @mock.patch("ui.handlers.celery_client.validate_and_launch")
    def test_extracts_task_id_and_switches_tab(
        self, mock_launch: mock.Mock
    ) -> None:
        """A dispatched task auto-fills the Task ID and switches to Monitoring."""
        mock_launch.return_value = "🚀 **Training Task Sent!**\n\n🆔 **Task ID:** `abc-123`"
        msg, task_id, tab_update = handle_train_click("yaml")
        assert task_id == "abc-123"
        assert dict(tab_update).get("selected") == "monitoring_tab"

    @mock.patch("ui.handlers.celery_client.validate_and_launch")
    def test_validation_error_no_switch(self, mock_launch: mock.Mock) -> None:
        """An invalid config does not switch tabs."""
        mock_launch.return_value = "❌ Missing mandatory key: 'model'"
        _msg, task_id, tab_update = handle_train_click("bad")
        assert task_id == ""
        assert "selected" not in dict(tab_update)
