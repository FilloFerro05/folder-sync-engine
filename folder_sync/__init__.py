"""folder_sync: sincronizzazione di una cartella di destinazione con una sorgente.

Esempio:
    from folder_sync import synchronize_folders

    report = synchronize_folders("dati", "backup", parallel=True)
"""

from .planner import COMPARISON_MODES, build_sync_plan
from .sync import synchronize_folders

__version__ = "1.0.0"

__all__ = ["synchronize_folders", "build_sync_plan", "COMPARISON_MODES", "__version__"]
