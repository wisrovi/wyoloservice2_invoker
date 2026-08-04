# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa

from pathlib import Path
import subprocess
import os
import shutil
import csv
import json

class TrainingReportAnalyzer:
    """
    Generate AI-assisted training analysis using OpenCode with fallback.
    """

    def analyze(
        self,
        results_file: str | Path
    ) -> str:
        """
        Generate a professional training report.

        Args:
            results_file: Path to YOLO results.csv file.

        Returns:
            Generated report text.
        """

        results_file = Path(results_file)

        if not results_file.exists():
            raise FileNotFoundError(
                f"Results file not found: {results_file}"
            )

        # Try OpenCode first with timeout
        try:
            report = self._analyze_with_opencode(results_file)
            if report and len(report.strip()) > 50:
                return report
        except Exception as exc:
            print(f"OpenCode analysis failed, using fallback: {exc}")

        # Fallback: generate basic report from CSV data
        return self._generate_fallback_report(results_file)

    def _analyze_with_opencode(self, results_file: Path) -> str | None:
        """Attempt to generate report using OpenCode with timeout."""
        prompt = """
        Generate a professional technical training report in English.

        Use correct grammar, punctuation, and spelling.

        Do not use markdown.

        Analyze the training that was performed.

        Evaluate:
        - Training progression.
        - Convergence.
        - Metrics obtained.
        - Possible overfitting.
        - Possible underfitting.
        - Overall model quality.
        - Detected risks.
        - Recommendations.

        Use the following sections:

        TRAINING SUMMARY

        METRICS ANALYSIS

        CONCLUSION

        Maximum three lines per section.

        Do not invent data.
        """

        OPENCODE_BIN = "/root/.opencode/bin/opencode"

        result = subprocess.run(
            [
                OPENCODE_BIN,
                "run",
                "--model",
                "opencode/deepseek-v4-flash-free",
                prompt,
                "-f",
                str(results_file)
            ],
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes timeout
        )

        print("PATH:", os.environ.get("PATH"))
        print("WHICH OPENCODE:", shutil.which("opencode"))

        print("STDOUT:")
        print(result.stdout)

        print("STDERR:")
        print(result.stderr)

        print("RETURN CODE:")
        print(result.returncode)

        if result.returncode != 0:
            raise RuntimeError(
                f"OpenCode error:\n{result.stderr}"
            )

        output = result.stdout.strip()
        if not output or len(output) < 50:
            raise RuntimeError("OpenCode returned empty or too short output")

        return output

    def _generate_fallback_report(self, results_file: Path) -> str:
        """Generate a basic report from CSV data when OpenCode fails."""
        try:
            with open(results_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as exc:
            return f"Error reading results file: {exc}"

        if not rows:
            return "No training data available for analysis."

        # Parse key metrics
        epochs = len(rows)
        last_row = rows[-1]

        # Extract metrics (handle different column names)
        train_loss = last_row.get('train/loss', last_row.get('train_loss', 'N/A'))
        val_loss = last_row.get('val/loss', last_row.get('val_loss', 'N/A'))
        precision = last_row.get('metrics/precision', last_row.get('precision', 'N/A'))
        recall = last_row.get('metrics/recall', last_row.get('recall', 'N/A'))
        mAP50 = last_row.get('metrics/mAP50(B)', last_row.get('mAP50', 'N/A'))
        mAP50_95 = last_row.get('metrics/mAP50-95(B)', last_row.get('mAP50-95', 'N/A'))
        accuracy = last_row.get('metrics/accuracy_top1', last_row.get('accuracy', 'N/A'))

        # Check for overfitting
        train_loss_first = rows[0].get('train/loss', rows[0].get('train_loss', '0'))
        train_loss_last = train_loss
        val_loss_first = rows[0].get('val/loss', rows[0].get('val_loss', '0'))
        val_loss_last = val_loss

        overfitting_risk = "Low"
        try:
            if float(train_loss_last) < float(train_loss_first) and float(val_loss_last) > float(val_loss_first):
                overfitting_risk = "High"
            elif float(val_loss_last) > float(val_loss_first) * 1.2:
                overfitting_risk = "Medium"
        except (ValueError, TypeError):
            pass

        # Build report
        report_lines = [
            "TRAINING SUMMARY",
            f"Training completed over {epochs} epochs. Final training loss: {train_loss}, validation loss: {val_loss}.",
            f"Model achieved accuracy: {accuracy}, mAP@50: {mAP50}, mAP@50-95: {mAP50_95}.",
            "",
            "METRICS ANALYSIS",
            f"Precision: {precision}, Recall: {recall}. mAP@50: {mAP50}, mAP@50-95: {mAP50_95}.",
            f"Overfitting risk: {overfitting_risk}. Training loss trend: {'decreasing' if float(train_loss_last) < float(train_loss_first) else 'stable/increasing'}.",
            f"Validation loss trend: {'decreasing' if float(val_loss_last) < float(val_loss_first) else 'increasing/stable'}.",
            "",
            "CONCLUSION",
            f"Model trained for {epochs} epochs with final accuracy {accuracy}.",
            f"Overfitting risk assessed as {overfitting_risk}. Consider regularization or early stopping if risk is high.",
            "Review confusion matrix and per-class metrics for detailed performance breakdown."
        ]

        return "\n".join(report_lines)