"""Costruzione del piano di sincronizzazione.

Il piano è un semplice dizionario con l'elenco delle azioni da compiere. Tenere
il confronto separato dall'esecuzione ha un vantaggio concreto: il piano si può
costruire, stampare e verificare (anche con ``dry_run=True``) senza toccare
nessun file, ed è testabile da solo.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

Plan = Dict[str, List[str]]
FileIndex = Dict[str, Dict[str, Any]]

# Modalità di confronto tra la versione in sorgente e quella in destinazione
COMPARISON_NEWER = "newer"
COMPARISON_ANY_DIFFERENCE = "any_difference"
COMPARISON_CHECKSUM = "checksum"

COMPARISON_MODES = (
    COMPARISON_NEWER,
    COMPARISON_ANY_DIFFERENCE,
    COMPARISON_CHECKSUM,
)


def needs_update(
    source_file: Dict[str, Any],
    destination_file: Dict[str, Any],
    comparison: str = COMPARISON_ANY_DIFFERENCE,
    mtime_tolerance_ns: int = 0,
) -> bool:
    """Decide se un file presente in entrambe le cartelle va aggiornato.

    Modalità di confronto:

    * ``"newer"``: aggiorna solo se la sorgente è più recente. È la regola
      della traccia ("quando la versione in sorgente è più recente"). Se
      qualcuno modifica un file direttamente nella destinazione, il file
      resta com'è.
    * ``"any_difference"`` (predefinita): aggiorna se dimensione o data di
      modifica sono diverse. Per un vero sistema di backup è la scelta più
      sicura: la destinazione deve essere una copia della sorgente, quindi
      anche un file modificato direttamente nel backup viene ripristinato.
    * ``"checksum"``: aggiorna solo se il contenuto è diverso (confronto
      dell'hash SHA-256). È la modalità più affidabile, perché non si fida
      delle date, ma richiede di leggere tutti i file.

    Args:
        mtime_tolerance_ns: differenza di date (in nanosecondi) da ignorare.
            Utile con file system che salvano le date con poca precisione
            (ad esempio FAT, 2 secondi), dove la copia potrebbe non
            conservare la data esatta.
    """
    if comparison == COMPARISON_CHECKSUM:
        return source_file["sha256"] != destination_file["sha256"]

    time_difference = source_file["modified_time"] - destination_file["modified_time"]
    same_size = source_file["size"] == destination_file["size"]

    if comparison == COMPARISON_NEWER:
        # Se i timestamp coincidono ma la dimensione è diversa i contenuti non
        # possono essere uguali, quindi aggiorniamo comunque.
        return time_difference > mtime_tolerance_ns or (
            abs(time_difference) <= mtime_tolerance_ns and not same_size
        )

    return (not same_size) or abs(time_difference) > mtime_tolerance_ns


def build_sync_plan(
    source_index: FileIndex,
    destination_index: FileIndex,
    source_directories: Iterable[str] = (),
    destination_directories: Iterable[str] = (),
    comparison: str = COMPARISON_ANY_DIFFERENCE,
    mtime_tolerance_ns: int = 0,
) -> Plan:
    """Confronta sorgente e destinazione e costruisce il piano di sincronizzazione.

    Le azioni sono:

    * ``copy``: file presenti solo nella sorgente (nuovi);
    * ``update``: file presenti in entrambe ma da aggiornare;
    * ``delete``: file presenti solo nella destinazione (obsoleti);
    * ``unchanged``: file già coerenti;
    * ``create_dirs``: cartelle della sorgente che mancano nella destinazione
      (comprese quelle vuote, che altrimenti non arriverebbero mai a destinazione);
    * ``remove_dirs``: cartelle presenti solo nella destinazione.

    Raises:
        ValueError: se la modalità di confronto non è riconosciuta.
    """
    if comparison not in COMPARISON_MODES:
        raise ValueError(
            f"Modalità di confronto non valida: {comparison!r}. "
            f"Valori ammessi: {', '.join(COMPARISON_MODES)}"
        )

    plan: Plan = {
        "copy": [],
        "update": [],
        "delete": [],
        "unchanged": [],
        "create_dirs": [],
        "remove_dirs": [],
    }

    # analizziamo tutti i file presenti nella sorgente
    for relative_path, source_file in source_index.items():

        # il file non esiste nella destinazione, deve essere copiato
        if relative_path not in destination_index:
            plan["copy"].append(relative_path)
            continue

        if needs_update(
            source_file,
            destination_index[relative_path],
            comparison,
            mtime_tolerance_ns,
        ):
            plan["update"].append(relative_path)
        else:
            plan["unchanged"].append(relative_path)

    # i file presenti soltanto nella destinazione sono obsoleti
    for relative_path in destination_index:
        if relative_path not in source_index:
            plan["delete"].append(relative_path)

    source_directories = set(source_directories)
    destination_directories = set(destination_directories)

    plan["create_dirs"] = list(source_directories - destination_directories)
    plan["remove_dirs"] = list(destination_directories - source_directories)

    # Ordiniamo tutto per rendere prevedibile l'output.
    # Le cartelle da creare vanno dalla più esterna alla più interna (prima il
    # genitore); quelle da rimuovere al contrario (prima i figli, perché una
    # cartella si può togliere solo quando è vuota).
    for action in ("copy", "update", "delete", "unchanged"):
        plan[action].sort()

    plan["create_dirs"].sort(key=lambda path: (path.count("/"), path))
    plan["remove_dirs"].sort(key=lambda path: (-path.count("/"), path))

    return plan


def print_sync_plan(plan: Plan) -> None:
    """Stampa un riepilogo leggibile del piano di sincronizzazione."""
    rows = [
        ("File nuovi da copiare", "copy"),
        ("File modificati da aggiornare", "update"),
        ("File obsoleti da rimuovere", "delete"),
        ("File invariati", "unchanged"),
        ("Cartelle da creare", "create_dirs"),
        ("Cartelle da rimuovere", "remove_dirs"),
    ]

    print("\nPIANO DI SINCRONIZZAZIONE")
    print("-" * 44)

    for label, action in rows:
        print(f"{label:<32}{len(plan[action]):>8}")
