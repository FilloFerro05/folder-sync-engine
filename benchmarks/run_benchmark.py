"""Benchmark: versione sequenziale contro versione parallela.

Uso (dalla cartella principale del progetto):
    python -m benchmarks.run_benchmark
    python -m benchmarks.run_benchmark --repetitions 5 --keep

Per ogni caso di test:
  1. si ripristina la destinazione allo stato iniziale (fondamentale per confrontare
     in modo corretto le due versioni: partono sempre dalla stessa situazione);
  2. si esegue la sincronizzazione, e se ne misura il tempo;
  3. si VERIFICA che la destinazione sia diventata identica alla sorgente
     (percorsi, contenuto e cartelle) e il risultato della verifica viene stampato;
  4. si ripete il tutto, per ridurre l'effetto delle variazioni momentanee.

I casi includono sia situazioni in cui il parallelismo non conviene (file
piccoli: l'overhead di thread e processi supera il vantaggio) sia situazioni
in cui conviene (file grandi), perché un benchmark onesto deve mostrare
entrambe le cose.
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from folder_sync.scanner import scan_folder_sequential
from folder_sync.sync import default_process_workers, synchronize_folders

from .scenarios import SCENARIOS, create_test_scenario

# Casi di test: (scenario, modalità di confronto, etichetta mostrata)
BENCHMARK_CASES = [
    ("few", "any_difference", "Pochi file"),
    ("many", "any_difference", "Molti file"),
    ("nested", "any_difference", "Sottocartelle"),
    ("large", "any_difference", "File grandi"),
    ("large", "checksum", "File grandi (checksum)"),
]


def restore_destination(initial_destination: Path, test_destination: Path) -> None:
    """Ripristina la destinazione alla situazione iniziale del test."""
    if test_destination.exists():
        shutil.rmtree(test_destination)

    shutil.copytree(initial_destination, test_destination)


def verify_synchronization(source_folder: Path, destination_folder: Path) -> Dict[str, object]:
    """Verifica che la destinazione sia identica alla sorgente.

    Confronta i percorsi dei file, il loro contenuto (hash SHA-256) e le
    cartelle, comprese quelle vuote.
    """
    source_index, source_dirs, source_errors = scan_folder_sequential(source_folder, compute_hash=True)
    destination_index, destination_dirs, destination_errors = scan_folder_sequential(
        destination_folder, compute_hash=True
    )

    source_paths = set(source_index)
    destination_paths = set(destination_index)

    missing_files = sorted(source_paths - destination_paths)
    extra_files = sorted(destination_paths - source_paths)
    different_files = sorted(
        path
        for path in source_paths & destination_paths
        if source_index[path]["sha256"] != destination_index[path]["sha256"]
    )
    missing_dirs = sorted(set(source_dirs) - set(destination_dirs))
    extra_dirs = sorted(set(destination_dirs) - set(source_dirs))
    errors = source_errors + destination_errors

    return {
        "valid": not (missing_files or extra_files or different_files or missing_dirs or extra_dirs or errors),
        "missing_files": missing_files,
        "extra_files": extra_files,
        "different_files": different_files,
        "missing_dirs": missing_dirs,
        "extra_dirs": extra_dirs,
        "errors": errors,
    }


def run_case(
    label: str,
    comparison: str,
    source_folder: Path,
    initial_destination: Path,
    repetitions: int,
    thread_workers: int,
    process_workers: int,
) -> Dict[str, object]:
    """Confronta versione sequenziale e parallela su un caso di test."""
    scenario_folder = source_folder.parent
    versions = {
        "sequential": {"destination": scenario_folder / "destination_sequential", "parallel": False},
        "parallel": {"destination": scenario_folder / "destination_parallel", "parallel": True},
    }

    times: Dict[str, List[float]] = {"sequential": [], "parallel": []}
    valid: Dict[str, bool] = {"sequential": True, "parallel": True}
    names = {"sequential": "Sequenziale", "parallel": "Parallela   "}

    print("\n" + "=" * 70)
    print(f"CASO: {label.upper()}  (confronto: {comparison})")
    print("=" * 70)

    for repetition in range(1, repetitions + 1):
        print(f"Ripetizione {repetition}/{repetitions}")

        for key, version in versions.items():
            restore_destination(initial_destination, version["destination"])

            report = synchronize_folders(
                source_folder=source_folder,
                destination_folder=version["destination"],
                parallel=version["parallel"],
                thread_workers=thread_workers,
                process_workers=process_workers,
                comparison=comparison,
                verbose=False,
            )

            verification = verify_synchronization(source_folder, version["destination"])

            times[key].append(report["total_time"])
            valid[key] = valid[key] and bool(verification["valid"]) and report["ok"]

            outcome = "OK" if verification["valid"] and report["ok"] else "ERRORE"
            print(f"  {names[key]}: {report['total_time']:.6f} s   verifica: {outcome}")

            if not verification["valid"]:
                print(f"    dettagli: {verification}")

    sequential_average = statistics.mean(times["sequential"])
    parallel_average = statistics.mean(times["parallel"])

    return {
        "label": label,
        "comparison": comparison,
        "sequential_times": times["sequential"],
        "parallel_times": times["parallel"],
        "sequential_average": sequential_average,
        "parallel_average": parallel_average,
        "speedup": sequential_average / parallel_average if parallel_average > 0 else 0,
        "sequential_valid": valid["sequential"],
        "parallel_valid": valid["parallel"],
    }


def print_results(results: List[Dict[str, object]]) -> None:
    """Stampa la tabella finale e un commento sui tempi misurati."""
    print("\n" + "=" * 92)
    print("RISULTATI FINALI")
    print("=" * 92)

    print(
        f"{'Caso':<26}{'Media seq.':>13}{'Media par.':>13}{'Speedup':>10}"
        f"{'Verifica seq.':>15}{'Verifica par.':>15}"
    )
    print("-" * 92)

    for result in results:
        print(
            f"{result['label']:<26}"
            f"{result['sequential_average']:>11.4f} s"
            f"{result['parallel_average']:>11.4f} s"
            f"{result['speedup']:>9.2f}x"
            f"{'OK' if result['sequential_valid'] else 'ERRORE':>15}"
            f"{'OK' if result['parallel_valid'] else 'ERRORE':>15}"
        )

    print("\nCOMMENTO SUI RISULTATI")
    print("-" * 92)

    for result in results:
        sequential_time = result["sequential_average"]
        parallel_time = result["parallel_average"]
        speedup = result["speedup"]

        print(f"\n{result['label']}:")

        if speedup > 1.05:
            print(
                f"La versione parallela è risultata più veloce: il tempo medio è passato da "
                f"{sequential_time:.4f} a {parallel_time:.4f} secondi, con uno speedup di circa {speedup:.2f}x."
            )
        elif speedup < 0.95:
            print(
                f"La versione parallela è risultata più lenta: il tempo medio è passato da "
                f"{sequential_time:.4f} a {parallel_time:.4f} secondi. Qui il costo di creare e "
                f"coordinare thread e processi supera il vantaggio ottenuto."
            )
        else:
            print(
                f"Le due versioni hanno ottenuto tempi simili ({sequential_time:.4f} s contro "
                f"{parallel_time:.4f} s): il parallelismo non ha prodotto un vantaggio rilevante."
            )

    print("\nCONCLUSIONE GENERALE")
    print("-" * 92)

    if all(r["sequential_valid"] and r["parallel_valid"] for r in results):
        print(
            "Tutte le sincronizzazioni sono state verificate: al termine di ogni test la "
            "destinazione contiene gli stessi file (con lo stesso contenuto) e le stesse "
            "cartelle della sorgente."
        )
    else:
        print("Almeno una verifica è fallita: controllare i dettagli stampati sopra.")

    print(
        "\nLe prestazioni dipendono dal numero e dalla dimensione dei file, dal costo di gestione di "
        "thread e processi, dal numero di core e dal file system. Per questo il parallelismo non è "
        "necessariamente più veloce in ogni scenario."
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark sequenziale contro parallelo")
    parser.add_argument("--repetitions", type=int, default=3, help="ripetizioni per ogni caso (predefinito: 3)")
    parser.add_argument("--threads", type=int, default=4, help="thread per copia e rimozione (predefinito: 4)")
    parser.add_argument("--processes", type=int, default=default_process_workers(),
                        help=f"processi per la scansione (predefinito: {default_process_workers()})")
    parser.add_argument("--workdir", default=None, help="cartella in cui creare i dati di test (predefinito: cartella temporanea)")
    parser.add_argument("--keep", action="store_true", help="non cancellare i dati di test al termine")
    parser.add_argument("--seed", type=int, default=42, help="seme casuale per dati riproducibili (predefinito: 42)")
    arguments = parser.parse_args(argv)

    workdir = Path(arguments.workdir) if arguments.workdir else Path(tempfile.mkdtemp(prefix="folder_sync_bench_"))
    workdir.mkdir(parents=True, exist_ok=True)

    print(f"Cartella dei dati di test: {workdir}")
    print(f"Thread: {arguments.threads} | Processi: {arguments.processes} | Ripetizioni: {arguments.repetitions}")

    try:
        scenarios = {}
        for scenario_name in SCENARIOS:
            scenarios[scenario_name] = create_test_scenario(scenario_name, workdir, arguments.seed)
            print(f"Scenario creato: {scenario_name}")

        results = [
            run_case(
                label,
                comparison,
                *scenarios[scenario_name],
                repetitions=arguments.repetitions,
                thread_workers=arguments.threads,
                process_workers=arguments.processes,
            )
            for scenario_name, comparison, label in BENCHMARK_CASES
        ]

        print_results(results)
    finally:
        if not arguments.keep:
            shutil.rmtree(workdir, ignore_errors=True)

    return 0 if all(r["sequential_valid"] and r["parallel_valid"] for r in results) else 1


# Il controllo __name__ == "__main__" è indispensabile con il multiprocessing
# (su Windows i processi figlio importano di nuovo questo modulo).
if __name__ == "__main__":
    raise SystemExit(main())
