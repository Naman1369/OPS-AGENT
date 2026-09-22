"""Optional MLflow experiment tracking (synopsis software requirement 7).

MLflow is not a hard dependency: without it (or without ``--mlflow``) the
tracker is a no-op and the JSON/Markdown reports remain the record of the run.
With it, each evaluation logs its parameters, headline metrics and report
folder to the ``ops-agent`` experiment (``mlruns/`` by default).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Tracker:
    def __init__(self, enabled: bool = False, experiment: str = "ops-agent") -> None:
        self.enabled = False
        self.experiment = experiment
        if not enabled:
            return
        try:
            import mlflow  # noqa: F401
        except ImportError:
            logger.warning("MLflow is not installed (pip install mlflow); tracking disabled.")
            return
        self.enabled = True

    def log_run(self, name: str, summary: dict[str, Any], artifacts: Path | None = None) -> bool:
        if not self.enabled:
            return False
        import mlflow

        mlflow.set_experiment(self.experiment)
        with mlflow.start_run(run_name=name):
            mlflow.log_params({
                "provider": summary.get("provider"),
                "embedder": summary.get("embedder"),
                "alpha": summary.get("alpha"),
                "delta": summary.get("delta"),
                "method": summary.get("method"),
                "seeds": len(summary.get("seeds", [])),
            })
            for variant, metrics in summary["canonical"]["heldout"].items():
                for key in ("automation_rate", "correct_resolution_rate", "unsafe_resolution_rate",
                            "mast_any_user_facing_rate"):
                    value = metrics.get(key)
                    if value is not None:
                        mlflow.log_metric(f"{variant}.{key}", float(value))
            if artifacts is not None and Path(artifacts).exists():
                mlflow.log_artifacts(str(artifacts))
        return True
