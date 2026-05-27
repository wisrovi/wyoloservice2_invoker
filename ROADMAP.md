# Roadmap - GPU Invoker (Hive)

## Q3 2026: Resource Management
- **MIG Support**: Slice A100/H100 GPUs into multiple instances.
- **Resource Quotas**: Hard limits on disk and network per trial.

## Q4 2026: Resiliency
- **Self-Healing**: Automated restart of the Celery worker on CUDA error.
- **Local Cache**: Persistent dataset caching to reduce Samba traffic.
