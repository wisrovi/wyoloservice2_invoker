# mypy: ignore-errors
# pylint: disable=all
# ruff: noqa

from pathlib import Path
import subprocess
import os
import shutil

class TrainingReportAnalyzer:
    """
    Generate AI-assisted training analysis using OpenCode.
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

        prompt = """
        Genera un informe técnico profesional en español.

        Utiliza correctamente todas las tildes,
        signos de puntuación y gramática.

        No utilices markdown.

        Analiza el entrenamiento realizado.

        Evalúa:
        - Evolución del entrenamiento.
        - Convergencia.
        - Métricas obtenidas.
        - Posible sobreajuste.
        - Posible infraajuste.
        - Calidad general del modelo.
        - Riesgos detectados.
        - Recomendaciones.

        Utiliza las siguientes secciones:

        RESUMEN DEL ENTRENAMIENTO

        ANÁLISIS DE MÉTRICAS

        CONCLUSIÓN

        Máximo tres líneas por sección.

        No inventes datos.
        """

        OPENCODE_BIN = "/root/.opencode/bin/opencode"

        result = subprocess.run(
            [
                OPENCODE_BIN,
                "run",
                prompt,
                "-f",
                str(results_file)
            ],
            capture_output=True,
            text=True
        )

        print("PATH:", os.environ.get("PATH"))
        print("WHICH OPENCODE:", shutil.which("opencode"))

        if result.returncode != 0:
            raise RuntimeError(
                f"OpenCode error:\n{result.stderr}"
            )

        return result.stdout.strip()