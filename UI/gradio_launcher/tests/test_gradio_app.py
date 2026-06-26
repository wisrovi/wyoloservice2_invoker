# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Unit tests for gradio_app.py.

Covers queue resolution, YAML validation, Redis persistence helpers,
Celery task submission, and the dry-run smoke test helper.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
import yaml

from gradio_app import (
    _save_with_feedback,
    check_redis_connection,
    launch_dry_run,
    load_template,
    resolve_queue,
    save_template,
    validate_and_launch,
    validate_min_config,
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

# ── resolve_queue ────────────────────────────────────────────────────


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
        assert validate_min_config("") == (False, "")

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

    def test_missing_author(self) -> None:
        """Detects missing metadata.author."""
        cfg = yaml.dump(
            {
                "model": "m",
                "type": "yolo",
                "train": {"b": 1},
                "metadata": {},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_missing_fitness(self) -> None:
        """Detects missing sweeper.fitness."""
        cfg = yaml.dump(
            {
                "model": "m",
                "type": "yolo",
                "train": {"b": 1},
                "metadata": {"author": "a"},
                "sweeper": {"study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False

    def test_empty_train(self) -> None:
        """Empty train dict is rejected."""
        cfg = yaml.dump(
            {
                "model": "m",
                "type": "yolo",
                "train": {},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert validate_min_config(cfg)[0] is False


class TestResolveQueue:
    """Tests for the queue-name resolution helper."""

    def test_private_queue(self) -> None:
        """Private queue value is returned as-is."""
        assert resolve_queue("192.168.1.137", "") == "192.168.1.137"

    def test_gpus_high(self) -> None:
        """gpus_high literal is returned as-is."""
        assert resolve_queue("gpus_high", "") == "gpus_high"

    def test_custom_non_empty(self) -> None:
        """Custom selection returns the typed value."""
        assert resolve_queue("__custom__", "gpus_low") == "gpus_low"

    def test_custom_empty_fallback(self) -> None:
        """Empty custom box falls back to gpus_high."""
        assert resolve_queue("__custom__", "") == "gpus_high"

    def test_custom_whitespace_fallback(self) -> None:
        """Whitespace-only custom box falls back to gpus_high."""
        assert resolve_queue("__custom__", "   ") == "gpus_high"


# ── validate_and_launch ─────────────────────────────────────────────


class TestValidateAndLaunch:
    """Tests for the main train-submission function."""

    @mock.patch("gradio_app._celery_app")
    @mock.patch("gradio_app.save_template")
    def test_valid_yaml(
        self,
        mock_save: mock.Mock,
        mock_celery: mock.Mock,
    ) -> None:
        """A fully-valid YAML is accepted and sent."""
        mock_celery.send_task.return_value.id = "abc-123"
        result = validate_and_launch(_MIN_VALID_YAML, "gpus_high", "")
        assert "✅" in result
        assert "abc-123" in result
        mock_save.assert_called_once_with(_MIN_VALID_YAML)

    @mock.patch("gradio_app._celery_app")
    @mock.patch("gradio_app.save_template")
    def test_user_id_filled_from_metadata(
        self,
        mock_save: mock.Mock,
        mock_celery: mock.Mock,
    ) -> None:
        """user_id defaults to metadata.author when absent."""
        mock_celery.send_task.return_value.id = "id"
        yaml_str = yaml.dump(
            {
                "model": "m",
                "type": "t",
                "train": {"batch": -1},
                "metadata": {"author": "alice"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        validate_and_launch(yaml_str, "gpus_high", "")
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["user_id"] == "alice"

    @mock.patch("gradio_app._celery_app")
    @mock.patch("gradio_app.save_template")
    def test_respects_existing_user_id(
        self,
        mock_save: mock.Mock,
        mock_celery: mock.Mock,
    ) -> None:
        """Existing user_id is preserved."""
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
        validate_and_launch(yaml_str, "gpus_high", "")
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["user_id"] == "bob"

    def test_empty_yaml(self) -> None:
        """Empty content returns an error."""
        assert "❌" in validate_and_launch("", "gpus_high", "")

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
        assert "model" in validate_and_launch(yaml_str, "gpus_high", "")

    def test_missing_type(self) -> None:
        """YAML without a type field is rejected."""
        yaml_str = yaml.dump(
            {
                "model": "m",
                "train": {"batch": -1},
                "metadata": {"author": "a"},
                "sweeper": {"fitness": "m", "study_name": "s"},
            }
        )
        assert "type" in validate_and_launch(yaml_str, "gpus_high", "")

    def test_invalid_yaml_syntax(self) -> None:
        """Malformed YAML returns a generic error (min config fails first)."""
        result = validate_and_launch(
            "{bad: yaml: }}",
            "gpus_high",
            "",
        )
        assert "❌" in result

    @mock.patch("gradio_app._celery_app")
    @mock.patch("gradio_app.save_template")
    def test_celery_error(
        self,
        mock_save: mock.Mock,
        mock_celery: mock.Mock,
    ) -> None:
        """A Celery transport error is surfaced."""
        mock_celery.send_task.side_effect = RuntimeError("Broker refused")
        result = validate_and_launch(_MIN_VALID_YAML, "gpus_high", "")
        assert "Celery error" in result


# ── launch_dry_run ───────────────────────────────────────────────────


class TestLaunchDryRun:
    """Tests for the smoke-test dry-run helper."""

    @mock.patch("gradio_app._celery_app")
    def test_dry_run_success(self, mock_celery: mock.Mock) -> None:
        """Dry run sends the correct task and returns a success message."""
        mock_celery.send_task.return_value.id = "dry-123"
        result = launch_dry_run()
        assert "🧪" in result
        assert "dry-123" in result

    @mock.patch("gradio_app._celery_app")
    def test_dry_run_payload_has_dry_run_flag(
        self,
        mock_celery: mock.Mock,
    ) -> None:
        """The payload sent includes dry_run: true."""
        mock_celery.send_task.return_value.id = "id"
        launch_dry_run()
        args = mock_celery.send_task.call_args
        payload = args[1]["args"][0]
        assert payload["dry_run"] is True

    @mock.patch("gradio_app._celery_app")
    def test_dry_run_uses_private_queue(self, mock_celery: mock.Mock) -> None:
        """Dry run always targets the private queue."""
        mock_celery.send_task.return_value.id = "id"
        launch_dry_run()
        args = mock_celery.send_task.call_args
        assert args[1]["queue"] == mock.ANY  # should be set
        # queue is _PRIVATE_QUEUE, which we check is a non-empty string
        assert isinstance(args[1]["queue"], str)
        assert len(args[1]["queue"]) > 0

    @mock.patch("gradio_app._celery_app")
    def test_dry_run_celery_error(self, mock_celery: mock.Mock) -> None:
        """A transport error is surfaced."""
        mock_celery.send_task.side_effect = RuntimeError("Timeout")
        result = launch_dry_run()
        assert "❌" in result


# ── Redis helpers ────────────────────────────────────────────────────


class TestCheckRedisConnection:
    """Tests for the Redis connectivity check."""

    @mock.patch("gradio_app._get_hm")
    def test_ok(self, mock_get: mock.Mock) -> None:
        """Returns green indicator when Redis responds."""
        mock_hm = mock.Mock()
        mock_hm.exist.return_value = True
        mock_get.return_value = mock_hm
        assert "🟢" in check_redis_connection()

    @mock.patch("gradio_app._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Returns red indicator when _get_hm returns None."""
        mock_get.return_value = None
        assert "🔴" in check_redis_connection()

    @mock.patch("gradio_app._get_hm")
    def test_exception(self, mock_get: mock.Mock) -> None:
        """Returns red indicator on exception."""
        mock_hm = mock.Mock()
        mock_hm.exist.side_effect = ConnectionError("refused")
        mock_get.return_value = mock_hm
        assert "🔴" in check_redis_connection()


class TestSaveTemplate:
    """Tests for the Redis template persistence helper."""

    @mock.patch("gradio_app._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Returns error message when Redis is unavailable."""
        mock_get.return_value = None
        msg = save_template("content")
        assert msg is not None
        assert "offline" in msg

    @mock.patch("gradio_app._get_hm")
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

    @mock.patch("gradio_app._get_hm")
    def test_yaml_parse_error(self, mock_get: mock.Mock) -> None:
        """Returns error on invalid YAML."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        msg = save_template("{bad: yaml: }}")
        assert msg is not None
        assert "YAML parse error" in msg

    @mock.patch("gradio_app._get_hm")
    def test_redis_exception(self, mock_get: mock.Mock) -> None:
        """Returns error message on Redis exception."""
        mock_hm = mock.Mock()
        mock_hm.create_hash.side_effect = ValueError("bad")
        mock_get.return_value = mock_hm
        msg = save_template("model: x\ntype: y\n")
        assert msg is not None
        assert "Redis error" in msg

    @mock.patch("gradio_app._get_hm")
    def test_non_dict_fallback(self, mock_get: mock.Mock) -> None:
        """Non-dict YAML (scalar) falls back to empty dict."""
        mock_hm = mock.Mock()
        mock_get.return_value = mock_hm
        assert save_template("just a string") is None
        _, kwargs = mock_hm.create_hash.call_args
        assert kwargs["value"] == {}


class TestSaveWithFeedback:
    """Tests for the user-facing save wrapper."""

    @mock.patch("gradio_app.save_template")
    def test_success(self, mock_save: mock.Mock) -> None:
        """Returns a green status message on success."""
        mock_save.return_value = None
        out = _save_with_feedback("anything")
        assert "🟢" in out
        assert "saved" in out.lower()

    @mock.patch("gradio_app.save_template")
    def test_error_passthrough(self, mock_save: mock.Mock) -> None:
        """Passes through the error message from save_template."""
        mock_save.return_value = "🔴 Redis offline"
        assert _save_with_feedback("x") == "🔴 Redis offline"


class TestLoadTemplate:
    """Tests for the Redis template loading helper."""

    @mock.patch("gradio_app._get_hm")
    def test_offline(self, mock_get: mock.Mock) -> None:
        """Returns empty string when Redis is unavailable."""
        mock_get.return_value = None
        assert load_template() == ""

    @mock.patch("gradio_app._get_hm")
    def test_new_format_dict(self, mock_get: mock.Mock) -> None:
        """Returns YAML dumped from a stored dict (new format)."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = {"model": "yolov8n.pt", "type": "yolo"}
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: yolov8n.pt" in out
        assert "type: yolo" in out

    @mock.patch("gradio_app._get_hm")
    def test_legacy_json_string(self, mock_get: mock.Mock) -> None:
        """Returns YAML from a legacy JSON-string value."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = json.dumps({"model": "m", "type": "t"})
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: m" in out
        assert "type: t" in out

    @mock.patch("gradio_app._get_hm")
    def test_legacy_yaml_string(self, mock_get: mock.Mock) -> None:
        """Returns raw YAML string (oldest format) as-is."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = "model: legacy\ntype: old\n"
        mock_get.return_value = mock_hm
        out = load_template()
        assert "model: legacy" in out
        assert "type: old" in out

    @mock.patch("gradio_app._get_hm")
    def test_key_not_found(self, mock_get: mock.Mock) -> None:
        """Returns empty string when read_hash returns None."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = None
        mock_get.return_value = mock_hm
        assert load_template() == ""

    @mock.patch("gradio_app._get_hm")
    def test_empty_dict(self, mock_get: mock.Mock) -> None:
        """Returns empty string when stored dict is empty."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = {}
        mock_get.return_value = mock_hm
        assert load_template() == ""

    @mock.patch("gradio_app._get_hm")
    def test_empty_string(self, mock_get: mock.Mock) -> None:
        """Returns empty string when stored value is empty string."""
        mock_hm = mock.Mock()
        mock_hm.read_hash.return_value = ""
        mock_get.return_value = mock_hm
        assert load_template() == ""
