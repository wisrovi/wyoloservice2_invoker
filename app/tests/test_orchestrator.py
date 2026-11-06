"""Unit tests for the Hybrid Orchestrator module."""

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from utils.orchestrator import (
    DockerOrchestrator,
    KubernetesOrchestrator,
    get_gpu_utilization,
    get_optimal_gpu_device,
    get_orchestrator,
    is_k8s_environment,
    sanitize_k8s_name,
)


def mock_k8s_get_side_effect(url: str, mock_logs: Any, mock_status: Any, **kwargs: Any) -> Any:
    """Return mock logs or mock status based on request URL."""
    if "log" in url:
        return mock_logs
    return mock_status


def mock_k8s_dynamic_get(
    url: str, log_streams: list, statuses: list, fallback_stream: Any, fallback_status: Any, **kwargs: Any
) -> Any:
    """Return log streams or pod statuses dynamically from lists."""
    if "log" in url:
        return log_streams.pop(0) if log_streams else fallback_stream
    return statuses.pop(0) if statuses else fallback_status


class TestOrchestrator:
    """Test suite for orchestrator components."""

    def test_sanitize_k8s_name(self):
        """Validates DNS-1123 name sanitization for Kubernetes resources."""
        assert sanitize_k8s_name("Trial_01_User@Host") == "trial-01-user-host"
        assert sanitize_k8s_name("---Invalid---Start---") == "invalid-start"
        assert sanitize_k8s_name("") == "wyolo-task"
        long_name = "a" * 100
        assert len(sanitize_k8s_name(long_name)) == 63

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s"}, clear=False)
    def test_is_k8s_environment_via_env(self):
        """Validates detection of Kubernetes mode via ORCHESTRATOR environment variable."""
        assert is_k8s_environment() is True

    @patch.dict(os.environ, {"ORCHESTRATOR": "docker"}, clear=False)
    def test_is_docker_environment_via_env(self):
        """Validates detection of Docker mode via ORCHESTRATOR=docker."""
        assert is_k8s_environment() is False

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s"}, clear=False)
    def test_get_orchestrator_k8s(self):
        """Validates that get_orchestrator returns KubernetesOrchestrator when in K8s mode."""
        orch = get_orchestrator({})
        assert isinstance(orch, KubernetesOrchestrator)

    @patch.dict(os.environ, {"ORCHESTRATOR": "docker"}, clear=False)
    @patch("docker.from_env")
    def test_get_orchestrator_docker(self, mock_docker_from_env):
        """Validates that get_orchestrator returns DockerOrchestrator when in Docker mode."""
        mock_docker_from_env.return_value = MagicMock()
        orch = get_orchestrator({})
        assert isinstance(orch, DockerOrchestrator)

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s", "WORKER_HOSTNAME": "node-test-01"}, clear=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_k8s_orchestrator_start_executor(self, mock_del, mock_get, mock_post, tmp_path):
        """Validates Kubernetes Pod creation and lifecycle in KubernetesOrchestrator."""
        mock_post_resp = MagicMock(status_code=201)
        mock_post.return_value = mock_post_resp

        mock_get_status = MagicMock(status_code=200)
        mock_get_status.json.return_value = {
            "status": {
                "phase": "Succeeded",
                "containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}],
            }
        }

        mock_get_logs = MagicMock(status_code=200)
        mock_get_logs.iter_lines.return_value = [b"[INFO] Training finished successfully."]
        mock_get_logs.text = "Epoch 10/10 1.2G"

        mock_get.side_effect = lambda url, **kw: mock_k8s_get_side_effect(url, mock_get_logs, mock_get_status, **kw)
        mock_del.return_value = MagicMock(status_code=200)

        orch = KubernetesOrchestrator()
        exit_code = orch.start_executor(
            image_name="test_image:v1.0.0",
            executor_name="test-trial-01",
            environments={"TRIAL_ID": "1"},
            volumes={},
            command_str="echo test",
            shm_size_bytes=16 * 1024**3,
            mem_limit=32 * 1024**3,
            cpu_limit=4.0,
            results_dir=str(tmp_path),
            timeout_seconds=60,
            invoker_name="test-invoker",
            redis_client=None,
        )

        assert exit_code == 0
        assert mock_post.called

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s", "WORKER_HOSTNAME": "node-test-01"}, clear=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_k8s_orchestrator_terminal_state_and_log_reconnect(self, mock_del, mock_get, mock_post, tmp_path):
        """Validates that K8s orchestrator reconnects logs and waits for terminal state."""
        mock_post.return_value = MagicMock(status_code=201)
        mock_del.return_value = MagicMock(status_code=200)

        status_running = MagicMock(status_code=200)
        status_running.json.return_value = {
            "status": {
                "phase": "Running",
                "containerStatuses": [{"state": {"running": {"startedAt": "2026-10-20T08:00:00Z"}}}],
            }
        }

        status_succeeded = MagicMock(status_code=200)
        status_succeeded.json.return_value = {
            "status": {
                "phase": "Succeeded",
                "containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}],
            }
        }

        stream_1 = MagicMock(status_code=200)
        stream_1.iter_lines.return_value = [b"[INFO] Epoch 1/10"]
        stream_1.__enter__ = MagicMock(return_value=stream_1)
        stream_1.__exit__ = MagicMock(return_value=False)

        stream_2 = MagicMock(status_code=200)
        stream_2.iter_lines.return_value = [b"[INFO] Epoch 10/10 Finished"]
        stream_2.__enter__ = MagicMock(return_value=stream_2)
        stream_2.__exit__ = MagicMock(return_value=False)

        log_streams = [stream_1, stream_2]
        statuses = [status_running, status_running, status_succeeded]

        mock_get.side_effect = lambda url, **kw: mock_k8s_dynamic_get(
            url, log_streams, statuses, stream_2, status_succeeded, **kw
        )

        orch = KubernetesOrchestrator()
        exit_code = orch.start_executor(
            image_name="test_image:v1.0.0",
            executor_name="test-trial-02",
            environments={"TRIAL_ID": "2"},
            volumes={},
            command_str="echo test",
            shm_size_bytes=16 * 1024**3,
            mem_limit=32 * 1024**3,
            cpu_limit=4.0,
            results_dir=str(tmp_path),
            timeout_seconds=60,
            invoker_name="test-invoker",
            redis_client=None,
        )

        assert exit_code == 0
        assert mock_del.called

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s", "WORKER_HOSTNAME": "node-test-01"}, clear=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_k8s_orchestrator_failed_state(self, mock_del, mock_get, mock_post, tmp_path):
        """Validates that K8s orchestrator captures failure state and returns non-zero exit code."""
        mock_post.return_value = MagicMock(status_code=201)
        mock_del.return_value = MagicMock(status_code=200)

        status_failed = MagicMock(status_code=200)
        status_failed.json.return_value = {
            "status": {
                "phase": "Failed",
                "message": "OOMKilled container",
                "containerStatuses": [{"state": {"terminated": {"exitCode": 137}}}],
            }
        }

        mock_logs = MagicMock(status_code=200)
        mock_logs.iter_lines.return_value = [b"[ERROR] CUDA Out of memory"]
        mock_logs.text = "[ERROR] CUDA Out of memory"
        mock_logs.__enter__ = MagicMock(return_value=mock_logs)
        mock_logs.__exit__ = MagicMock(return_value=False)

        mock_get.side_effect = lambda url, **kw: mock_k8s_get_side_effect(url, mock_logs, status_failed, **kw)

        orch = KubernetesOrchestrator()
        exit_code = orch.start_executor(
            image_name="test_image:v1.0.0",
            executor_name="test-trial-fail",
            environments={"TRIAL_ID": "3"},
            volumes={},
            command_str="echo fail",
            shm_size_bytes=16 * 1024**3,
            mem_limit=32 * 1024**3,
            cpu_limit=4.0,
            results_dir=str(tmp_path),
            timeout_seconds=60,
            invoker_name="test-invoker",
            redis_client=None,
        )

        assert exit_code == 1
        assert mock_del.called
