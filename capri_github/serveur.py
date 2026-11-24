import os
import json
import secrets
import hmac
import socket
import io
import base64
import time
import shutil
import subprocess
import atexit
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
import urllib.request
from pathlib import Path
from flask import Flask, request, jsonify
from mode_cours import MoteurCours
from PIL import ImageGrab
import pyautogui

app = Flask(__name__)

# ==========================================
# CONFIGURATION & CAPRI
# ==========================================
from chemins import DONNEES, DOSSIER_EXE
# La config du serveur (clé d'accès générée automatiquement) vit dans ~/.capri,
# jamais dans le dossier du programme : elle ne finit donc pas sur GitHub.
CONFIG_FILE = str(DONNEES / "serveur_config.json")
DATA_GAMES = Path.home() / ".capri" / "games.json"
ngrok_process = None

# Le code PIN Windows n'est plus écrit dans le code.
# Pour activer /unlock, définis la variable d'environnement CAPRI_WINDOWS_PIN
# (ou "windows_pin" dans config.json). Sans PIN, /unlock est désactivé.

# Variable pour gérer la fenêtre d'écran noir
black_screen_window = None

# ==========================================
# GESTION DU BLOCAGE PHYSIQUE DE LA SOURIS
# ==========================================
class RECT(ctypes.Structure):
    _fields_ = [
        ('left', ctypes.c_long),
        ('top', ctypes.c_long),
        ('right', ctypes.c_long),
        ('bottom', ctypes.c_long)
    ]

def freeze_mouse():
    """Enferme la souris dans 1 seul pixel pour l'empêcher physiquement de bouger."""
    try:
        rect = RECT(0, 0, 1, 1)
        ctypes.windll.user32.ClipCursor(ctypes.byref(rect))
    except Exception as e:
        print(f"Erreur freeze_mouse: {e}")

def unfreeze_mouse():
    """Libère la souris."""
    try:
        ctypes.windll.user32.ClipCursor(None)
    except Exception as e:
        print(f"Erreur unfreeze_mouse: {e}")

# ==========================================
# GESTION DES CLÉS & RÉSEAU
# ==========================================
def generate_random_key():
    """Clé longue et aléatoire (32 caractères, impossible à deviner)."""
    return secrets.token_urlsafe(24)

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def load_key():
    cfg = load_config()
    key = str(cfg.get("access_key") or "")
    # Les anciennes clés de 8 caractères sont trop faciles à deviner : on en génère une nouvelle.
    if len(key) < 24:
        key = generate_random_key()
        cfg["access_key"] = key
        save_config(cfg)
        print("🔐 Nouvelle clé d'accès générée (l'ancienne était trop courte). Mets-la à jour sur ton téléphone.")
    return key

SECRET_KEY = load_key()
WINDOWS_PIN = os.environ.get("CAPRI_WINDOWS_PIN") or str(load_config().get("windows_pin") or "")

# ==========================================
# PROTECTION CONTRE LES ESSAIS DE CLÉS
# ==========================================
MAX_FAILS = 5            # essais ratés autorisés…
FAIL_WINDOW = 600        # …sur 10 minutes
BLOCK_TIME = 1800        # puis blocage 30 minutes
_fails = {}
_blocked = {}
_auth_lock = threading.Lock()

def client_id():
    # Derrière ngrok, la vraie IP est ajoutée en DERNIER dans X-Forwarded-For
    # (les valeurs du début peuvent être inventées par le client).
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[-1].strip() if fwd else request.remote_addr) or "?"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def verify_auth(req_key):
    """Vérifie la clé. Plus de clé « de secours » codée en dur, et blocage après 5 échecs."""
    cid = client_id()
    now = time.time()
    with _auth_lock:
        if _blocked.get(cid, 0) > now:
            return False
        ok = bool(req_key) and hmac.compare_digest(str(req_key).strip().encode(), SECRET_KEY.encode())
        if ok:
            _fails.pop(cid, None)
            return True
        recent = [t for t in _fails.get(cid, []) if now - t < FAIL_WINDOW] + [now]
        _fails[cid] = recent
        if len(recent) >= MAX_FAILS:
            _blocked[cid] = now + BLOCK_TIME
            _fails.pop(cid, None)
            print(f"⛔ {cid} bloqué 30 min après {MAX_FAILS} mauvaises clés.")
        return False

def load_games():
    try:
        with open(DATA_GAMES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def find_registered_game(path=None, name=None):
    """Seuls les jeux/programmes enregistrés dans Capri peuvent être lancés ou fermés à distance."""
    for g in load_games():
        gp, gn = str(g.get("path", "")), str(g.get("name", ""))
        if path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(gp)):
            return g
        if name and name.strip().lower() == gn.strip().lower():
            return g
    return None

def get_running_process_names():
    """Récupère en bloc tous les processus Windows en cours d'exécution."""
    try:
        output = subprocess.check_output('tasklist /FO CSV /NH', shell=True).decode('cp1252', errors='ignore')
        running = set()
        for line in output.splitlines():
            parts = line.split('","')
            if parts:
                running.add(parts[0].replace('"', '').strip().lower())
        return running
    except Exception:
        return set()

# ==========================================
# GESTION AUTOMATIQUE DE NGROK
# ==========================================
def find_ngrok_binary():
    script_dir = str(DOSSIER_EXE)
    candidates = [
        os.path.join(script_dir, "ngrok.exe"),
        str(DONNEES / "ngrok.exe"),
        os.path.join(os.getcwd(), "ngrok.exe"),
        "ngrok.exe",
        "ngrok"
    ]
    for path in candidates:
        if os.path.isabs(path) and os.path.exists(path):
            return path
        elif not os.path.isabs(path) and os.path.exists(os.path.join(script_dir, path)):
            return os.path.join(script_dir, path)
        elif shutil.which(path):
            return path
    return "ngrok"

def start_ngrok():
    global ngrok_process
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as resp:
            data = json.loads(resp.read().decode())
            if data.get("tunnels"):
                for t in data["tunnels"]:
                    if t.get("proto") == "https":
                        return t.get("public_url")
                return data["tunnels"][0]["public_url"]
    except Exception:
        pass

    ngrok_bin = find_ngrok_binary()
    try:
        ngrok_process = subprocess.Popen(
            [ngrok_bin, "http", "5000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
    except Exception as e:
        print(f"⚠️ Erreur lors du lancement de ngrok : {e}")
        return None

    print("⏳ Démarrage du tunnel Ngrok en cours...")
    for _ in range(20):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as resp:
                data = json.loads(resp.read().decode())
                tunnels = data.get("tunnels", [])
                for t in tunnels:
                    if t.get("proto") == "https":
                        return t.get("public_url")
                if tunnels:
                    return tunnels[0]["public_url"]
        except Exception:
            pass

    return None

def cleanup():
    global ngrok_process
    unfreeze_mouse()  # S'assure que la souris est débloquée si on coupe le serveur
    if ngrok_process:
        try:
            ngrok_process.terminate()
        except Exception:
            pass

atexit.register(cleanup)

# ==========================================
# GESTION DU FILTRE ÉCRAN NOIR (AVEC VERROUILLAGE SOURIS)
# ==========================================
def run_black_screen():
    global black_screen_window
    freeze_mouse()  # Piège la souris dès l'apparition de l'écran noir

    root = tk.Tk()
    root.attributes('-fullscreen', True)
    root.attributes('-topmost', True)
    root.configure(bg='black')
    root.config(cursor="none")

    # Bloque les clics et les touches physiques sur le PC
    root.bind("<Motion>", lambda e: freeze_mouse())
    root.bind("<Button-1>", lambda e: "break")
    root.bind("<Button-2>", lambda e: "break")
    root.bind("<Button-3>", lambda e: "break")
    root.bind("<Key>", lambda e: "break")
    root.protocol("WM_DELETE_WINDOW", lambda: None)

    black_screen_window = root
    root.mainloop()

# ==========================================
# ROUTES DE L'API FLASK
# ==========================================

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json or {}
    if verify_auth(data.get("key")):
        return jsonify({"status": "connected", "message": "Accès autorisé"}), 200
    return jsonify({"status": "error", "message": "Clé incorrecte"}), 403

@app.route('/apps', methods=['POST'])
def list_apps():
    """Lit les jeux enregistrés dans Capri et indique leur statut en direct."""
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403

    games = []
    if DATA_GAMES.exists():
        try:
            with open(DATA_GAMES, "r", encoding="utf-8") as f:
                games = json.load(f)
        except Exception:
            games = []

    running_procs = get_running_process_names()
    apps_list = []
    for g in games:
        path = g.get("path", "")
        name = g.get("name", "Inconnu")
        exe_name = os.path.basename(path).lower()
        if exe_name.endswith(".lnk"):
            exe_name = f"{os.path.splitext(exe_name)[0]}.exe"

        is_running = (exe_name in running_procs) or (f"{name.lower()}.exe" in running_procs)

        apps_list.append({
            "name": name,
            "path": path,
            "exe": exe_name,
            "is_running": is_running
        })

    return jsonify({"status": "success", "apps": apps_list}), 200

@app.route('/launch', methods=['POST'])
def launch():
    """Lance un jeu ou programme Capri."""
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403

    path = data.get("path") or data.get("app")
    if not path:
        return jsonify({"status": "error", "message": "Chemin manquant"}), 400

    game = find_registered_game(path=path, name=data.get("name"))
    if not game:
        return jsonify({"status": "error", "message": "Programme non enregistré dans Capri"}), 403
    path = game["path"]
    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "Fichier introuvable sur le PC"}), 404

    try:
        folder = os.path.dirname(path) or None
        if path.lower().endswith(".exe"):
            subprocess.Popen([path], cwd=folder)
        else:
            os.startfile(path)   # pas de shell : aucune commande ne peut être injectée
        return jsonify({"status": "success", "message": "Application lancée"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/close', methods=['POST'])
def close():
    """Ferme radicalement le jeu, résout les raccourcis .lnk et scanne les fenêtres."""
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403

    game = find_registered_game(path=data.get("path"), name=data.get("name"))
    if not game:
        return jsonify({"status": "error", "message": "Programme non enregistré dans Capri"}), 403
    name = str(game.get("name", ""))
    path = str(game.get("path", ""))
    exe = os.path.basename(path)
    if exe.lower().endswith(".lnk"):
        exe = os.path.splitext(exe)[0] + ".exe"

    print(f"\n🔴 [DEMANDE DE FERMETURE] Jeu: '{name}' | Exe: '{exe}' | Chemin: '{path}'")

    real_exe = None
    if path and path.lower().endswith(".lnk") and os.path.exists(path):
        try:
            ps_cmd = "$sh = New-Object -ComObject WScript.Shell; $t = $sh.CreateShortcut($env:CAPRI_PATH).TargetPath; Split-Path $t -Leaf"
            out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps_cmd], text=True,
                                          env={**os.environ, "CAPRI_PATH": path}).strip()
            if out:
                real_exe = out.lower()
                print(f"🎯 Cible du raccourci .lnk résolue : {real_exe}")
        except Exception:
            pass

    targets = []
    if real_exe:
        targets.append(real_exe)
    if exe:
        targets.append(exe if exe.lower().endswith(".exe") else f"{exe}.exe")
    if path:
        base = os.path.basename(path)
        if base.lower().endswith(".exe"):
            targets.append(base)
    if name:
        clean = "".join(c for c in name if c.isalnum() or c in "._-").strip()
        targets.append(f"{clean}.exe")
        targets.append(f"{name.split()[0]}.exe")

    targets = list(dict.fromkeys(targets))

    killed = False
    details = []

    for target in targets:
        if not target.lower().endswith(".exe") or not all(c.isalnum() or c in "._- " for c in target):
            continue
        res = subprocess.run(["taskkill", "/F", "/T", "/IM", target], capture_output=True, text=True)
        if res.returncode == 0:
            killed = True
            details.append(target)
            print(f"✅ Fermé via taskkill : {target}")

    if not killed:
        search_term = name or (exe.replace(".exe", "") if exe else "")
        search_term = search_term.replace("'", "").replace('"', '')
        if search_term:
            # Le terme passe par une variable d'environnement : rien n'est interprété comme du code
            ps_kill = """
            $t = $env:CAPRI_TERM
            $p = Get-Process | Where-Object {
                $_.MainWindowTitle -like "*$t*" -or $_.ProcessName -like "*$t*"
            }
            if ($p) { $p | Stop-Process -Force; Write-Output "OK" }
            """
            try:
                res_ps = subprocess.run(["powershell", "-NoProfile", "-Command", ps_kill], capture_output=True, text=True,
                                        env={**os.environ, "CAPRI_TERM": search_term})
                if "OK" in res_ps.stdout:
                    killed = True
                    details.append(search_term)
                    print(f"✅ Fermé via PowerShell (titre/nom de fenêtre) : {search_term}")
            except Exception as e:
                print(f"Erreur PowerShell: {e}")

    if killed:
        return jsonify({"status": "success", "message": f"Fermé avec succès : {', '.join(details)}"}), 200
    else:
        print("❌ Aucun processus correspondant trouvé sous Windows.")
        return jsonify({"status": "warning", "message": "Aucun processus trouvé pour ce jeu"}), 200

@app.route('/screen', methods=['POST'])
def screen():
    """Prend une capture d'écran, la compresse et la renvoie en direct."""
    data = request.json or {}
    if verify_auth(data.get("key")):
        try:
            img = ImageGrab.grab()
            w, h = img.size
            ratio = 960 / w
            resized = img.resize((960, int(h * ratio)))

            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=45)
            img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return jsonify({"status": "success", "image": img_b64}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error", "message": "Non autorisé"}), 403

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Éteint le PC."""
    data = request.json or {}
    if verify_auth(data.get("key")):
        os.system("shutdown /s /t 1")
        return jsonify({"status": "success", "message": "PC en cours d'extinction"}), 200
    return jsonify({"status": "error", "message": "Non autorisé"}), 403

# ==========================================
# 1. VERROUILLAGE WINDOWS
# ==========================================
@app.route('/lock', methods=['POST'])
def lock():
    """Verrouille la session Windows."""
    data = request.json or {}
    if verify_auth(data.get("key")):
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return jsonify({"status": "success", "message": "PC Verrouillé"}), 200
    return jsonify({"status": "error", "message": "Non autorisé"}), 403

# ==========================================
# 2. DÉVERROUILLAGE WINDOWS (TEST DIRECT NATIVE)
# ==========================================
@app.route('/unlock', methods=['POST'])
def unlock():
    """Tente le déverrouillage via les codes touches physiques (Pavé numérique)."""
    data = request.json or {}
    if verify_auth(data.get("key")):
        if not WINDOWS_PIN:
            return jsonify({"status": "error", "message": "Déverrouillage désactivé (aucun PIN configuré)"}), 403
        def do_unlock():
            time.sleep(0.3)
            # 1. Réveille l'écran
            pyautogui.press('space')
            
            # 2. Attente de 2.2s
            time.sleep(2.2)
            
            # 3. Mappage des touches du Pavé Numérique (VK_NUMPAD0 = 0x60)
            numpad_keys = {
                '0': 0x60, '1': 0x61, '2': 0x62, '3': 0x63, '4': 0x64,
                '5': 0x65, '6': 0x66, '7': 0x67, '8': 0x68, '9': 0x69
            }
            
            for char in str(WINDOWS_PIN).strip():
                if char in numpad_keys:
                    vk = numpad_keys[char]
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0) # Touche enfoncée
                    time.sleep(0.08)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0) # Touche relâchée
                else:
                    pyautogui.press(char)
                time.sleep(0.2)
                
            time.sleep(0.4)
            # Touche Entrée (VK_RETURN = 0x0D)
            ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)

        threading.Thread(target=do_unlock, daemon=True).start()
        return jsonify({"status": "success", "message": "Déverrouillage en cours..."}), 200
    return jsonify({"status": "error", "message": "Non autorisé"}), 403

# ==========================================
# 3. MASQUER / DÉMASQUER L'ÉCRAN (ÉCRAN NOIR + BLOCAGE SOURIS)
# ==========================================
@app.route('/mask_screen', methods=['POST'])
def mask_screen():
    """Active ou désactive l'écran noir opaque et le piège à souris."""
    global black_screen_window
    data = request.json or {}
    if verify_auth(data.get("key")):
        enabled = data.get("enabled", False)

        if enabled:
            if black_screen_window is None:
                threading.Thread(target=run_black_screen, daemon=True).start()
        else:
            unfreeze_mouse()  # Débloque la souris immédiatement
            if black_screen_window is not None:
                try:
                    black_screen_window.destroy()
                except Exception:
                    pass
                black_screen_window = None

        return jsonify({"status": "success", "message": "Écran masqué" if enabled else "Écran visible", "enabled": enabled}), 200
    return jsonify({"status": "error", "message": "Non autorisé"}), 403

# ==========================================
# 4. MODE COURS (enregistrement, tâches, alerte prénom)
# ==========================================
moteur_cours = MoteurCours(str(DONNEES / "cours"), load_config)

@app.route('/cours/start', methods=['POST'])
def cours_start():
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403
    ok, msg = moteur_cours.demarrer()
    return jsonify({"status": "success" if ok else "error", "message": msg}), 200 if ok else 409

@app.route('/cours/stop', methods=['POST'])
def cours_stop():
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403
    ok, msg = moteur_cours.arreter()
    return jsonify({"status": "success" if ok else "error", "message": msg}), 200 if ok else 409

@app.route('/cours/etat', methods=['POST'])
def cours_etat():
    """Renvoie l'état du mode cours et les événements depuis l'id `depuis`."""
    data = request.json or {}
    if not verify_auth(data.get("key")):
        return jsonify({"status": "error", "message": "Non autorisé"}), 403
    try:
        depuis = int(data.get("depuis") or 0)
    except (TypeError, ValueError):
        depuis = 0
    return jsonify({"status": "success", **moteur_cours.etat(depuis)}), 200

# ==========================================
# LANCEMENT
# ==========================================
def main():
    public_url = start_ngrok()

    print("\n" + "="*50)
    print("🚀 SERVEUR PC REMOTE & NGROK DÉMARRÉS !")
    print("="*50)
    print(f"📍 IP locale (Wi-Fi)       : {get_local_ip()}")
    print(f"🔑 TA CLÉ D'ACCÈS           : {SECRET_KEY}")
    print(f"🔓 Déverrouillage à distance : {'activé' if WINDOWS_PIN else 'désactivé (aucun PIN configuré)'}")
    if public_url:
        print(f"🌐 LIEN NGROK (4G/Partout)  : {public_url}")
    else:
        print("⚠️ Ngrok n'a pas pu démarrer automatiquement.")
    print("="*50)
    print("Laisse uniquement cette fenêtre ouverte pour contrôler ton PC.\n")

    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()
