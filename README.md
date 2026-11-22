# 📁 Folder Sync Engine

Sistema di sincronizzazione di cartelle in Python: rende una cartella di destinazione una **copia coerente** della sorgente (copia i file nuovi, aggiorna quelli diversi, rimuove quelli obsoleti, replica anche le cartelle vuote), con una versione sequenziale e una **parallela** che usa **multiprocessing** per la scansione e **multithreading** per le operazioni di I/O.

Progetto del corso di Python avanzato.

[![Apri in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1b7S0y9QtlB8WAb-yi5IPd0RZ21f3Bd8c)

## Il problema

Data una `source_folder` e una `destination_folder`, la destinazione deve diventare identica alla sorgente:

- file presenti solo nella sorgente → **copiati**
- file presenti in entrambe ma diversi → **aggiornati**
- file presenti solo nella destinazione → **rimossi**
- cartelle (anche vuote) → **replicate / rimosse**

## Come funziona

Il flusso è: validazione → scansione → piano → esecuzione → report.

| Fase | Strumento | Perché |
|------|-----------|--------|
| Scansione (attraversamento + `stat` + eventuale hash) | **Processi** | Lavoro con calcolo (soprattutto l'hash SHA-256): i processi non sono limitati dal GIL |
| Piano di sincronizzazione | Processo principale | Pochi confronti su dizionari: parallelizzare costerebbe più che farlo |
| Copia, aggiornamento, rimozione | **Thread** | Lavoro di I/O: il GIL viene rilasciato durante le operazioni su file; i thread sono leggeri e condividono la memoria |

Il piano è costruito separatamente dall'esecuzione: si può quindi stampare, testare e usare con `--dry-run` senza toccare nulla.

### Modalità di confronto

| Modalità | Aggiorna quando… |
|----------|------------------|
| `newer` | la sorgente è più recente (regola della traccia originale) |
| `any_difference` (predefinita) | dimensione o data di modifica sono diverse: ripristina anche i file modificati a mano nel backup |
| `checksum` | l'hash SHA-256 del contenuto è diverso (la più affidabile, la più lenta) |

## Risultati dei test

Test automatici: **32 test superati** (`pytest`). Benchmark su 5 casi, 3 ripetizioni ciascuno, con verifica della destinazione (percorsi, contenuto SHA-256, cartelle) dopo ogni sincronizzazione:

| Caso | Sequenziale | Parallela | Speedup | Verifica seq. / par. |
|------|------------:|----------:|--------:|:--------------------:|
| Pochi file (15) | 0,0011 s | 0,0114 s | 0,10x | OK / OK |
| Molti file (1000) | 0,0567 s | 0,1252 s | 0,45x | OK / OK |
| Sottocartelle (120, 3 livelli) | 0,0091 s | 0,0260 s | 0,35x | OK / OK |
| File grandi (40 × 2 MiB) | 0,0182 s | 0,0227 s | 0,80x | OK / OK |
| File grandi, confronto `checksum` | 0,1281 s | 0,0847 s | **1,51x** | OK / OK |

> Misure su una macchina con 2 core, con i file già in cache di sistema (copie quasi istantanee). **Sono indicative e dipendono da hardware, disco e file system**: su un disco reale le copie di file grandi costano di più e il parallelismo tende a convenire anche senza `checksum`.

Lettura: con pochi file piccoli il costo di avviare processi e thread supera il lavoro da fare, quindi la versione parallela è più lenta. Il vantaggio compare quando c'è lavoro pesante da distribuire, come il calcolo degli hash su file grandi.

## Stack

Solo libreria standard di Python 3.9+: `os`, `shutil`, `hashlib`, `concurrent.futures`, `argparse`. Nessuna dipendenza per l'esecuzione; `pytest` solo per i test.

## Struttura

```
folder-sync-engine/
├── folder_sync/        # pacchetto: validation, scanner, planner, operations, sync, cli
├── benchmarks/         # scenari di test e confronto sequenziale / parallelo
├── tests/              # test automatici (pytest)
├── docs/               # documentazione tecnica e guida alla configurazione
├── pytest.ini
└── requirements.txt
```

## Come avviarlo

```bash
git clone https://github.com/FilloFerro05/folder-sync-engine.git
cd folder-sync-engine

python -m folder_sync SORGENTE DESTINAZIONE                 # sequenziale
python -m folder_sync SORGENTE DESTINAZIONE --parallel      # parallela
python -m folder_sync SORGENTE DESTINAZIONE --dry-run       # solo simulazione
python -m folder_sync SORGENTE DESTINAZIONE --compare checksum

python -m benchmarks.run_benchmark                          # benchmark
python -m pytest                                            # test
```

Da codice:

```python
from folder_sync import synchronize_folders
report = synchronize_folders("dati", "backup", parallel=True)
```

## Documentazione

- [Documentazione tecnica](docs/DOCUMENTAZIONE_TECNICA.md)
- [Guida alla configurazione](docs/GUIDA_CONFIGURAZIONE.md)

## Limiti noti

- I collegamenti simbolici a file vengono copiati come file normali; quelli a cartelle sono ignorati.
- La copia non è atomica: un'interruzione può lasciare un file a metà.
- Se quasi tutti i file stanno in una sola sottocartella, la scansione parallela non può bilanciare il lavoro.
- Su file system con date poco precise (FAT) usare `mtime_tolerance_ns`.

Autore: [FilloFerro05](https://github.com/FilloFerro05)
