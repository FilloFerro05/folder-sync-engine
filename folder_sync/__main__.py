"""Permette di lanciare il programma con ``python -m folder_sync``."""

from .cli import main

# Il controllo __name__ == "__main__" è indispensabile con il multiprocessing:
# su Windows (e macOS) ogni processo figlio importa di nuovo questo modulo, e
# senza il controllo ricreerebbe a sua volta altri processi all'infinito.
if __name__ == "__main__":
    raise SystemExit(main())
