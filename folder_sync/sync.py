"""Funzione principale: collega validazione, scansione, confronto, esecuzione e report."""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, Optional

from .operations import execute_plan_sequential, execute_plan_threaded
from .planner import COMPARISON_ANY_DIFFERENCE, COMPARISON_CHECKSUM, build_sync_plan, print_sync_plan
from .scanner import scan_folder_multiprocessing, scan_folder_sequential
from .validation import PathLike, validate_folders

Report = Dict[str, Any]


def default_process_workers() -> int:
    """Numero predefinito di processi: al massimo 4, e mai più dei core disponibili."""
    return min(4, os.cpu_count() or 1)


def synchronize_folders(
    source_folder: PathLike,
    destination_folder: PathLike,
    parallel: bool = False,
    thread_workers: int = 4,
    process_workers: Optional[int] = None,
    comparison: str = COMPARISON_ANY_DIFFERENCE,
    mtime_tolerance_ns: int = 0,
    dry_run: bool = False,
    verbose: bool = True,
) -> Report:
    """Rende ``destination_folder`` una copia coerente di ``source_folder``.

    Il flusso è: validazione dei percorsi, scansione di sorgente e destinazione,
    confronto (piano di sincronizzazione), esecuzione, report con tempi,
    risultati ed errori.

    Args:
        parallel: se False, scansione ed esecuzione sono sequenziali. Se True,
            la scansione usa il **multiprocessing** (ogni processo attraversa
            un gruppo di sottocartelle) e l'esecuzione usa il **multithreading**
            (copie e cancellazioni, che sono lavoro di input/output).
        thread_workers: numero di thread per copia, aggiornamento e rimozione.
        process_workers: numero di processi per la scansione (predefinito:
            vedi ``default_process_workers``).
        comparison: come decidere se un file va aggiornato, vedi
            ``folder_sync.planner.needs_update`` (``"newer"``,
            ``"any_difference"`` o ``"checksum"``).
        mtime_tolerance_ns: differenza di date da ignorare, in nanosecondi.
        dry_run: se True costruisce e restituisce il piano senza modificare
            nessun file.
        verbose: se True stampa piano e risultato.

    Sicurezza: se la scansione della sorgente non è riuscita del tutto (ad
    esempio una sottocartella non è leggibile) le cancellazioni vengono
    **saltate**. Altrimenti i file della destinazione corrispondenti alla parte
    non letta sembrerebbero obsoleti e verrebbero eliminati per errore.

    Returns:
        Un dizionario con modalità, piano, tempi, operazioni riuscite e
        fallite, errori di scansione e il campo ``ok`` (True se è andato tutto bene).
    """
    if process_workers is None:
        process_workers = default_process_workers()

    source, destination = validate_folders(source_folder, destination_folder)

    compute_hash = comparison == COMPARISON_CHECKSUM
    total_start = time.perf_counter()

    # --- scansione --------------------------------------------------------
    scan_start = time.perf_counter()

    if parallel:
        # Un solo gruppo di processi per entrambe le scansioni: creare i
        # processi costa, quindi lo si fa una volta sola.
        with ProcessPoolExecutor(max_workers=process_workers) as executor:
            source_index, source_directories, source_scan_errors = scan_folder_multiprocessing(
                source, process_workers, executor, compute_hash
            )
            destination_index, destination_directories, destination_scan_errors = (
                scan_folder_multiprocessing(destination, process_workers, executor, compute_hash)
            )
    else:
        source_index, source_directories, source_scan_errors = scan_folder_sequential(
            source, compute_hash
        )
        destination_index, destination_directories, destination_scan_errors = (
            scan_folder_sequential(destination, compute_hash)
        )

    scan_time = time.perf_counter() - scan_start

    # --- piano ------------------------------------------------------------
    plan_start = time.perf_counter()

    plan = build_sync_plan(
        source_index,
        destination_index,
        source_directories,
        destination_directories,
        comparison,
        mtime_tolerance_ns,
    )

    # Se non abbiamo letto tutta la sorgente non possiamo sapere cosa sia
    # davvero obsoleto: meglio non cancellare nulla.
    deletions_skipped = bool(source_scan_errors) and bool(plan["delete"] or plan["remove_dirs"])
    if source_scan_errors:
        plan["delete"] = []
        plan["remove_dirs"] = []

    plan_time = time.perf_counter() - plan_start

    if verbose:
        print_sync_plan(plan)
        if deletions_skipped:
            print(
                "\nATTENZIONE: la sorgente non è stata letta per intero, "
                "le cancellazioni sono state saltate."
            )

    # --- esecuzione -------------------------------------------------------
    execution_start = time.perf_counter()

    if dry_run:
        operation_results = []
    elif parallel:
        operation_results = execute_plan_threaded(source, destination, plan, thread_workers)
    else:
        operation_results = execute_plan_sequential(source, destination, plan)

    execution_time = time.perf_counter() - execution_start
    total_time = time.perf_counter() - total_start

    # --- report -----------------------------------------------------------
    successful_operations = [r for r in operation_results if r["success"]]
    failed_operations = [r for r in operation_results if not r["success"]]
    scan_errors = source_scan_errors + destination_scan_errors

    report: Report = {
        "mode": "Parallela" if parallel else "Sequenziale",
        "comparison": comparison,
        "dry_run": dry_run,
        "source_files": len(source_index),
        "source_directories": len(source_directories),
        "destination_files_before_sync": len(destination_index),
        "plan": plan,
        "scan_time": scan_time,
        "plan_time": plan_time,
        "execution_time": execution_time,
        "total_time": total_time,
        "successful_operations": successful_operations,
        "failed_operations": failed_operations,
        "scan_errors": scan_errors,
        "removed_directories": [
            r["file"] for r in successful_operations if r["action"] == "rmdir"
        ],
        "deletions_skipped": deletions_skipped,
        "ok": not failed_operations and not scan_errors,
    }

    if verbose:
        print_report(report)

    return report


def print_report(report: Report) -> None:
    """Stampa il risultato di una sincronizzazione."""
    print("\nRISULTATO")
    print("-" * 44)
    print(f"Modalità:                 {report['mode']}")
    print(f"Confronto:                {report['comparison']}")

    if report["dry_run"]:
        print("Simulazione (dry run):    nessun file è stato modificato")

    print(f"Operazioni riuscite:      {len(report['successful_operations'])}")
    print(f"Operazioni fallite:       {len(report['failed_operations'])}")
    print(f"Errori di scansione:      {len(report['scan_errors'])}")
    print(f"Tempo scansione:          {report['scan_time']:.6f} secondi")
    print(f"Tempo creazione piano:    {report['plan_time']:.6f} secondi")
    print(f"Tempo esecuzione:         {report['execution_time']:.6f} secondi")
    print(f"Tempo totale:             {report['total_time']:.6f} secondi")

    if report["failed_operations"]:
        print("\nERRORI NELLE OPERAZIONI")
        for error in report["failed_operations"]:
            print(f"- {error['action']} | {error['file']} | {error['error']}")

    if report["scan_errors"]:
        print("\nERRORI DI SCANSIONE")
        for error in report["scan_errors"]:
            print(f"- {error['file']} | {error['error']}")
