"""Unified dataset analyzer facade for classification, detection, and segmentation."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

from .classification_analyzer import ClassificationAnalyzer
from .detection_analyzer import DetectionAnalyzer
from .segmentation_analyzer import SegmentationAnalyzer


class DatasetAnalyzer:
    """Analyze a dataset directory and automatically dispatch to domain-specific analyzer."""

    def analyze(self, dataset_path: str | Path) -> dict[str, Any]:
        """Analyze a dataset path and compute summary statistics.

        Args:
            dataset_path (Union[str, Path]): Filesystem path to dataset.

        Returns:
            Dict[str, Any]: Formatted statistics dictionary.
        """
        ds_path = Path(dataset_path)
        ds_type = self.detect_dataset_type(ds_path)
        class_names = self.load_class_names(ds_path)

        if ds_type == "classification":
            return ClassificationAnalyzer().analyze(ds_path)
        if ds_type == "detection":
            return DetectionAnalyzer().analyze(ds_path, class_names)
        if ds_type == "segmentation":
            return SegmentationAnalyzer().analyze(ds_path, class_names)
        return {"dataset_type": "unknown", "total_images": 0}

    def detect_dataset_type(self, dataset_path: str | Path) -> str:
        """Detect the dataset task type based on directory layout and label formats.

        Args:
            dataset_path (Union[str, Path]): Path to inspect.

        Returns:
            str: Task type string ('classification', 'detection', 'segmentation', or 'unknown').
        """
        ds_path = Path(dataset_path)
        if (ds_path / "train").exists():
            subdirs = [p for p in (ds_path / "train").iterdir() if p.is_dir()]
            subdir_names = {p.name for p in subdirs}
            if subdir_names and not subdir_names.intersection({"images", "labels"}):
                return "classification"

        yaml_files = list(ds_path.glob("*.yaml")) + list(ds_path.glob("*.yml"))
        if yaml_files:
            return self.detect_yolo_type(ds_path)
        return "unknown"

    def detect_yolo_type(self, dataset_path: str | Path) -> str:
        """Inspect YOLO label text files to differentiate detection from segmentation.

        Args:
            dataset_path (Union[str, Path]): Root path of dataset.

        Returns:
            str: 'segmentation', 'detection', or 'unknown'.
        """
        ds_path = Path(dataset_path)
        for label_file in ds_path.rglob("labels/**/*.txt"):
            try:
                with open(label_file, encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) > 5:
                            return "segmentation"
                        if len(parts) == 5:
                            return "detection"
            except Exception:
                pass
        return "detection"

    def load_class_names(self, dataset_path: str | Path) -> dict[str, str]:
        """Parse class names dictionary from YAML metadata if available.

        Args:
            dataset_path (Union[str, Path]): Directory containing data.yaml.

        Returns:
            Dict[str, str]: Index to name mapping.
        """
        ds_path = Path(dataset_path)
        yaml_files = list(ds_path.glob("*.yaml")) + list(ds_path.glob("*.yml"))
        if not yaml_files:
            return {}

        try:
            with open(yaml_files[0], encoding="utf-8") as f:
                data = yaml.safe_load(f)
            names = data.get("names", {})
            if isinstance(names, list):
                return {str(idx): name for idx, name in enumerate(names)}
            if isinstance(names, dict):
                return {str(k): str(v) for k, v in names.items()}
        except Exception:
            pass
        return {}


class DatasetEDAState:
    """Pipeline state class for executing dataset exploratory data analysis."""

    def execute(self, dataset_path: str | Path) -> dict[str, Any]:
        """Execute complete analysis workflow on dataset.

        Args:
            dataset_path (Union[str, Path]): Target dataset directory.

        Returns:
            Dict[str, Any]: Analysis summary.

        Raises:
            FileNotFoundError: If the specified directory does not exist.
        """
        ds_path = Path(dataset_path)
        if not ds_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")
        return DatasetAnalyzer().analyze(ds_path)
