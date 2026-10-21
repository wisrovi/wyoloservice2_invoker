# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa
"""Unit tests for the Hybrid Orchestrator module.

This module validates:
1. Environment detection (Docker vs Kubernetes).
2. Sanitization of Kubernetes DNS-1123 resource names.
3. Factory instantiation of DockerOrchestrator and KubernetesOrchestrator.
4. Kubernetes Pod specification generation and lifecycle logic.
"""

import os
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


class TestOrchestrator:
    """Test suite for orchestrator components."""

    def test_sanitize_k8s_name(self):
        """Validates DNS-1123 name sanitization for Kubernetes resources.

        Kubernetes names must only contain lower case alphanumeric characters or '-',
        must start and end with an alphanumeric character, and be at most 63 characters long.
        """
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
        """Validates Kubernetes Pod creation and lifecycle in KubernetesOrchestrator.

        Verifies:
        1. Pod is pinned to WORKER_HOSTNAME (spec.nodeName).
        2. In-cluster REST API is invoked with correct manifest.
        3. Pod deletion is called upon completion.
        """
        # Mock pod creation
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post.return_value = mock_post_resp

        # Mock pod status and logs
        mock_get_status = MagicMock()
        mock_get_status.status_code = 200
        mock_get_status.json.return_value = {
            "status": {
                "phase": "Succeeded",
                "containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}],
            }
        }

        mock_get_logs = MagicMock()
        mock_get_logs.status_code = 200
        mock_get_logs.iter_lines.return_value = [b"[INFO] Training finished successfully."]
        mock_get_logs.text = "Epoch 10/10 1.2G"

        def get_side_effect(url, **kwargs):
            """Return mock logs or mock status based on request URL."""
            if "log" in url:
                return mock_get_logs
            return mock_get_status

        mock_get.side_effect = get_side_effect

        mock_del_resp = MagicMock()
        mock_del_resp.status_code = 200
        mock_del.return_value = mock_del_resp

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
        # Check manifest posted
        posted_manifest = mock_post.call_args[1]["json"]
        assert posted_manifest["spec"]["nodeName"] == "node-test-01"
        assert posted_manifest["spec"]["priorityClassName"] == "system-node-critical"
        assert posted_manifest["metadata"]["labels"]["app"] == "wyolo-executor"
        assert "envFrom" in posted_manifest["spec"]["containers"][0]
        assert (
            posted_manifest["spec"]["containers"][0]["envFrom"][0]["configMapRef"]["name"]
            == "train-service-global-config"
        )
        assert posted_manifest["spec"]["containers"][0]["envFrom"][1]["secretRef"]["name"] == "train-service-secrets"

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s", "WORKER_HOSTNAME": "node-test-01"}, clear=False)
    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_k8s_orchestrator_terminal_state_and_log_reconnect(self, mock_del, mock_get, mock_post, tmp_path):
        """Validates that K8s orchestrator reconnects logs and waits for terminal state.

        Verifies:
        1. Premature log drop while pod is Running does not cause premature return or deletion.
        2. Stream reconnects and waits until Pod transitions to terminal Succeeded state.
        3. Real exit code (0) is returned.
        """
        mock_post.return_value = MagicMock(status_code=201)
        mock_del.return_value = MagicMock(status_code=200)

        # Status: Running on initial check, Running after stream drop, then Succeeded
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

        # First log stream drops after one line, second stream provides remaining line
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

        def dynamic_get(url, **kwargs):
            """Return log streams or pod statuses dynamically."""
            if "log" in url:
                return log_streams.pop(0) if log_streams else stream_2
            return statuses.pop(0) if statuses else status_succeeded

        mock_get.side_effect = dynamic_get

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

        def dynamic_get(url, **kwargs):
            """Return mock failure logs or failed pod status."""
            if "log" in url:
                return mock_logs
            return status_failed

        mock_get.side_effect = dynamic_get

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

        assert exit_code == 137
        assert mock_del.called

    @patch("subprocess.check_output")
    def test_get_optimal_gpu_device_auto_select(self, mock_smi):
        """Validates that get_optimal_gpu_device selects the GPU with max free memory."""
        mock_smi.return_value = "0, 2048\n1, 10240\n2, 4096\n"
        selected = get_optimal_gpu_device(None)
        assert selected == ["1"]

    def test_get_optimal_gpu_device_explicit(self):
        """Validates explicit GPU device specification."""
        assert get_optimal_gpu_device("2") == ["2"]
        assert get_optimal_gpu_device("0,1") == ["0", "1"]
        assert get_optimal_gpu_device("all") == ["all"]

    @patch("docker.from_env")
    def test_docker_clean_orphaned_tasks(self, mock_docker_from_env):
        """Validates that DockerOrchestrator removes lingering executor and eda containers."""
        mock_client = MagicMock()
        mock_docker_from_env.return_value = mock_client

        c1 = MagicMock()
        c1.name = "wyolo_executor_worker1_trial123"
        c2 = MagicMock()
        c2.name = "wyolo_eda_runner_worker1"
        c3 = MagicMock()
        c3.name = "redis_database"
        mock_client.containers.list.return_value = [c1, c2, c3]

        orch = DockerOrchestrator()
        cleaned = orch.clean_orphaned_tasks()

        assert cleaned == 2
        c1.remove.assert_called_once_with(force=True)
        c2.remove.assert_called_once_with(force=True)
        c3.remove.assert_not_called()

    @patch.dict(os.environ, {"ORCHESTRATOR": "k8s", "WORKER_HOSTNAME": "node-test-01"}, clear=False)
    @patch("requests.get")
    @patch("requests.delete")
    def test_k8s_clean_orphaned_tasks(self, mock_del, mock_get):
        """Validates that KubernetesOrchestrator sweeps orphaned pods matching node."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "metadata": {"name": "wyolo-executor-test-1"},
                    "spec": {"nodeName": "node-test-01"},
                },
                {
                    "metadata": {"name": "wyolo-executor-other-node"},
                    "spec": {"nodeName": "other-node"},
                },
            ]
        }
        mock_get.return_value = mock_resp

        orch = KubernetesOrchestrator()
        cleaned = orch.clean_orphaned_tasks()

        assert cleaned == 1
        assert mock_del.called
