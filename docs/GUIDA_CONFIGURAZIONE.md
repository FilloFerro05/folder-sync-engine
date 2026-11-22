# Guida alla configurazione

## 1. Requisiti

- Python 3.9 o superiore (`python --version`)
- Nessuna libreria esterna per l'esecuzione; `pytest` solo per i test

## 2. Scaricare il progetto

```bash
git clone https://github.com/FilloFerro05/folder-sync-engine.git
cd folder-sync-engine
```

## 3. Ambiente virtuale (consigliato)

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Per i test: `pip install -r requirements.txt`

## 4. Uso da riga di comando

```bash
python -m folder_sync SORGENTE DESTINAZIONE [opzioni]
```

| Opzione | Significato |
|---------|-------------|
| `--parallel` | scansione con processi, operazioni con thread |
| `--threads N` | numero di thread (predefinito 4) |
| `--processes N` | numero di processi (predefinito: min(4, core)) |
| `--compare {newer,any_difference,checksum}` | criterio di confronto (predefinito `any_difference`) |
| `--dry-run` | mostra il piano senza modificare nulla |
| `--quiet` | nessun output (utile negli script: usa il codice di uscita) |

Codici di uscita: `0` tutto ok, `1` errori nelle operazioni o nella scansione, `2` percorsi non validi.

**Consiglio:** provare sempre prima con `--dry-run`, perché la destinazione viene modificata (anche con cancellazioni).

## 5. Uso da codice

```python
from folder_sync import synchronize_folders

report = synchronize_folders("dati", "backup", parallel=True, comparison="checksum")
print(report["ok"], report["total_time"])
```

## 6. Benchmark e test

```bash
python -m benchmarks.run_benchmark --repetitions 5
python -m benchmarks.run_benchmark --workdir ./bench_data --keep
python -m pytest
```

Lanciare i comandi dalla cartella principale del progetto.

## 7. Pubblicare su GitHub

```bash
git init
git add .
git commit -m "Aggiunge Folder Sync Engine"
git branch -M main
git remote add origin https://github.com/FilloFerro05/folder-sync-engine.git
git push -u origin main
```

(Prima crea su GitHub un repository vuoto chiamato `folder-sync-engine`.)

## 8. Problemi comuni

| Problema | Soluzione |
|----------|-----------|
| `ModuleNotFoundError: folder_sync` | Lancia i comandi dalla cartella principale del progetto |
| Su Windows il programma si riavvia / errore sui processi | Usa `python -m folder_sync` oppure proteggi lo script con `if __name__ == "__main__":` |
| `Errore: La cartella sorgente non esiste` | Controlla il percorso (usa le virgolette se contiene spazi) |
| Il parallelo è più lento | Normale con pochi file piccoli; conviene con molto lavoro (file grandi, `checksum`) |
| File ricopiati a ogni esecuzione su disco FAT | Usa `mtime_tolerance_ns=2_000_000_000` da codice |
