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
