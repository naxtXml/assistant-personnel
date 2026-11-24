"""Chemins de Capri, valables en script Python comme dans Capri.exe.

- RESSOURCES : fichiers livrés avec Capri (sprites, images). En .exe, PyInstaller
  les décompresse dans un dossier temporaire (sys._MEIPASS).
- DOSSIER_EXE : dossier où se trouve Capri.exe (ou capri.py). On y cherche
  ngrok.exe et le HUD CapriDesktop.
- DONNEES : réglages et clés de l'utilisateur (~/.capri). Jamais dans le dépôt.
"""
import sys
from pathlib import Path

EST_EXE = getattr(sys, "frozen", False)

if EST_EXE:
    RESSOURCES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DOSSIER_EXE = Path(sys.executable).resolve().parent
else:
    RESSOURCES = Path(__file__).resolve().parent
    DOSSIER_EXE = RESSOURCES

DONNEES = Path.home() / ".capri"
DONNEES.mkdir(parents=True, exist_ok=True)
