"""YOLO segmentation dataset analyzer."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


class SegmentationAnalyzer:
    """Analyze YOLO segmentation datasets and compute polygon statistics."""

    IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png"}

    def analyze(self, dataset_path: Union[str, Path], class_names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Analyze a segmentation dataset directory.

        Args:
            dataset_path (Union[str, Path]): Path to root dataset directory.
            class_names (Optional[Dict[str, str]]): Mapping of class IDs to names.

        Returns:
            Dict[str, Any]: Segmentation statistics and polygon counts.
        """
        ds_path = Path(dataset_path)
        total_images = 0
        total_segments = 0
        names = class_names or {}
        class_distribution: Dict[str, int] = {}
        split_distribution: Dict[str, Dict[str, Any]] = {}
        splits = ["train", "val", "test", "inference"]

        for split in splits:
            split_dir = ds_path / split
            if not split_dir.exists():
                continue
            img_dir = split_dir / "images"
            lbl_dir = split_dir / "labels"
            split_distribution[split] = {"images": 0, "segments": 0, "classes": {}}

            if img_dir.exists():
                for img_file in img_dir.rglob("*"):
                    if img_file.suffix.lower() in self.IMAGE_EXTENSIONS:
                        total_images += 1
                        split_distribution[split]["images"] += 1

            if lbl_dir.exists():
                for lbl_file in lbl_dir.rglob("*.txt"):
                    try:
                        with open(lbl_file, "r", encoding="utf-8") as f:
                            for line in f:
                                vals = line.split()
                                if not vals:
                                    continue
                                total_segments += 1
                                split_distribution[split]["segments"] += 1
                                c_id = vals[0]
                                c_name = names.get(c_id, c_id)
                                split_distribution[split]["classes"][c_name] = (
                                    split_distribution[split]["classes"].get(c_name, 0) + 1
                                )
                                class_distribution[c_name] = class_distribution.get(c_name, 0) + 1
                    except Exception:
                        pass

        percentages: Dict[str, float] = {}
        if total_images > 0:
            for s_name, s_data in split_distribution.items():
                percentages[s_name] = round((s_data["images"] / total_images) * 100, 2)

        return {
            "dataset_type": "segmentation",
            "total_images": total_images,
            "total_segments": total_segments,
            "num_classes": len(class_distribution),
            "class_distribution": class_distribution,
            "split_distribution": split_distribution,
            "split_percentage_distribution": percentages,
        }
