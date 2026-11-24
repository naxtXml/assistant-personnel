# -*- mode: python ; coding: utf-8 -*-
# Construction :  pyinstaller Capri.spec
# Résultat     :  dist\Capri\Capri.exe (+ ses fichiers)

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = [
    ("sprites", "sprites"),
    ("call_btn.png", "."),
    ("stopcall.png", "."),
    ("vpn_btn.png", "."),
    ("vpn_power.png", "."),
]
datas += collect_data_files("speech_recognition")   # contient flac.exe, utilisé par la reconnaissance vocale
datas += collect_data_files("soundcard")

hiddenimports = (
    ["capri", "serveur", "mode_cours", "chemins", "plyer.platforms.win.notification"]
    + collect_submodules("asknews_sdk")
    + collect_submodules("google.genai")
)

a = Analysis(
    ["lanceur.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "pytest"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Capri",
    icon="installer/capri.ico" if __import__("os").path.exists("installer/capri.ico") else None,
    console=False,          # pas de fenêtre noire ; le serveur ouvre la sienne
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Capri", upx=False)
