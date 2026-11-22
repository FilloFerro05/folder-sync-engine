"""Scansione delle cartelle: versione sequenziale e versione con multiprocessing.

Il risultato di una scansione è una tupla ``(indice, cartelle, errori)``:

* ``indice``: dizionario che ha per chiave il percorso relativo del file (sempre
  con ``/`` come separatore, anche su Windows) e per valore le sue informazioni;
* ``cartelle``: elenco dei percorsi relativi di tutte le sottocartelle, comprese
  quelle vuote (la radice non è inclusa);
* ``errori``: elenco dei file o cartelle che non è stato possibile leggere.

Perché il multiprocessing qui
-----------------------------
La parte costosa di una scansione è attraversare l'albero delle cartelle e
leggere i metadati di ogni file (e, in modalità checksum, il suo contenuto per
calcolare l'hash). Sono operazioni che nel processo principale verrebbero
eseguite una dopo l'altra. Per questo ogni processo riceve un gruppo di
*sottocartelle di primo livello* e le attraversa per intero da solo: il
processo principale elenca soltanto il primo livello (costo trascurabile) e
smista il lavoro. Il calcolo dell'hash è lavoro di CPU puro, ed è il caso in cui
i processi (che non condividono il GIL) portano un vantaggio reale.
"""

from __future__ import annotations

import hashlib
import os
import stat
from concurrent.futures import Executor, ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FileIndex = Dict[str, Dict[str, Any]]
ScanResult = Tuple[FileIndex, List[str], List[Dict[str, str]]]

# Dimensione dei blocchi di lettura per l'hash: i file vengono letti a pezzi
# per non caricare in memoria file molto grandi.
HASH_BLOCK_SIZE = 1024 * 1024


def split_into_chunks(items: Sequence, number_of_chunks: int) -> list:
    """Divide una lista in sottogruppi di dimensione simile.

    I sottogruppi servono per assegnare a ogni processo una parte del lavoro.
    Se ci sono meno elementi che gruppi richiesti, i gruppi sono meno.
    """
    if not items:
        return []

    number_of_chunks = max(1, min(number_of_chunks, len(items)))
    chunk_size = (len(items) + number_of_chunks - 1) // number_of_chunks

    return [
        list(items[index:index + chunk_size])
        for index in range(0, len(items), chunk_size)
    ]


def hash_file(file_path: os.PathLike, block_size: int = HASH_BLOCK_SIZE) -> str:
    """Restituisce l'hash SHA-256 del contenuto di un file, letto a blocchi."""
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for block in iter(lambda: file.read(block_size), b""):
            digest.update(block)

    return digest.hexdigest()


def _describe_file(
    root: Path, file_path: Path, compute_hash: bool
) -> Optional[Dict[str, Any]]:
    """Raccoglie le informazioni di un file; restituisce None se non è un file regolare.

    Può sollevare OSError (file non leggibile): lo gestisce il chiamante, che
    lo registra tra gli errori senza interrompere la scansione.
    """
    file_info = os.stat(file_path)

    # Scartiamo ciò che non è un file regolare (ad esempio un collegamento
    # simbolico che punta a una cartella, o un file speciale).
    if not stat.S_ISREG(file_info.st_mode):
        return None

    return {
        "relative_path": file_path.relative_to(root).as_posix(),
        "absolute_path": str(file_path),
        "size": file_info.st_size,
        # st_mtime_ns è più preciso del timestamp in secondi, perciò usiamo quello
        "modified_time": file_info.st_mtime_ns,
        "sha256": hash_file(file_path) if compute_hash else None,
    }


def _scan_error(file_path: Any, error: OSError) -> Dict[str, str]:
    return {"file": str(file_path), "operation": "scansione", "error": str(error)}


def scan_subtrees(arguments: Tuple[str, List[str], bool]) -> ScanResult:
    """Attraversa per intero le cartelle indicate e descrive ciò che trova.

    Questa è la funzione eseguita in ogni processo (e, nella versione
    sequenziale, nel processo principale: il codice è lo stesso, così le due
    modalità producono per costruzione lo stesso risultato).

    Args:
        arguments: ``(radice, cartelle_di_partenza, calcola_hash)``. Le
            informazioni sono passate come testo e non come oggetti ``Path``
            per rendere semplice e leggero il passaggio tra processi.
    """
    root_string, start_folders, compute_hash = arguments

    root = Path(root_string)
    entries: List[Dict[str, Any]] = []
    directories: List[str] = []
    errors: List[Dict[str, str]] = []

    def on_walk_error(error: OSError) -> None:
        # os.walk chiama questa funzione quando non riesce a leggere una cartella
        errors.append(_scan_error(error.filename, error))

    for start_folder in start_folders:
        for current_folder, _, file_names in os.walk(start_folder, onerror=on_walk_error):
            current = Path(current_folder)

            if current != root:
                directories.append(current.relative_to(root).as_posix())

            for file_name in file_names:
                file_path = current / file_name

                try:
                    entry = _describe_file(root, file_path, compute_hash)
                except OSError as error:
                    errors.append(_scan_error(file_path, error))
                else:
                    if entry is not None:
                        entries.append(entry)

    return _as_result(entries, directories, errors)


def scan_file_list(arguments: Tuple[str, List[str], bool]) -> ScanResult:
    """Descrive un elenco di file già individuati (quelli nel primo livello).

    Args:
        arguments: ``(radice, percorsi_dei_file, calcola_hash)``.
    """
    root_string, file_strings, compute_hash = arguments

    root = Path(root_string)
    entries: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for file_string in file_strings:
        file_path = Path(file_string)

        try:
            entry = _describe_file(root, file_path, compute_hash)
        except OSError as error:
            errors.append(_scan_error(file_path, error))
        else:
            if entry is not None:
                entries.append(entry)

    return _as_result(entries, [], errors)


def _as_result(entries: list, directories: list, errors: list) -> ScanResult:
    """Trasforma l'elenco dei file in un indice basato sul percorso relativo."""
    index = {entry["relative_path"]: entry for entry in entries}
    return index, directories, errors


def scan_folder_sequential(folder: os.PathLike, compute_hash: bool = False) -> ScanResult:
    """Scansiona una cartella in un unico processo, un file dopo l'altro.

    Serve come riferimento di correttezza e come termine di confronto per la
    versione con multiprocessing.
    """
    folder = Path(folder)
    return scan_subtrees((str(folder), [str(folder)], compute_hash))


def scan_folder_multiprocessing(
    folder: os.PathLike,
    process_workers: int,
    executor: Optional[Executor] = None,
    compute_hash: bool = False,
) -> ScanResult:
    """Scansiona una cartella distribuendo il lavoro su più processi.

    Il processo principale elenca soltanto il primo livello della cartella; poi
    le sottocartelle di primo livello e i file sciolti vengono divisi in gruppi
    e assegnati ai processi, che li elaborano in parallelo.

    Args:
        folder: la cartella da scansionare.
        process_workers: numero massimo di processi (e di gruppi di lavoro).
        executor: un ``ProcessPoolExecutor`` già creato. Se viene passato lo si
            riutilizza (creare i processi costa: conviene farlo una sola volta
            per sincronizzazione); altrimenti ne viene creato uno temporaneo.
        compute_hash: se True ogni processo calcola anche l'hash SHA-256 dei
            file che elabora.
    """
    if executor is None:
        with ProcessPoolExecutor(max_workers=process_workers) as own_executor:
            return scan_folder_multiprocessing(
                folder, process_workers, own_executor, compute_hash
            )

    folder = Path(folder)
    top_directories: List[str] = []
    top_files: List[str] = []

    try:
        with os.scandir(folder) as iterator:
            for item in iterator:
                if item.is_dir(follow_symlinks=False):
                    top_directories.append(item.path)
                else:
                    top_files.append(item.path)
    except OSError as error:
        return {}, [], [_scan_error(folder, error)]

    futures = []

    for chunk in split_into_chunks(top_directories, process_workers):
        futures.append(executor.submit(scan_subtrees, (str(folder), chunk, compute_hash)))

    for chunk in split_into_chunks(top_files, process_workers):
        futures.append(executor.submit(scan_file_list, (str(folder), chunk, compute_hash)))

    file_index: FileIndex = {}
    directories: List[str] = []
    errors: List[Dict[str, str]] = []

    for future in futures:
        partial_index, partial_directories, partial_errors = future.result()
        file_index.update(partial_index)
        directories.extend(partial_directories)
        errors.extend(partial_errors)

    return file_index, directories, errors
