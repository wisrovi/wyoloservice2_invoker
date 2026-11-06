"""Image classification dataset analyzer."""

from pathlib import Path
from typing import Any, Dict, List, Set, Union


class ClassificationAnalyzer:
    """Analyze image classification datasets and compute class and split statistics."""

    IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png"}

    def analyze(self, dataset_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze a classification dataset directory.

        Args:
            dataset_path (Union[str, Path]): Path to root dataset directory.

        Returns:
            Dict[str, Any]: Classification statistics and distribution map.
        """
        ds_path = Path(dataset_path)
        total_images = 0
        class_distribution: Dict[str, int] = {}
        split_distribution: Dict[str, Dict[str, int]] = {}
        splits = ["train", "val", "test", "inference"]

        for split in splits:
            split_dir = ds_path / split
            if not split_dir.exists():
                continue
            split_distribution[split] = {}
            for class_dir in split_dir.iterdir():
                if not class_dir.is_dir():
                    continue
                count = sum(1 for f in class_dir.rglob("*") if f.is_file() and f.suffix.lower() in self.IMAGE_EXTENSIONS)
                split_distribution[split][class_dir.name] = count
                class_distribution[class_dir.name] = class_distribution.get(class_dir.name, 0) + count
                total_images += count

        percentages: Dict[str, float] = {}
        if total_images > 0:
            for s_name, s_data in split_distribution.items():
                s_sum = sum(s_data.values())
                percentages[s_name] = round((s_sum / total_images) * 100, 2)

        return {
            "dataset_type": "classification",
            "total_images": total_images,
            "classes_detected": list(class_distribution.keys()),
            "class_distribution": class_distribution,
            "split_distribution": split_distribution,
            "split_percentages": percentages,
        }
