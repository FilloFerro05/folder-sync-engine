# Documentazione tecnica

Repository: https://github.com/FilloFerro05/folder-sync-engine

## 1. Architettura

| Modulo | Responsabilità |
|--------|----------------|
| `validation.py` | Controlla i percorsi (esistenza, tipo, cartelle uguali o annidate) e crea la destinazione |
| `scanner.py` | Costruisce l'indice dei file (percorso relativo, dimensione, data, hash opzionale) e l'elenco delle cartelle |
| `planner.py` | Confronta gli indici e produce il piano: `copy`, `update`, `delete`, `unchanged`, `create_dirs`, `remove_dirs` |
| `operations.py` | Esegue le singole operazioni, in modo sequenziale o con thread |
| `sync.py` | Orchestra il flusso e produce il report |
| `cli.py`, `__main__.py` | Interfaccia a riga di comando |

## 2. Thread o processi: motivazioni passo per passo

1. **Validazione** – poche chiamate al file system: nessun parallelismo.
2. **Scansione** – **processi**. Ogni processo attraversa un gruppo di sottocartelle di primo livello (`os.walk`) ed esegue `stat` ed eventualmente l'hash SHA-256. L'hash è lavoro di CPU e con i thread il GIL lo serializzerebbe. Il processo principale elenca solo il primo livello. Un solo `ProcessPoolExecutor` è riusato per sorgente e destinazione, perché creare i processi ha un costo.
3. **Piano** – processo principale. Sono confronti tra dizionari in memoria: inviare i dati ad altri processi costerebbe più del calcolo.
4. **Copia / aggiornamento / rimozione** – **thread**. Sono operazioni di I/O in cui il GIL viene rilasciato; i thread sono leggeri e non richiedono di serializzare i dati tra processi.
5. **Ordine** – prima si creano le cartelle (genitori prima), poi si copiano i file, poi si eliminano i file obsoleti, infine si rimuovono le cartelle obsolete (figlie prima). Ogni fase termina prima della successiva.

## 3. Come sono stati affrontati i feedback

| Feedback | Intervento |
|----------|------------|
| Stampare `sequential_valid` / `parallel_valid` | Il benchmark verifica ogni sincronizzazione e stampa l'esito per ogni ripetizione e nella tabella finale |
| Multiprocessing debole (il cammino sulle cartelle era nel processo principale) | L'attraversamento ora avviene nei processi; il principale elenca solo il primo livello |
| Caso in cui il parallelo vince | Aggiunti i casi "File grandi" e "File grandi (checksum)"; il secondo mostra il vantaggio con hash |
| File modificato nel backup lasciato com'è | Modalità predefinita `any_difference`: qualunque differenza è un aggiornamento (la regola `newer` resta disponibile) |
| Cartelle vuote non copiate | Le cartelle sono replicate (`create_dirs`) e rimosse se obsolete (`remove_dirs`) |
| Docstring dentro le funzioni | Tutte le funzioni pubbliche hanno docstring (visibili con `help()`) |
| `except (PermissionError, OSError)` ridondante | Eccezioni gestite una sola volta, `OSError` copre già `PermissionError` |
| `remove_empty_directories` ignorava ogni `OSError` | `remove_directory_if_empty` ignora solo `ENOTEMPTY`/`EEXIST`; ogni altro errore è riportato come operazione fallita |
| Entry point protetto, `ProcessPoolExecutor` | `if __name__ == "__main__"` in `__main__.py` e nel benchmark; uso di `ProcessPoolExecutor` |

## 4. Scelte di sicurezza

- Se la scansione della sorgente ha avuto errori, le cancellazioni vengono **saltate** (`deletions_skipped`): altrimenti i file della destinazione corrispondenti alla parte non letta sembrerebbero obsoleti.
- Le cartelle sorgente e destinazione non possono essere uguali né una dentro l'altra.
- Ogni operazione restituisce un risultato (`success`, `action`, `file`, `error`): un errore non interrompe le altre operazioni ed è presente nel report.

## 5. Benchmark

Gli scenari (`benchmarks/scenarios.py`) usano dati casuali con seme fisso. Ogni scenario contiene file nuovi, modificati, obsoleti e cartelle vuote. Prima di ogni ripetizione la destinazione viene ripristinata, così le due versioni partono dalla stessa situazione.

Risultati misurati (2 core, file in cache di sistema, 3 ripetizioni):

| Caso | Sequenziale | Parallela | Speedup |
|------|------------:|----------:|--------:|
| Pochi file | 0,0011 s | 0,0114 s | 0,10x |
| Molti file | 0,0567 s | 0,1252 s | 0,45x |
| Sottocartelle | 0,0091 s | 0,0260 s | 0,35x |
| File grandi | 0,0182 s | 0,0227 s | 0,80x |
| File grandi (checksum) | 0,1281 s | 0,0847 s | 1,51x |

Interpretazione: l'avvio dei processi e dei thread ha un costo fisso di alcune decine di millisecondi, che domina quando il lavoro è piccolo. Nel caso "File grandi" qui la copia avviene tra file già in memoria (circa 20 MB in 17 ms), quindi non c'è I/O lento da sovrapporre; su un disco reale il risultato può cambiare. Il caso `checksum` è quello in cui c'è davvero calcolo da distribuire, e il parallelo vince. **I numeri sono indicativi**: vanno rieseguiti sulla propria macchina.

## 6. Limiti noti

- Link simbolici: i file sono seguiti e copiati come file normali, quelli a cartelle ignorati.
- Copia non atomica (nessun file temporaneo + rinomina).
- Un conflitto di tipo (file in sorgente, cartella in destinazione) non è gestito in modo speciale.
- Una sola sottocartella molto grande limita il bilanciamento della scansione parallela.
- FAT e simili hanno date poco precise: usare `mtime_tolerance_ns`.
- La modalità `checksum` legge tutti i file in entrambe le cartelle.

## 7. Sviluppi futuri

- Copia atomica (file temporaneo e rinomina).
- Bilanciamento della scansione a più livelli di profondità.
- Cache degli hash per evitare riletture.
- Gestione esplicita dei link simbolici.
