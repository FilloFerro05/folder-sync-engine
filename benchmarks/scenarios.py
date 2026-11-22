"""Generazione degli scenari di test per il benchmark.

Ogni scenario è composto da:
* una cartella sorgente con file generati a caso;
* una destinazione iniziale, copia della sorgente a cui sono state introdotte
  differenze controllate, così ogni test mette alla prova tutte le operazioni:
  copia (file nuovi), aggiornamento (file modificati), rimozione (file obsoleti)
  e creazione di cartelle vuote.

I contenuti sono generati con un generatore casuale con seme fisso, quindi gli
scenari sono riproducibili.
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from typing import Dict, Tuple

# Dimensione dei blocchi con cui vengono scritti i file, per non creare
# in memoria contenuti molto grandi tutti insieme.
WRITE_BLOCK_SIZE = 1024 * 1024

# Definizione degli scenari. Per ognuno: etichetta, numero di file, intervallo di
# dimensione dei file (in byte), numero di cartelle e differenze introdotte.
SCENARIOS: Dict[str, dict] = {
    "few": {
        "label": "Pochi file",
        "files": 15,
        "size": (1024, 4096),
        "differences": {"new": 3, "modified": 3, "obsolete": 3, "empty_dirs": 1},
    },
    "many": {
        "label": "Molti file",
        "files": 1000,
        "size": (1024, 8192),
        "differences": {"new": 200, "modified": 200, "obsolete": 200, "empty_dirs": 2},
    },
    "nested": {
        "label": "Sottocartelle",
        "files": 120,
        "size": (1024, 6144),
        "differences": {"new": 20, "modified": 20, "obsolete": 20, "empty_dirs": 3},
    },
    # Pochi file ma grandi (2 MiB): qui la copia pesa davvero e il parallelismo
    # ha materiale su cui lavorare. È lo scenario in cui ci si aspetta che la
    # versione parallela convenga.
    "large": {
        "label": "File grandi",
        "files": 40,
        "size": (2 * 1024 * 1024, 2 * 1024 * 1024),
        "differences": {"new": 10, "modified": 10, "obsolete": 5, "empty_dirs": 1},
    },
}


def create_random_file(file_path: Path, size_bytes: int, rng: random.Random) -> None:
    """Crea un file con contenuto casuale della dimensione indicata."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "wb") as file:
        remaining_bytes = size_bytes

        while remaining_bytes > 0:
            block_size = min(remaining_bytes, WRITE_BLOCK_SIZE)
            file.write(rng.randbytes(block_size))
            remaining_bytes -= block_size


def _file_location(scenario_name: str, index: int) -> Tuple[str, ...]:
    """Cartelle (relative alla sorgente) in cui va il file numero ``index``."""
    if scenario_name == "many":
        return (f"group_{index % 10}",)

    if scenario_name == "nested":
        return (
            f"level_1_{index % 4}",
            f"level_2_{index % 6}",
            f"level_3_{index % 8}",
        )

    return ()  # pochi file e file grandi: tutti nella cartella principale


def prepare_destination_with_differences(
    source_folder: Path,
    destination_folder: Path,
    number_new: int,
    number_modified: int,
    number_obsolete: int,
    number_empty_dirs: int,
    rng: random.Random,
) -> None:
    """Crea la destinazione come copia della sorgente e vi introduce differenze controllate."""
    source_folder = Path(source_folder)
    destination_folder = Path(destination_folder)

    if destination_folder.exists():
        shutil.rmtree(destination_folder)

    shutil.copytree(source_folder, destination_folder)

    source_files = sorted(path for path in source_folder.rglob("*") if path.is_file())

    # File nuovi: li eliminiamo dalla destinazione, così risultano presenti
    # solo nella sorgente.
    for source_file in source_files[:number_new]:
        (destination_folder / source_file.relative_to(source_folder)).unlink()

    # File modificati: modifichiamo la SORGENTE (la destinazione resta la versione vecchia)
    # e la rendiamo più recente di 10 secondi.
    modified_files = source_files[number_new:number_new + number_modified]

    for source_file in modified_files:
        relative_path = source_file.relative_to(source_folder)
        old_destination_time = (destination_folder / relative_path).stat().st_mtime

        with open(source_file, "ab") as file:
            file.write(b"\nCONTENUTO AGGIUNTO ALLA SORGENTE")

        newer_time = old_destination_time + 10
        os.utime(source_file, (newer_time, newer_time))

    # File obsoleti: esistono soltanto nella destinazione, in una cartella a parte
    for index in range(number_obsolete):
        create_random_file(
            destination_folder / "obsolete_files" / f"obsolete_{index:04d}.bin",
            rng.randint(512, 2048),
            rng,
        )

    # Cartelle vuote: esistono nella sorgente ma non nella destinazione, e vanno
    # create comunque (un backup deve conservare anche la struttura).
    for index in range(number_empty_dirs):
        (source_folder / "empty_folders" / f"empty_{index}").mkdir(parents=True, exist_ok=True)

    if number_empty_dirs:
        shutil.rmtree(destination_folder / "empty_folders", ignore_errors=True)


def create_test_scenario(
    scenario_name: str, base_folder: Path, seed: int = 42
) -> Tuple[Path, Path]:
    """Crea una cartella di test per lo scenario indicato.

    Returns:
        (cartella sorgente, destinazione iniziale).
    """
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Scenario non riconosciuto: {scenario_name}")

    definition = SCENARIOS[scenario_name]
    rng = random.Random(seed)

    scenario_folder = Path(base_folder) / scenario_name
    source_folder = scenario_folder / "source_folder"
    initial_destination = scenario_folder / "initial_destination"

    if scenario_folder.exists():
        shutil.rmtree(scenario_folder)

    source_folder.mkdir(parents=True)

    minimum_size, maximum_size = definition["size"]

    for index in range(definition["files"]):
        location = source_folder.joinpath(*_file_location(scenario_name, index))
        create_random_file(
            location / f"file_{index:04d}.bin",
            rng.randint(minimum_size, maximum_size),
            rng,
        )

    differences = definition["differences"]

    prepare_destination_with_differences(
        source_folder=source_folder,
        destination_folder=initial_destination,
        number_new=differences["new"],
        number_modified=differences["modified"],
        number_obsolete=differences["obsolete"],
        number_empty_dirs=differences["empty_dirs"],
        rng=rng,
    )

    return source_folder, initial_destination
