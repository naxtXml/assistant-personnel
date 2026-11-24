"""Point d'entrée de Capri.exe.

    Capri.exe             -> lance l'assistante
    Capri.exe --serveur   -> lance le serveur de contrôle à distance
"""
import sys


def _ouvrir_console():
    """Capri.exe n'a pas de console : le serveur en ouvre une pour afficher sa clé."""
    if sys.platform != "win32":
        return
    import ctypes
    if ctypes.windll.kernel32.AllocConsole():
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        ctypes.windll.kernel32.SetConsoleTitleW("Capri - Serveur")


if __name__ == "__main__":
    if "--serveur" in sys.argv:
        if getattr(sys, "frozen", False):
            _ouvrir_console()
        import serveur
        serveur.main()
    else:
        import capri
        capri.main()
