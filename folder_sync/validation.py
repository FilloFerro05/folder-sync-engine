"""Validazione dei percorsi di sorgente e destinazione."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

PathLike = Union[str, Path]


def validate_folders(
    source_folder: PathLike, destination_folder: PathLike
) -> Tuple[Path, Path]:
    """Controlla che sorgente e destinazione siano utilizzabili.

    Una destinazione dentro la sorgente (o viceversa) è il tipo di errore
    che in produzione fa danni seri: la sincronizzazione copierebbe la
    cartella dentro se stessa all'infinito, oppure cancellerebbe la sorgente.
    Per questo i casi pericolosi vengono bloccati prima di toccare qualunque file.

    Se la destinazione non esiste, viene creata.

    Raises:
        FileNotFoundError: la sorgente non esiste.
        NotADirectoryError: sorgente o destinazione esistono ma non sono cartelle.
        ValueError: sorgente e destinazione coincidono o sono annidate.

    Returns:
        I percorsi assoluti (sorgente, destinazione).
    """
    source = Path(source_folder).resolve()
    destination = Path(destination_folder).resolve()

    if not source.exists():
        raise FileNotFoundError(f"La cartella sorgente non esiste: {source}")

    if not source.is_dir():
        raise NotADirectoryError(f"Il percorso sorgente non è una cartella: {source}")

    if destination.exists() and not destination.is_dir():
        raise NotADirectoryError(
            f"Il percorso di destinazione non è una cartella: {destination}"
        )

    if source == destination:
        raise ValueError("La sorgente e la destinazione non possono coincidere.")

    if source in destination.parents:
        raise ValueError("La destinazione non può essere contenuta nella sorgente.")

    if destination in source.parents:
        raise ValueError("La sorgente non può essere contenuta nella destinazione.")

    # La destinazione viene creata se non esiste
    destination.mkdir(parents=True, exist_ok=True)

    return source, destination
