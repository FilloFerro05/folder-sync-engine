"""Esecuzione del piano di sincronizzazione: copia, aggiornamento, rimozione.

Perché i thread qui
-------------------
Copiare, aggiornare e cancellare file è soprattutto lavoro di input/output: il
programma passa il tempo ad aspettare il disco, e durante l'attesa Python
rilascia il GIL, quindi altri thread possono elaborare altri file. I thread
costano poco da creare e condividono la memoria, ed è per questo che qui si
usano i thread e non i processi (che avrebbero un costo di avvio molto più alto
senza dare alcun vantaggio, perché la CPU non è il collo di bottiglia).

Ordine delle operazioni
-----------------------
1. creazione delle cartelle mancanti (prima i genitori);
2. copia e aggiornamento dei file;
3. rimozione dei file obsoleti;
4. rimozione delle cartelle obsolete (prima i figli), solo se vuote.

Le cancellazioni partono quando tutte le copie sono terminate: il flusso è più
ordinato e se una copia fallisce non si sono già perse informazioni.
"""

from __future__ import annotations

import errno
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

Result = Dict[str, Any]

# Errori con cui il sistema operativo segnala "la cartella non è vuota"
# (il valore esatto dipende dal sistema operativo).
_NOT_EMPTY_ERRNOS = {errno.ENOTEMPTY, errno.EEXIST}


def _result(success: bool, action: str, target: Path, error: Optional[str] = None) -> Result:
    return {
        "success": success,
        "action": action,
        "file": str(target),
        "error": error,
    }


def copy_single_file(source_file: os.PathLike, destination_file: os.PathLike, action: str) -> Result:
    """Copia (o aggiorna) un singolo file, creando le cartelle che mancano.

    Usa ``shutil.copy2``, che conserva anche i principali metadati, compresa la
    data di modifica: così alla sincronizzazione successiva il file risulta
    invariato.

    Args:
        action: ``"copy"`` o ``"update"``, riportata nel risultato.
    """
    source_file = Path(source_file)
    destination_file = Path(destination_file)

    try:
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination_file)
        return _result(True, action, destination_file)

    except OSError as error:  # PermissionError è già una sottoclasse di OSError
        return _result(False, action, destination_file, str(error))


def delete_single_file(destination_file: os.PathLike) -> Result:
    """Elimina un singolo file obsoleto dalla destinazione."""
    destination_file = Path(destination_file)

    try:
        destination_file.unlink()
        return _result(True, "delete", destination_file)

    except OSError as error:
        return _result(False, "delete", destination_file, str(error))


def create_directory(directory: os.PathLike) -> Result:
    """Crea una cartella (e i suoi genitori) nella destinazione."""
    directory = Path(directory)

    try:
        directory.mkdir(parents=True, exist_ok=True)
        return _result(True, "mkdir", directory)

    except OSError as error:
        return _result(False, "mkdir", directory, str(error))


def remove_directory_if_empty(directory: os.PathLike) -> Optional[Result]:
    """Rimuove una cartella obsoleta, ma solo se è vuota.

    Una cartella non vuota fa fallire ``rmdir`` in modo del tutto normale e
    viene lasciata dov'è (restituisce None). Qualunque *altro* errore, ad
    esempio un problema di permessi, viene invece restituito come
    operazione fallita: ignorarlo in silenzio lascerebbe il problema inosservato.
    """
    directory = Path(directory)

    try:
        os.rmdir(directory)
        return _result(True, "rmdir", directory)

    except OSError as error:
        if error.errno in _NOT_EMPTY_ERRNOS:
            return None
        return _result(False, "rmdir", directory, str(error))


def execute_plan_sequential(
    source_folder: os.PathLike, destination_folder: os.PathLike, plan: Dict[str, List[str]]
) -> List[Result]:
    """Esegue il piano un'operazione alla volta.

    La usiamo come riferimento per misurare il vantaggio (o lo svantaggio) del
    parallelismo.
    """
    source_folder = Path(source_folder)
    destination_folder = Path(destination_folder)

    results: List[Result] = []

    for relative_path in plan["create_dirs"]:
        results.append(create_directory(destination_folder / relative_path))

    for action in ("copy", "update"):
        for relative_path in plan[action]:
            results.append(
                copy_single_file(
                    source_folder / relative_path,
                    destination_folder / relative_path,
                    action,
                )
            )

    for relative_path in plan["delete"]:
        results.append(delete_single_file(destination_folder / relative_path))

    for relative_path in plan["remove_dirs"]:
        result = remove_directory_if_empty(destination_folder / relative_path)
        if result is not None:
            results.append(result)

    return results


def execute_plan_threaded(
    source_folder: os.PathLike,
    destination_folder: os.PathLike,
    plan: Dict[str, List[str]],
    thread_workers: int,
) -> List[Result]:
    """Esegue il piano con più thread per le copie e le cancellazioni.

    La creazione e la rimozione delle cartelle restano sequenziali: sono poche,
    veloci, e l'ordine (genitori prima dei figli, o viceversa) è importante.
    """
    source_folder = Path(source_folder)
    destination_folder = Path(destination_folder)

    results: List[Result] = []

    for relative_path in plan["create_dirs"]:
        results.append(create_directory(destination_folder / relative_path))

    # prima eseguiamo in parallelo copie e aggiornamenti
    with ThreadPoolExecutor(max_workers=thread_workers) as executor:
        futures = [
            executor.submit(
                copy_single_file,
                source_folder / relative_path,
                destination_folder / relative_path,
                action,
            )
            for action in ("copy", "update")
            for relative_path in plan[action]
        ]

        for future in as_completed(futures):
            results.append(future.result())

    # le cancellazioni iniziano solo quando tutte le copie sono terminate
    with ThreadPoolExecutor(max_workers=thread_workers) as executor:
        futures = [
            executor.submit(delete_single_file, destination_folder / relative_path)
            for relative_path in plan["delete"]
        ]

        for future in as_completed(futures):
            results.append(future.result())

    for relative_path in plan["remove_dirs"]:
        result = remove_directory_if_empty(destination_folder / relative_path)
        if result is not None:
            results.append(result)

    return results
