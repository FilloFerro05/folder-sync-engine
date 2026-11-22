"""Interfaccia a riga di comando.

Uso:
    python -m folder_sync SORGENTE DESTINAZIONE [opzioni]
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from .planner import COMPARISON_ANY_DIFFERENCE, COMPARISON_MODES
from .sync import default_process_workers, synchronize_folders


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="folder_sync",
        description="Rende la cartella di destinazione una copia coerente della sorgente: "
        "copia i file nuovi, aggiorna quelli modificati, rimuove quelli obsoleti.",
    )
    parser.add_argument("source_folder", metavar="SORGENTE", help="cartella da copiare")
    parser.add_argument("destination_folder", metavar="DESTINAZIONE", help="cartella di backup")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="usa il multiprocessing per la scansione e il multithreading per le copie",
    )
    parser.add_argument("--threads", type=int, default=4, help="thread per copie e cancellazioni (predefinito: 4)")
    parser.add_argument(
        "--processes",
        type=int,
        default=None,
        help=f"processi per la scansione (predefinito: {default_process_workers()})",
    )
    parser.add_argument(
        "--compare",
        choices=COMPARISON_MODES,
        default=COMPARISON_ANY_DIFFERENCE,
        help="come decidere se un file va aggiornato: 'newer' (solo se la sorgente è più recente), "
        "'any_difference' (dimensione o data diverse, predefinito), 'checksum' (contenuto diverso)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="mostra il piano senza modificare nessun file",
    )
    parser.add_argument("--quiet", action="store_true", help="non stampare il riepilogo")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso. Restituisce 0 se tutto è andato bene, 1 se ci sono stati errori, 2 per percorsi non validi."""
    arguments = build_parser().parse_args(argv)

    try:
        report = synchronize_folders(
            arguments.source_folder,
            arguments.destination_folder,
            parallel=arguments.parallel,
            thread_workers=arguments.threads,
            process_workers=arguments.processes,
            comparison=arguments.compare,
            dry_run=arguments.dry_run,
            verbose=not arguments.quiet,
        )
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        print(f"Errore: {error}")
        return 2

    return 0 if report["ok"] else 1
