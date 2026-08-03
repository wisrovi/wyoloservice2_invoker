from pathlib import Path
from typing import Any
import yaml

class DatasetAnalyzer:
    """
    Analyze a dataset and automatically determine its type.

    This class detects whether the dataset is intended for
    classification, object detection, or segmentation tasks
    and delegates the analysis to the corresponding analyzer.
    """
    def analyze(
        self,
        dataset_path: str | Path
    ) -> dict[str, Any]:
        """
        Analyze a dataset and return its statistics.

        Parameters
        ----------
        dataset_path : str | Path
            Path to the dataset directory.

        Returns
        -------
        dict[str, Any]
            Dataset analysis results.
        """
                
        print(f"Analyzing dataset: {dataset_path}")
        print(f"Exists: {Path(dataset_path).exists()}")
        
        dataset_type = self.detect_dataset_type(
            dataset_path
        )


        if dataset_type == "classification":
            return ClassificationAnalyzer().analyze(
                dataset_path
            )

        if dataset_type == "detection":
            return DetectionAnalyzer().analyze(
                dataset_path
            )

        if dataset_type == "segmentation":
            return SegmentationAnalyzer().analyze(
                dataset_path
            )

        return {
            "dataset_type": "unknown"
        }

    def detect_dataset_type(
        self,
        dataset_path: str | Path
    ) -> str:
        """
        Detect the dataset type based on its directory structure.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        str
            Dataset type. Possible values are
            'classification', 'detection',
            'segmentation', or 'unknown'.
        """
        dataset_path = Path(dataset_path)

        train_path = dataset_path / "train"

        # Detection and segmentation (YOLO)
        if ((train_path / "images").exists() and (train_path / "labels").exists()):
            return self.detect_yolo_type(dataset_path)

        # Classification

        class_dirs = []

        for item in dataset_path.iterdir():

            if item.is_dir():
                class_dirs.append(item)

        if len(class_dirs) > 0:
            return "classification"

        return "unknown"

    def detect_yolo_type(
        self,
        dataset_path: str | Path
    ) -> str:
        """
        Determine whether a YOLO dataset is intended for
        object detection or segmentation.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        str
            YOLO dataset type.
        """
        for split in ["train", "val", "test"]:

            labels_path = dataset_path / split / "labels"

            if not labels_path.exists():
                continue

            for label_file in labels_path.rglob("*.txt"):

                with open(label_file, encoding="utf-8") as f:

                    for line in f:

                        values = line.split()

                        if not values:
                            continue

                        if len(values) == 5:
                            return "detection"

                        if len(values) > 5:
                            return "segmentation"

        return "unknown"

    def load_class_names(
        self,
        dataset_path: str | Path
    ) -> dict[str, str]:

        dataset_path = Path(dataset_path)

        yaml_files = list(dataset_path.glob("*.yaml"))

        if not yaml_files:
            return {}

        with open(yaml_files[0], encoding="utf-8") as f:
            data = yaml.safe_load(f)

        names = data.get("names", {})

        if isinstance(names, list):
            return {
                str(idx): name
                for idx, name in enumerate(names)
            }

        if isinstance(names, dict):
            return {
                str(idx): name
                for idx, name in names.items()
            }

        return {}

class ClassificationAnalyzer:
    """
    Analyze image classification datasets and compute
    class and split distribution statistics.
    """
    IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png"
    }

    def analyze(
        self,
        dataset_path: str | Path
    ) -> dict[str, Any]:
        """
        Analyze a classification dataset.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        dict[str, Any]
            Dataset statistics including class distribution,
            split distribution, and imbalance information.
        """
        dataset_path = Path(dataset_path)

        total_images = 0

        class_distribution = {}

        imbalanced_dataset = False

        imbalanced_pairs = []

        split_distribution = {}

        split_percentage_distribution = {}

        splits = ["train", "val", "test", "inference"]

        for split in splits:

            split_path = dataset_path / split

            if not split_path.exists():
                continue

            split_distribution[split] = {}

            for class_dir in split_path.iterdir():

                if not class_dir.is_dir():
                    continue

                image_count = 0

                for file in class_dir.rglob("*"):

                    if (
                        file.is_file()
                        and file.suffix.lower()
                        in self.IMAGE_EXTENSIONS
                    ):
                        image_count += 1

                split_distribution[split][class_dir.name] = image_count

                class_distribution[class_dir.name] = (
                    class_distribution.get(class_dir.name,0) + image_count)

                total_images += image_count

        # Imbalance detection
        classes = list(class_distribution.items())

        for i in range(len(classes)):

            class_a, count_a = classes[i]

            for j in range(i + 1, len(classes)):

                class_b, count_b = classes[j]

                bigger = max(count_a, count_b)
                smaller = min(count_a, count_b)

                difference = (bigger - smaller) / bigger

                if difference > 0.30:

                    imbalanced_dataset = True

                    imbalanced_pairs.append({
                        "class_a": class_a,
                        "class_b": class_b,
                        "difference_percent": round(
                            difference * 100, 2
                        )
                    })

        # Split percentages
        for split, data in split_distribution.items():
            split_images = sum(data.values())
            split_percentage_distribution[split] = round(split_images * 100 / total_images, 2)

        # Results
        return {
            "dataset_type": "classification",
            "num_classes": len(class_distribution),
            "total_images": total_images,
            "class_distribution": class_distribution,
            "split_distribution": split_distribution,
            "split_percentage_distribution": split_percentage_distribution,
            "imbalanced_dataset": imbalanced_dataset,
            "imbalanced_pairs": imbalanced_pairs
        }


class DetectionAnalyzer:
    """
    Analyze YOLO object detection datasets and compute
    annotation and class distribution statistics.
    """
    IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png"
    }

    def analyze(
        self,
        dataset_path: str | Path
    ) -> dict[str, Any]:

        """
        Analyze an object detection dataset.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        dict[str, Any]
            Detection dataset statistics and imbalance metrics.
        """

        dataset_path = Path(dataset_path)

        total_images = 0
        total_annotations = 0


        class_names = DatasetAnalyzer().load_class_names(dataset_path)

        class_distribution = {}

        split_distribution = {}

        split_percentage_distribution = {}

        imbalanced_dataset = False

        imbalanced_pairs = []

        splits = ["train", "val", "test", "inference"]

        for split in splits:

            split_path = dataset_path / split
            if not split_path.exists():
                continue

            images_split_path = dataset_path / split  / "images"
            labels_split_path = dataset_path / split  / "labels"

            split_distribution[split] = {
                "images": 0,
                "annotations": 0,
                "classes": {}
            }

            # Count images

            for image_file in images_split_path.rglob("*"):

                if image_file.suffix.lower() in self.IMAGE_EXTENSIONS:

                    total_images += 1

                    split_distribution[split]["images"] += 1

            # Count annotations

            for label_file in labels_split_path.rglob("*.txt"):

                with open(label_file, "r", encoding="utf-8") as f:

                    for line in f:

                        values = line.split()

                        if not values:
                            continue

                        total_annotations += 1

                        split_distribution[split]["annotations"] += 1

                        class_id = values[0]

                        class_name = class_names.get(
                            class_id,
                            class_id
                        )

                        if class_name not in split_distribution[split]["classes"]:
                            split_distribution[split]["classes"][class_name] = 0
                        split_distribution[split]["classes"][class_name] += 1

                        if class_name not in class_distribution:
                            class_distribution[class_name] = 0
                        class_distribution[class_name] += 1

        classes = list(class_distribution.items())

        for i in range(len(classes)):

            class_a, count_a = classes[i]

            for j in range(i + 1, len(classes)):

                class_b, count_b = classes[j]

                bigger = max(count_a, count_b)
                smaller = min(count_a, count_b)

                difference = (bigger - smaller) / bigger

                if difference > 0.30:

                    imbalanced_dataset = True

                    imbalanced_pairs.append({
                        "class_a": class_a,
                        "class_b": class_b,
                        "difference_percent": round(
                            difference * 100, 2
                        )
                    })

        # Split percentages
        for split, data in split_distribution.items():
            split_percentage_distribution[split] = round(data["images"] * 100 / total_images, 2)

        return {
            "dataset_type": "detection",
            "total_images": total_images,
            "total_annotations": total_annotations,
            "num_classes": len(class_distribution),
            "class_distribution": class_distribution,
            "split_distribution": split_distribution,
            "split_percentage_distribution": split_percentage_distribution,
            "imbalanced_dataset": imbalanced_dataset,
            "imbalanced_pairs": imbalanced_pairs
        }


class SegmentationAnalyzer:
    """
    Analyze YOLO segmentation datasets and compute
    segment and class distribution statistics.
    """
    IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png"
    }

    def analyze(
        self,
        dataset_path: str | Path
    ) -> dict[str, Any]:
        """
        Analyze a segmentation dataset.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        dict[str, Any]
            Segmentation dataset statistics and imbalance metrics.
        """
        dataset_path = Path(dataset_path)

        total_images = 0
        total_segments = 0

        class_names = DatasetAnalyzer().load_class_names(dataset_path)


        class_distribution = {}

        split_distribution = {}

        split_percentage_distribution = {}

        imbalanced_dataset = False

        imbalanced_pairs = []

        splits = ["train", "val", "test", "inference"]

        for split in splits:

            split_path = dataset_path / split
            if not split_path.exists():
                continue

            images_split_path = dataset_path / split / "images"
            labels_split_path = dataset_path / split / "labels"

            split_distribution[split] = {
                "images": 0,
                "segments": 0,
                "classes": {}
            }

            # Count images

            for image_file in images_split_path.rglob("*"):

                if image_file.suffix.lower() in self.IMAGE_EXTENSIONS:

                    total_images += 1

                    split_distribution[split]["images"] += 1

            # Count annotations

            for label_file in labels_split_path.rglob("*.txt"):

                with open(label_file, "r", encoding="utf-8") as f:

                    for line in f:

                        values = line.split()

                        if not values:
                            continue

                        total_segments += 1

                        split_distribution[split]["segments"] += 1

                        class_id = values[0]

                        class_name = class_names.get(
                            class_id,
                            class_id
                        )

                        if class_name not in split_distribution[split]["classes"]:
                            split_distribution[split]["classes"][class_name] = 0
                        split_distribution[split]["classes"][class_name] += 1

                        if class_name not in class_distribution:
                            class_distribution[class_name] = 0
                        class_distribution[class_name] += 1

        classes = list(class_distribution.items())

        for i in range(len(classes)):

            class_a, count_a = classes[i]

            for j in range(i + 1, len(classes)):

                class_b, count_b = classes[j]

                bigger = max(count_a, count_b)
                smaller = min(count_a, count_b)

                difference = (bigger - smaller) / bigger

                if difference > 0.30:

                    imbalanced_dataset = True

                    imbalanced_pairs.append({
                        "class_a": class_a,
                        "class_b": class_b,
                        "difference_percent": round(
                            difference * 100, 2
                        )
                    })

        # Split percentages
        for split, data in split_distribution.items():
            if total_images > 0:
                split_percentage_distribution[split] = round(data["images"] * 100 / total_images, 2)

        return {
            "dataset_type": "segmentation",
            "total_images": total_images,
            "total_segments": total_segments,
            "num_classes": len(class_distribution),
            "class_distribution": class_distribution,
            "split_distribution": split_distribution,
            "split_percentage_distribution": split_percentage_distribution,
            "imbalanced_dataset": imbalanced_dataset,
            "imbalanced_pairs": imbalanced_pairs
        }


class DatasetEDAState:
    """
    Pipeline state responsible for executing
    dataset exploratory data analysis.
    """
    def execute(
        self,
        dataset_path: str | Path
    ) -> dict[str, Any]:
        """
        Execute dataset analysis.

        Parameters
        ----------
        dataset_path : str | Path
            Dataset directory.

        Returns
        -------
        dict[str, Any]
            Dataset analysis results.
        """
        dataset_path = Path(dataset_path)

        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {dataset_path}"
            )

        return (
            DatasetAnalyzer()
            .analyze(dataset_path)
        )


if __name__ == "__main__":

    import sys
    import json

    if len(sys.argv) != 2:
        raise ValueError(
            "Usage: python dataset_analyzer.py <dataset_path>"
        )

    dataset_path = Path(sys.argv[1])

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {dataset_path}"
        )

    analyzer = DatasetAnalyzer()

    result = analyzer.analyze(
        dataset_path
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )
