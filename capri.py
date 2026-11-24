#!/usr/bin/env python3
# ============================================================================
# CAPRI — version complète (stabilité + vocal + Discord + HUD C# + Help & Info)
# ============================================================================
import difflib
import json
import math
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import time
import threading
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, simpledialog, ttk
import unicodedata
from pathlib import Path
import ctypes
from ctypes import wintypes
import atexit
import urllib.parse
import socket

def send_to_csharp_hud(text, state="speaking", duration=0):
    """Envoie en direct le message, l'état visuel et la durée au HUD C#."""
    try:
        payload = json.dumps({"text": text, "state": state, "duration": duration}, ensure_ascii=False) + "\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(("127.0.0.1", 45789))
            s.sendall(payload.encode("utf-8"))
    except Exception:
        pass

# Import Pillow pour les sprites et icônes
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Import IA optionnel
try:
    from google import genai
    IA_AVAILABLE = True
except ImportError:
    IA_AVAILABLE = False

# Import AskNews (actualités) optionnel
try:
    from asknews_sdk import AskNewsSDK
    ASKNEWS_AVAILABLE = True
except ImportError:
    ASKNEWS_AVAILABLE = False

# Import Vocal
try:
    import speech_recognition as sr
    VOCAL_AVAILABLE = True
except ImportError:
    VOCAL_AVAILABLE = False

# PyAutoGUI pour l'automatisation clavier/souris (OPTIMISÉ)
try:
    import pyautogui
    pyautogui.PAUSE = 0.015  # Accélération des inputs
    pyautogui.FAILSAFE = False  # Désactive le crash si la souris touche un coin
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# ==========================================
# DESIGN & DIMENSIONS COMPACTES
# ==========================================
SCALE = 0.72
W = int(300 * SCALE)   # ~216 px
CH = int(370 * SCALE)  # ~266 px
ENTRY_H = 38
BASE_Y = CH - 8

PINK = "#ff2a85"
CYAN = "#00f5ff"
VIOLET = "#7928ca"
BG_MAIN = "#0b0517"
BG_PANEL = "#110822"
BG_CARD = "#190c33"
BG_INPUT = "#221045"
BORDER_COLOR = "#341763"
GREEN_LED = "#10b981"
RED_LED = "#ef4444"
TEXT_DIM = "#9b85c2"

DATA_GAMES = Path.home() / ".capri" / "games.json"
DATA_CONFIG = Path.home() / ".capri" / "config.json"
ICONS_CACHE = Path.home() / ".capri" / "icons"
from chemins import RESSOURCES, DOSSIER_EXE, EST_EXE
SPRITES = RESSOURCES / "sprites"
SERVER_PATH = RESSOURCES / "serveur.py"

ICONS_CACHE.mkdir(parents=True, exist_ok=True)

# Contacts Discord : chaque utilisateur configure les siens dans la console (onglet CONTACTS).
# Fichier : ~/.capri/contacts.json -> [{"pseudo": "gougouz", "alias": ["lucas", "lukas", "lulu"]}]
DATA_CONTACTS = Path.home() / ".capri" / "contacts.json"
DISCORD_ALIASES = {}

def load_contacts():
    try: data = json.loads(DATA_CONTACTS.read_text(encoding="utf-8"))
    except Exception: data = []
    return [c for c in data if isinstance(c, dict) and str(c.get("pseudo", "")).strip()]

def rebuild_aliases(contacts):
    """Recalcule la table « mot prononcé -> pseudo Discord » (modifiée sur place)."""
    DISCORD_ALIASES.clear()
    for c in contacts:
        pseudo = str(c["pseudo"]).strip()
        for mot in [pseudo] + list(c.get("alias", [])):
            if (cle := norm(str(mot))): DISCORD_ALIASES[cle] = pseudo

DISCORD_HOTKEYS = {
    "mute": ["ctrl", "shift", "m"],
    "call": ["ctrl", "²"],
    "disconnect": ["ctrl", "shift", "o"],
}

COMMON_APPS = {
    "discord": os.path.expandvars(r"%LocalAppData%\Discord\Update.exe --processStart Discord.exe"),
    "discorde": os.path.expandvars(r"%LocalAppData%\Discord\Update.exe --processStart Discord.exe"),
    "discort": os.path.expandvars(r"%LocalAppData%\Discord\Update.exe --processStart Discord.exe"),
    "visual code": "code", "visual studio code": "code", "vs code": "code", "vscode": "code", "code": "code",
    "minecraft": "minecraft", "mine craft": "minecraft",
    "opera": "opera", "opera gx": "opera", "opéra": "opera",
    "chrome": "chrome", "firefox": "firefox", "edge": "msedge",
    "spotify": "spotify", "steam": "steam",
    "notepad": "notepad", "bloc note": "notepad", "bloc notes": "notepad",
    "calculatrice": "calc", "explorateur": "explorer"
}

KNOWN_SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "twitch": "https://www.twitch.tv", "netflix": "https://www.netflix.com",
    "reddit": "https://www.reddit.com", "chatgpt": "https://chatgpt.com",
    "twitter": "https://x.com", "x": "https://x.com",
    "instagram": "https://www.instagram.com", "github": "https://github.com",
    "tiktok": "https://www.tiktok.com", "amazon": "https://www.amazon.fr"
}

IDLE = ["lotus", "sit_cross", "sit_lean", "laptop_sit"]
FUN = ["peek", "ball", "hack", "flip"]
MOOD_POSES = {
    "excited": ["love", "ball", "flip", "hack"],
    "surprised": ["shake", "curious", "poke"],
    "curious": ["curious", "peek"],
    "bored": ["sit_lean", "laptop_sit", "sit_cross"],
    "sleepy": ["sleep"],
}
ALL_POSES = sorted(set(IDLE + FUN + ["sleep", "love", "shake", "curious", "poke"]))

def fix_names(text):
    # Les variantes de prénoms mal reconnues par la dictée se règlent maintenant
    # dans l'onglet CONTACTS (alias), plus de noms écrits en dur ici.
    return text

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join("".join(c if (c.isalnum() or c in ":,.?!-") else " " for c in s).split())

def resolve_contact(name):
    raw = (name or "").strip()
    key = norm(raw)
    if key in DISCORD_ALIASES: return DISCORD_ALIASES[key]
    close = difflib.get_close_matches(key, list(DISCORD_ALIASES.keys()), n=1, cutoff=0.86)
    if close: return DISCORD_ALIASES[close[0]]
    return raw.capitalize()

def load_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def format_discord_purple_message(message):
    clean_msg = message.strip()
    return f"```ansi\n\u001b[1;35m[Capri]\u001b[0m {clean_msg}\n```"

def get_hardware_info():
    if PSUTIL_AVAILABLE:
        try:
            cpu_pct = int(psutil.cpu_percent(interval=None))
            ram = psutil.virtual_memory()
            return cpu_pct, int(ram.percent), round(ram.used / (1024**3), 1), round(ram.total / (1024**3), 1)
        except Exception: pass
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return 15, int(stat.dwMemoryLoad), round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3), 1), round(stat.ullTotalPhys / (1024**3), 1)
    except Exception: pass
    return 15, 45, 7.2, 16.0

def fetch_active_apps_with_icons():
    ps_cmd = f"""
    Add-Type -AssemblyName System.Drawing
    $cache = '{str(ICONS_CACHE)}'
    Get-Process | Where-Object {{ $_.MainWindowTitle -ne '' }} | ForEach-Object {{
        $p = $_
        $path = ''
        try {{ $path = $p.Path }} catch {{}}
        $iconFile = Join-Path $cache "$($p.ProcessName).png"
        if ($path -and !(Test-Path $iconFile)) {{
            try {{
                $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
                $icon.ToBitmap().Save($iconFile, [System.Drawing.Imaging.ImageFormat]::Png)
            }} catch {{}}
        }}
        "$($p.ProcessName)|$($p.Id)|$($p.MainWindowTitle)"
    }}
    """
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_cmd], text=True, errors="replace", timeout=10,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        apps, seen = [], set()
        ignored = {"explorer", "applicationframehost", "systemsettings", "shellexperiencehost", "textinputhost"}
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                name, pid, title = parts[0], parts[1], parts[2]
                if name.lower() not in ignored and name.lower() not in seen:
                    seen.add(name.lower())
                    icon_path = ICONS_CACHE / f"{name}.png"
                    apps.append({"name": name, "pid": pid, "title": title[:24], "icon": str(icon_path) if icon_path.exists() else None})
        return apps
    except Exception: return []

def change_volume(action):
    try:
        if sys.platform == "win32":
            vk_map = {"up": 0xAF, "down": 0xAE, "mute": 0xAD, "playpause": 0xB3, "next": 0xB0, "prev": 0xB1}
            if action in vk_map:
                vk = vk_map[action]
                for _ in range(5 if action in ["up", "down"] else 1):
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return True
    except Exception: return False

def start_program(path):
    folder = os.path.dirname(path) or None
    if sys.platform == "win32":
        if path.lower().endswith(".exe"):
            try: subprocess.Popen([path], cwd=folder)
            except OSError as e:
                if getattr(e, "winerror", 0) == 740: os.startfile(path, "runas")
                else: raise
        else: os.startfile(path)
    else: subprocess.Popen([path], cwd=folder)

def launch_common(cmd):
    try:
        if " --" in cmd:
            exe, args = cmd.split(" --", 1)
            subprocess.Popen([exe.strip().strip('"')] + ("--" + args).split())
        elif cmd.endswith(".exe") and os.path.exists(cmd):
            subprocess.Popen([cmd])
        else:
            os.system(f'start "" "{cmd}"')
        return True
    except Exception:
        return False

def can_launch(name):
    n = name.strip().strip('"')
    if not n: return False
    if shutil.which(n) or os.path.exists(n): return True
    if re.search(r"[:\\/]", n) or n.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".url")): return True
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for suffix in ("", ".exe"):
                try:
                    winreg.CloseKey(winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{n}{suffix}"))
                    return True
                except OSError: pass
    except Exception: pass
    return False

def force_focus_window(hwnd):
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd): return False
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd): user32.ShowWindow(hwnd, 9)
    fore_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    app_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    if fore_thread != app_thread:
        user32.AttachThreadInput(fore_thread, app_thread, True)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        user32.AttachThreadInput(fore_thread, app_thread, False)
    else:
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    return True

def get_all_visible_windows():
    windows = []
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    my_pid = os.getpid()

    def enum_win_proc(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == my_pid: return True

                p_name = ""
                h_proc = kernel32.OpenProcess(0x1000, False, pid)
                if h_proc:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        p_name = os.path.basename(buf.value).lower().replace(".exe", "")
                    kernel32.CloseHandle(h_proc)

                if p_name and p_name not in {"progman", "explorer", "shellexperiencehost", "textinputhost", "systemsettings", "applicationframehost"}:
                    windows.append({"hwnd": hwnd, "title": title, "proc": p_name, "title_norm": norm(title), "proc_norm": norm(p_name), "pid": pid.value})
        return True

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(EnumWindowsProc(enum_win_proc), 0)
    return windows

def find_window_by_name(target_name):
    t_norm = norm(target_name)
    if t_norm in ["discorde", "discort", "dis corde"]: t_norm = "discord"

    all_wins = get_all_visible_windows()
    alias_norm = norm(COMMON_APPS.get(t_norm, t_norm))

    for win in all_wins:
        if t_norm in win["proc_norm"] or t_norm in win["title_norm"] or alias_norm in win["proc_norm"] or alias_norm in win["title_norm"]:
            return win["hwnd"], win["proc"].capitalize()

    words = [w for w in t_norm.split() if len(w) >= 3 and w not in ["le", "la", "les", "studio"]]
    for win in all_wins:
        for w in words:
            if w in win["proc_norm"] or w in win["title_norm"]:
                return win["hwnd"], win["proc"].capitalize()
    return None, None

def find_discord_window():
    for win in get_all_visible_windows():
        if win["proc_norm"] == "discord": return win["hwnd"]
    hwnd, _ = find_window_by_name("discord")
    return hwnd

def move_window_position(hwnd, position):
    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd): return False, "Fenêtre introuvable ou fermée."
    user32 = ctypes.windll.user32
    force_focus_window(hwnd)

    class RECT(ctypes.Structure): _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    work_rect = RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work_rect), 0)
    sx, sy, sw, sh = work_rect.left, work_rect.top, work_rect.right - work_rect.left, work_rect.bottom - work_rect.top

    if position == "unfullscreen":
        user32.ShowWindow(hwnd, 9)
        w_rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(w_rect))
        cw, ch = w_rect.right - w_rect.left, w_rect.bottom - w_rect.top
        if cw >= sw or ch >= sh:
            cw, ch = int(sw * 0.75), int(sh * 0.75)
            user32.MoveWindow(hwnd, sx + (sw - cw) // 2, sy + (sh - ch) // 2, cw, ch, True)
        return True, "Grand écran retiré !"

    if position == "fullscreen":
        user32.ShowWindow(hwnd, 3)
        return True, "Passé en grand écran !"

    user32.ShowWindow(hwnd, 9)
    half_w, half_h = sw // 2, sh // 2

    if position == "left": user32.MoveWindow(hwnd, sx, sy, half_w, sh, True); return True, "Calé à gauche !"
    elif position == "right": user32.MoveWindow(hwnd, sx + half_w, sy, half_w, sh, True); return True, "Calé à droite !"
    elif position == "center":
        cw, ch = int(sw * 0.72), int(sh * 0.72)
        user32.MoveWindow(hwnd, sx + (sw - cw) // 2, sy + (sh - ch) // 2, cw, ch, True)
        return True, "Centré au milieu !"
    return False, "Position non reconnue."

# Processus Windows que Capri ne doit jamais fermer
PROTECTED_PROCESSES = {
    "system", "idle", "csrss", "wininit", "winlogon", "services", "lsass", "smss", "svchost",
    "explorer", "dwm", "fontdrvhost", "sihost", "taskhostw", "ctfmon", "runtimebroker",
    "searchhost", "startmenuexperiencehost", "shellexperiencehost", "textinputhost",
    "securityhealthservice", "msmpeng", "audiodg", "spoolsv", "conhost", "python", "pythonw",
}

COMMAND_VERBS = {
    "deplace", "deplacer", "mets", "met", "place", "cale", "glisse",
    "appelle", "appeler", "telephone", "telephoner", "raccroche", "raccrocher",
    "quitte", "quitter", "sors", "sortir", "deconnecte", "deconnecter",
    "mute", "demute", "unmute", "muter",
    "ouvre", "ouvrir", "lance", "lancer", "demarre", "ferme", "fermer", "tue",
    "joue", "jouer", "cherche", "recherche", "trouve", "minimise", "reduis", "maximise", "agrandis", "positionne",
}

def extract_message_intent(raw_text):
    clean_norm = norm(re.sub(r"\bdeux points\b", ":", raw_text.strip(), flags=re.IGNORECASE))

    first_word = clean_norm.split()[0] if clean_norm.split() else ""
    if first_word in COMMAND_VERBS:
        return None, None, None

    pat_init = re.search(r"^(?:envoie|envoyer|ecris|ecrire|envoi)\s+(?:un\s+message\s+|un\s+msg\s+)?(?:a|pour)\s+(.+)$", clean_norm)
    if pat_init and not any(sep in pat_init.group(1).strip() for sep in [":", " que ", " qui dit "]):
        target = resolve_contact(pat_init.group(1).strip())
        if not any(v in pat_init.group(1).strip().split() for v in {"ouvre", "lance", "ferme", "mets", "place", "cale", "deplace"}):
            return "INIT", target, None

    pat_recip_first = re.search(r"^(?:envoie|envoyer|ecris|ecrire|envoi|dis)\s+(?:un\s+message\s+)?(?:a|pour)\s+(.+?)\s*(?::|que|,|\s+qui\s+dit)\s*(.+)$", clean_norm, re.IGNORECASE)
    if pat_recip_first:
        msg = re.sub(r"^[:\"'\s]+", "", pat_recip_first.group(2).strip()).strip()
        if norm(msg) not in ["un message", "message", "un msg", ""]:
            return "SEND", resolve_contact(pat_recip_first.group(1).strip()), msg

    for sep in [" a ", " pour "]:
        if sep in clean_norm:
            parts = clean_norm.rsplit(sep, 1)
            if len(parts) == 2:
                right_recip = norm(parts[1].strip())
                if any(d in right_recip for d in ["gauche", "droite", "milieu", "centre", "ecran"]):
                    continue

                left_clean = re.sub(r"^(?:envoie|envoyer|ecris|ecrire|envoi)\s+(?:un\s+message\s*)?(?::|,)?\s*", "", parts[0].strip(), flags=re.IGNORECASE).strip()
                left_clean = re.sub(r"^[:\"'\s]+", "", left_clean).strip()
                target = resolve_contact(right_recip)
                if left_clean and norm(left_clean) not in ["un message", "message", ""]: return "SEND", target, left_clean
                else: return "INIT", target, None

    pat_chat = re.search(r"(?:discussion de|discussion avec|ouvre la discussion de|va sur la discussion de)\s+(.+)$", clean_norm)
    if pat_chat: return "INIT", resolve_contact(pat_chat.group(1).strip()), None
    return None, None, None

CALL_PREFIXES = r"(?:appelle|appeler|telephone|telephoner|passe un appel|lance un appel|fais un appel|donne un coup de fil|call|appel)"

def extract_call_target(cmd):
    m = re.match(rf"^{CALL_PREFIXES}\s+(?:a\s+|pour\s+|avec\s+)?(.+)$", cmd.replace("-", " "))
    if not m: return None
    chunk = re.split(r"\b(?:puis|ensuite|et apres|apres|et|sur|en|dans)\b|[,;]", m.group(1))[0].strip()
    if not chunk or chunk in {"moi", "toi", "me", "nous"}: return None
    return chunk

def detect_discord_voice_action(cmd):
    words = set(cmd.replace("-", " ").split())
    if words & {"volume", "musique", "son"}: return None
    if words & {"raccroche", "raccrocher"}: return "leave"
    leave_verbs = {"quitte", "quitter", "sors", "sortir", "deconnecte", "deconnecter", "coupe", "couper", "pars"}
    if words & leave_verbs and words & {"vocal", "vocale", "appel", "call", "salon"}: return "leave"
    if words & {"mute", "muet", "muter", "demute", "demuter", "unmute"}: return "mute"
    if words & {"micro", "mic", "microphone"} and words & {"coupe", "coupes", "couper", "reactive", "reactiver", "remets", "remet", "desactive", "active", "ferme", "ouvre", "mets", "met", "enleve"}:
        return "mute"
    return None

def log_ia_error(msg):
    """Garde une trace des échecs de l'IA dans ~/.capri/ia_erreurs.txt (sans les clés)."""
    try:
        p = Path.home() / ".capri" / "ia_erreurs.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass

crash_lock = threading.Lock()
_last_crash_time = 0.0

def handle_crash(exc_type, exc_value, exc_tb):
    global _last_crash_time
    with crash_lock:
        try:
            now = time.time()
            if now - _last_crash_time < 5.0:
                sys.__excepthook__(exc_type, exc_value, exc_tb)
                return
            _last_crash_time = now

            error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            log_dir = Path.home() / ".capri" / "crash_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_path = log_dir / f"crash_{timestamp}.txt"

            content = f"=== CAPRI CRASH REPORT ===\nDate : {timestamp}\n\nSalut, j'ai eu un dysfonctionnement de mes systèmes !\nRaison de l'arrêt :\n\n{error_details}"
            log_path.write_text(content, encoding="utf-8")

            if sys.platform == "win32": os.startfile(log_path)
            else: subprocess.Popen(["xdg-open", str(log_path)])
        except Exception: pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = handle_crash

def thread_crash_handler(args):
    if args.exc_type is SystemExit: return
    handle_crash(args.exc_type, args.exc_value, args.exc_traceback)
threading.excepthook = thread_crash_handler

class Capri:
    def launch_csharp_hud(self):
        """Lance automatiquement le projet C# CapriDesktop."""
        candidates = [
            DOSSIER_EXE / "CapriDesktop",
            RESSOURCES / "CapriDesktop",
            Path.cwd() / "CapriDesktop"
        ]

        project_dir = next((p for p in candidates if p.exists()), None)
        if not project_dir:
            return

        if PSUTIL_AVAILABLE:
            for p in psutil.process_iter(['name']):
                try:
                    if "capridesktop" in (p.info['name'] or "").lower():
                        return
                except Exception:
                    pass

        try:
            built_exe = list(project_dir.glob("**/CapriDesktop.exe"))
            if built_exe:
                exe_path = built_exe[0]
                self.hud_process = subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
            else:
                self.hud_process = subprocess.Popen(
                    ["dotnet", "run", "--project", str(project_dir)],
                    cwd=str(project_dir),
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
        except Exception as e:
            print(f"Erreur lancement HUD C#: {e}")

    def kill_csharp_hud(self):
        """Ferme proprement le HUD C#."""
        if self.hud_process:
            try:
                self.hud_process.terminate()
            except Exception:
                pass
        if sys.platform == "win32":
            subprocess.run("taskkill /F /IM CapriDesktop.exe", shell=True, capture_output=True)

    def __init__(self):
        self.root = tk.Tk()
        self.root.report_callback_exception = handle_crash
        
        # Suivi d'inactivité pour capri_ennuie.gif (50 secondes)
        self.last_command_time = time.time()
        self.bored_triggered = False

        # Historique de recherche pour le clic automatique
        self.last_search_engine = "google"
        self.last_search_time = 0.0

        # Gestion du HUD C#
        self.hud_process = None
        self.launch_csharp_hud()
        atexit.register(self.kill_csharp_hud)

        # File d'attente UI
        self.ui_queue = queue.Queue()

        self.is_executing = False
        self.exec_lock = threading.Lock()
        self.last_launch_ok = False
        self.discord_muted = False
        self.pending_since = 0.0
        self.server_alive_cache = False

        self.root.title("CAPRI")
        self.sprites = self.load_sprites()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.bg = BG_MAIN
        try:
            self.root.attributes("-transparentcolor", "#010101")
            self.bg = "#010101"
        except tk.TclError: pass
        self.root.configure(bg=self.bg)

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.rx, self.ry = sw - W - 30, sh - CH - 60
        self.root.geometry(f"{W}x{CH}+{self.rx}+{self.ry}")

        self.cv = tk.Canvas(self.root, width=W, height=CH, bg=self.bg, highlightthickness=0)
        self.cv.pack()

        self.entry_visible = False
        self.entry = tk.Entry(self.root, bg=BG_INPUT, fg=CYAN, insertbackground=PINK, relief="flat", font=("Consolas", 10))
        self.entry.bind("<Return>", self.submit)
        self.entry.bind("<Escape>", lambda _: self.toggle_entry(False))

        self.games = load_json(DATA_GAMES, [])
        self.contacts = load_contacts(); rebuild_aliases(self.contacts)
        self.config = load_json(DATA_CONFIG, {"ai_mode": False, "auto_reply": False, "custom_cmds": {}, "api_key": "", "mic_index": None})

        self.t0 = time.time()
        self.mood, self.mood_until, self.last_mood = "happy", 0, "happy"
        self.pose, self.pose_until = random.choice(IDLE), 0
        self.text, self.shown, self.text_until = "", 0.0, 0
        self.last_input = time.time()
        self.glitch = 0
        self.parts = [[random.randint(8, W - 8), random.randint(0, CH), random.uniform(0.4, 1.4)] for _ in range(14)]

        self.pending_discord_action = None
        self.vocal_lock = threading.Lock()
        self.is_processing_vocal = False
        self.dictating = False   # dictée d'un message Discord en cours : l'écoute « Capri » se met en pause
        self.wake_word_running = True

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)

        self.server_process = None
        # Le serveur de contrôle à distance est désactivé par défaut :
        # il ne démarre tout seul que si l'option est cochée dans l'onglet SYSTÈME.
        if self.config.get("serveur_auto", False):
            self.launch_server_background()
        self.hud_win = None
        self.build_panel()

        self.alt1_lock = False
        self.ptt_active = False
        self.ptt_used_at = 0.0
        self.last_external_hwnd = None
        self.current_hardware = (15, 45, 7.2, 16.0)

        self.start_background_workers()

        if VOCAL_AVAILABLE:
            threading.Thread(target=self.continuous_wake_word_loop, daemon=True).start()

        self.say("Capri prête ! Dis 'Capri' ou fais Alt+1.", "excited", hold=4)

    def ui(self, fn):
        self.ui_queue.put(fn)

    def _drain_ui_queue(self):
        for _ in range(60):
            try: fn = self.ui_queue.get_nowait()
            except queue.Empty: break
            try: fn()
            except Exception as e: handle_crash(type(e), e, e.__traceback__)

    def say(self, text, mood=None, hold=None):
        def _update():
            self.text = text
            self.shown = 0.0
            self.text_until = time.time() + (hold or max(3, len(text) * 0.05 + 2))
            if mood: self.mood, self.mood_until = mood, time.time() + (hold or 5)

            if mood in ["sleepy", "off", "eteint"]:
                target_state = "eteint"
            elif mood in ["ennuie", "bored"]:
                target_state = "ennuie"
            else:
                target_state = "speaking"

            duration = int(hold) if hold else 0
            threading.Thread(target=send_to_csharp_hud, args=(text, target_state, duration), daemon=True).start()
        self.ui(_update)

    def clear_say(self):
        def _clear():
            self.text, self.shown, self.text_until = "", 0.0, 0
        self.ui(_clear)

    def wake(self):
        def _update():
            self.last_input = time.time()
            self.last_command_time = time.time()
            self.bored_triggered = False
            if self.mood == "sleepy": self.mood, self.mood_until = "surprised", time.time() + 3
        self.ui(_update)

    def toggle_entry(self, show=None):
        def _do():
            self.entry_visible = not self.entry_visible if show is None else show
            if self.entry_visible:
                self.root.geometry(f"{W}x{CH + ENTRY_H}+{self.rx}+{self.ry - ENTRY_H}")
                self.entry.pack(fill="x", padx=10, pady=(0, 6), ipady=4)
                self.entry.focus_force()
                self.wake()
            else:
                self.entry.pack_forget()
                self.root.geometry(f"{W}x{CH}+{self.rx}+{self.ry}")
                self.root.focus_set()
        self.ui(_do)

    def set_clipboard_safe(self, text):
        def _task():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update_idletasks()
            finally:
                done.set()
        if threading.current_thread() is threading.main_thread():
            done = threading.Event()
            _task()
            return
        done = threading.Event()
        self.ui(_task)
        done.wait(timeout=1.5)

    def start_background_workers(self):
        threading.Thread(target=self._keyboard_listener_worker, daemon=True).start()
        threading.Thread(target=self._window_tracker_worker, daemon=True).start()
        threading.Thread(target=self._hardware_worker, daemon=True).start()
        threading.Thread(target=self._server_status_worker, daemon=True).start()

    def _keyboard_listener_worker(self):
        while True:
            try:
                alt_pressed = (ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000) != 0
                k1_pressed = ((ctypes.windll.user32.GetAsyncKeyState(0x31) & 0x8000) != 0) or ((ctypes.windll.user32.GetAsyncKeyState(0x61) & 0x8000) != 0)

                if alt_pressed and k1_pressed:
                    if not self.alt1_lock:
                        self.alt1_lock = True
                        self.toggle_entry()
                else:
                    self.alt1_lock = False

                # Push-to-talk sur F8 (avant : la touche 0, qui déclenchait le micro dès qu'on tapait un nombre)
                k0_pressed = (ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000) != 0
                if k0_pressed and not self.entry_visible:
                    if not self.ptt_active:
                        self.ptt_active = True
                        self.ptt_used_at = time.time()
                        threading.Thread(target=self.ptt_listen_worker, daemon=True).start()
                elif self.ptt_active and not k0_pressed:
                    self.ptt_active = False
            except Exception: pass
            time.sleep(0.06)

    def _window_tracker_worker(self):
        while True:
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    pid = wintypes.DWORD()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value != os.getpid():
                        self.last_external_hwnd = hwnd
            except Exception: pass
            time.sleep(0.2)

    def _hardware_worker(self):
        while True:
            self.current_hardware = get_hardware_info()
            time.sleep(2.0)

    def _server_status_worker(self):
        while True:
            try: self.server_alive_cache = self.is_server_alive()
            except Exception: pass
            time.sleep(3.0)

    def load_sprites(self):
        imgs = {}
        for name in ALL_POSES:
            p = SPRITES / f"{name}.png"
            if not p.exists(): imgs[name] = tk.PhotoImage()
            else:
                if PIL_AVAILABLE:
                    try:
                        im = Image.open(p)
                        nw, nh = max(10, int(im.width * SCALE)), max(10, int(im.height * SCALE))
                        imgs[name] = ImageTk.PhotoImage(im.resize((nw, nh), Image.Resampling.LANCZOS))
                    except Exception: imgs[name] = tk.PhotoImage(file=str(p))
                else: imgs[name] = tk.PhotoImage(file=str(p))
        return imgs

    def get_selected_mic_index(self):
        if not VOCAL_AVAILABLE: return None
        saved_idx = self.config.get("mic_index")
        if saved_idx is not None:
            try:
                names = sr.Microphone.list_microphone_names()
                if 0 <= saved_idx < len(names): return saved_idx
            except Exception: pass
        return None

    def continuous_wake_word_loop(self):
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.energy_threshold = 300
        r.pause_threshold = 0.7
        r.non_speaking_duration = 0.5
        r.operation_timeout = 10

        while self.wake_word_running:
            if self.is_processing_vocal or self.ptt_active or self.is_executing or self.dictating:
                time.sleep(0.2); continue

            mic_index = self.get_selected_mic_index()
            listen_start = time.time()
            try:
                with self.vocal_lock:
                    with sr.Microphone(device_index=mic_index) as source:
                        r.adjust_for_ambient_noise(source, duration=0.3)
                        audio = r.listen(source, timeout=2.5, phrase_time_limit=14.0)

                # Écoute recouverte par un push-to-talk (ou une commande) : on jette ce qu'on a entendu
                if self.is_executing or self.ptt_active or self.ptt_used_at > listen_start: continue

                self.is_processing_vocal = True
                try:
                    raw_spoken = fix_names(r.recognize_google(audio, language="fr-FR"))
                    if re.search(r"\b(capri|kabri|cabri|capris|caprice)\b", norm(raw_spoken)):
                        self.handle_wake_word_flow(raw_spoken, r)
                finally:
                    self.is_processing_vocal = False
            except (sr.WaitTimeoutError, sr.UnknownValueError): continue
            except Exception: time.sleep(1.0)

    def handle_wake_word_flow(self, text, recognizer):
        cmd_direct = re.sub(r"\b(capri|kabri|cabri|capris|caprice)\b", "", text, flags=re.IGNORECASE).strip()
        if len(norm(cmd_direct)) > 2:
            self.process_command(cmd_direct, confirmed=True)
            return

        self.say("Oui ?", "curious", hold=3)
        try:
            with self.vocal_lock:
                with sr.Microphone(device_index=self.get_selected_mic_index()) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.25)
                    recognizer.pause_threshold, recognizer.non_speaking_duration = 1.0, 0.8
                    audio = recognizer.listen(source, timeout=1.1, phrase_time_limit=14.0)

            order_text = fix_names(recognizer.recognize_google(audio, language="fr-FR"))
            if order_text.strip():
                self.say("Compris, je fais ça !", "excited", hold=2)
                time.sleep(0.6)
                self.process_command(order_text, confirmed=True)
        except sr.WaitTimeoutError: self.say("", "happy", hold=0)
        except (sr.UnknownValueError, Exception): pass

    def ptt_listen_worker(self):
        if not VOCAL_AVAILABLE:
            self.say("Module vocal non installé !", "surprised")
            self.ptt_active = False
            return

        if self.is_executing or self.is_processing_vocal:
            self.say("Attends, je termine la commande précédente !", "surprised", hold=2)
            return

        self.say("🎤 Écoute (F8)...", "curious", hold=15)
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.operation_timeout = 10

        try:
            # Pas de vocal_lock ici : l'écoute « Capri » peut garder le micro jusqu'à ~2,5 s,
            # ce qui coupait le début de la phrase. Windows permet d'ouvrir le micro deux fois ;
            # l'écoute « Capri » ignore ce qu'elle a entendu pendant le push-to-talk.
            with sr.Microphone(device_index=self.get_selected_mic_index()) as source:
                    frames = []
                    while self.ptt_active:
                        try: frames.append(source.stream.read(source.CHUNK))
                        except Exception: break

                    if len(frames) > 5:
                        audio = sr.AudioData(b"".join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                        self.process_command(fix_names(r.recognize_google(audio, language="fr-FR")), confirmed=True)
                    else:
                        self.say("Parle en maintenant F8 !", "bored", hold=2)
        except Exception: self.say("Pas bien capté !", "bored", hold=2)

    def launch_server_background(self):
        if EST_EXE:
            # Version .exe : Capri.exe se relance lui-même en mode serveur
            cmd, cwd = [sys.executable, "--serveur"], str(DOSSIER_EXE)
        else:
            target = next((p for p in [SERVER_PATH, Path.cwd() / "serveur.py"] if p.exists()), None)
            if not target: return
            cmd, cwd = [sys.executable, str(target)], str(target.parent)
        if not self.is_server_alive():
            try:
                self.server_process = subprocess.Popen(cmd, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
                self.server_alive_cache = True
                atexit.register(self.kill_server)
            except Exception: pass

    def is_server_alive(self):
        if self.server_process and self.server_process.poll() is None: return True
        if PSUTIL_AVAILABLE:
            for p in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmdline = [str(c) for c in (p.info['cmdline'] or [])]
                    if (p.info['name'] or '').lower() in ('python.exe', 'pythonw.exe', 'py.exe') and any('serveur.py' in c for c in cmdline): return True
                    if (p.info['name'] or '').lower() == 'capri.exe' and '--serveur' in cmdline: return True
                except Exception: pass
        return False

    def kill_server(self):
        if self.server_process:
            try:
                if sys.platform == "win32":
                    # /T ferme aussi ngrok, lancé par le serveur
                    subprocess.run(f"taskkill /F /T /PID {self.server_process.pid}", shell=True, capture_output=True)
                else:
                    self.server_process.terminate()
            except Exception: pass
            self.server_process = None
        self.server_alive_cache = False

    def stop_server_from_panel(self):
        self.kill_server()
        self.say("Serveur à distance arrêté.", "happy", hold=2)
        self.srv_status_lbl.configure(text="○ SERVEUR ARRÊTÉ", fg=RED_LED)

    def toggle_server_auto(self):
        self.config["serveur_auto"] = bool(self.srv_auto_var.get()); save_json(DATA_CONFIG, self.config)

    # ==========================================
    # GESTION DES RECHERCHES ET ONGLETS OPERA
    # ==========================================
    def open_in_opera_tab(self, query_or_url, label=None):
        if not PYAUTOGUI_AVAILABLE:
            self.say("Pyautogui requis pour cette action !", "surprised")
            return

        hwnd = self.open_or_focus_app("opera") or self.open_or_focus_app("opera gx")
        if not hwnd:
            try:
                os.system('start opera')
                time.sleep(2.5)
                hwnd, _ = find_window_by_name("opera")
            except Exception: pass

        if hwnd:
            force_focus_window(hwnd)
            time.sleep(0.3)
            move_window_position(hwnd, "fullscreen")
            time.sleep(0.3)

        pyautogui.hotkey('ctrl', 't')
        time.sleep(0.4)

        clean_q = norm(query_or_url)
        url_to_open = KNOWN_SITES.get(clean_q, query_or_url)
        if not url_to_open.startswith("http://") and not url_to_open.startswith("https://"):
            if "." in url_to_open and " " not in url_to_open:
                url_to_open = f"https://{url_to_open}"
            else:
                url_to_open = f"https://www.google.com/search?q={urllib.parse.quote_plus(url_to_open)}"

        self.last_search_engine = "youtube" if "youtube" in url_to_open else "google"
        self.last_search_time = time.time()

        self.set_clipboard_safe(url_to_open)
        time.sleep(0.15)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.1)
        pyautogui.press('enter')

        display_name = label or clean_q.capitalize()
        if label:
            self.say(f"Recherche de '{display_name}' lancée sur Opera !", "excited", hold=3)
        else:
            self.say(f"Onglet {display_name} ouvert dans Opera !", "excited", hold=3)


    # ==========================================
    # GESTION DU VPN OPERA (BADGE + BOUTON POWER)
    # ==========================================
    def toggle_opera_vpn(self):
        """Active/désactive le VPN Opera en cliquant sur le badge puis sur le bouton Power."""
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI requis pour activer le VPN !", "surprised")
            return False

        vpn_btn_path = RESSOURCES / "vpn_btn.png"
        vpn_power_path = RESSOURCES / "vpn_power.png"

        if not vpn_btn_path.is_file() or not vpn_power_path.is_file():
            self.say("Images vpn_btn.png ou vpn_power.png introuvables !", "surprised")
            return False

        hwnd = self.open_or_focus_app("opera") or self.open_or_focus_app("opera gx")
        if not hwnd and self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
            hwnd = self.last_external_hwnd
        if hwnd:
            force_focus_window(hwnd)
            time.sleep(0.3)

        # 1. Clic sur le badge VPN
        badge_pos = None
        for _ in range(8):
            try:
                b = pyautogui.locateOnScreen(str(vpn_btn_path), confidence=0.7)
            except (Exception, getattr(pyautogui, "ImageNotFoundException", Exception)):
                b = None

            if b:
                badge_pos = pyautogui.center(b)
                pyautogui.click(badge_pos)
                break
            time.sleep(0.15)

        if not badge_pos:
            self.say("Je ne vois pas le badge VPN sur Opera !", "surprised")
            return False

        # 2. Temps d'apparition de la pop-up
        time.sleep(0.5)

        # 3. Clic sur le bouton de lancement (Power) avec seuil adapté et tolérant
        power_pos = None
        for _ in range(12):
            try:
                p = pyautogui.locateOnScreen(str(vpn_power_path), confidence=0.55)
            except (Exception, getattr(pyautogui, "ImageNotFoundException", Exception)):
                p = None

            if p:
                power_pos = pyautogui.center(p)
                pyautogui.click(power_pos)
                break
            time.sleep(0.15)

        if power_pos:
            self.say("VPN activé sur Opera !", "excited", hold=3)
            return True
        else:
            self.say("Bouton de lancement du VPN introuvable !", "surprised")
            return False

    # ==========================================
    # CLIC AUTOMATIQUE SUR LE PREMIER LIEN
    # ==========================================
    def click_first_search_link(self):
        if not PYAUTOGUI_AVAILABLE:
            self.say("Pyautogui requis pour cette action !", "surprised")
            return False

        elapsed = time.time() - getattr(self, "last_search_time", 0.0)
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)

        hwnd = self.open_or_focus_app("opera") or self.open_or_focus_app("opera gx")
        if not hwnd and self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
            hwnd = self.last_external_hwnd
        if hwnd:
            force_focus_window(hwnd)
            time.sleep(0.25)

        sw, sh = pyautogui.size()   # (Tkinter ne doit pas être appelé depuis ce thread)

        engine = getattr(self, "last_search_engine", "google")

        if engine == "youtube":
            target_x = int(sw * 0.35)
            target_y = int(sh * 0.28)
            pyautogui.moveTo(target_x, target_y, duration=0.15)
            pyautogui.click()
            self.say("Première vidéo YouTube ouverte !", "excited", hold=3)
            return True

        target_x = int(sw * 0.26)
        target_y = int(sh * 0.31)
        pyautogui.moveTo(target_x, target_y, duration=0.15)
        pyautogui.click()
        time.sleep(0.08)
        pyautogui.press('enter')

        self.say("Premier résultat ouvert !", "excited", hold=3)
        return True

    def open_apps_hud(self):
        if self.hud_win and self.hud_win.winfo_exists(): self.hud_win.lift(); return

        self.hud_win = tk.Toplevel(self.root)
        self.hud_win.overrideredirect(True)
        self.hud_win.attributes("-topmost", True)
        self.hud_win.configure(bg=BG_PANEL)
        self.hud_win.geometry(f"300x380+{max(20, self.rx - 320)}+{self.ry}")

        def start_drag(e): self.hud_win._dx, self.hud_win._dy = e.x, e.y
        def do_drag(e): self.hud_win.geometry(f"+{self.hud_win.winfo_x() + (e.x - self.hud_win._dx)}+{self.hud_win.winfo_y() + (e.y - self.hud_win._dy)}")

        hdr = tk.Frame(self.hud_win, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        hdr.pack(fill="x", padx=4, pady=4)
        hdr.bind("<ButtonPress-1>", start_drag)
        hdr.bind("<B1-Motion>", do_drag)

        title = tk.Label(hdr, text="◆ HUD // APPLIS OUVERTES", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold"))
        title.pack(side="left", padx=8, pady=6)
        title.bind("<ButtonPress-1>", start_drag)
        title.bind("<B1-Motion>", do_drag)

        tk.Button(hdr, text="✕", command=self.hud_win.destroy, bg=BG_CARD, fg=PINK, relief="flat", font=("Consolas", 10, "bold"), bd=0).pack(side="right", padx=6)
        tk.Button(hdr, text="⟳", command=self.refresh_hud_apps, bg=BG_CARD, fg=CYAN, relief="flat", font=("Consolas", 11), bd=0).pack(side="right", padx=2)

        self.hud_canvas_scroll = tk.Canvas(self.hud_win, bg=BG_PANEL, highlightthickness=0)
        self.hud_canvas_scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self.hud_container = tk.Frame(self.hud_canvas_scroll, bg=BG_PANEL)
        self.hud_canvas_scroll.create_window((0, 0), window=self.hud_container, anchor="nw")
        self.hud_container.bind("<Configure>", lambda _: self.hud_canvas_scroll.configure(scrollregion=self.hud_canvas_scroll.bbox("all")))

        self.hud_icon_refs = []
        self.refresh_hud_apps()

    def refresh_hud_apps(self):
        if not (self.hud_win and self.hud_win.winfo_exists()): return
        for w in self.hud_container.winfo_children(): w.destroy()
        self.hud_icon_refs.clear()
        loading_lbl = tk.Label(self.hud_container, text="Scan des fenêtres...", bg=BG_PANEL, fg=TEXT_DIM, font=("Consolas", 9))
        loading_lbl.pack(pady=20)

        def _fetch():
            apps = fetch_active_apps_with_icons()
            self.ui(lambda: self._render_hud_apps(apps, loading_lbl))
        threading.Thread(target=_fetch, daemon=True).start()

    def _render_hud_apps(self, apps, loading_lbl):
        try:
            if not (self.hud_win and self.hud_win.winfo_exists() and loading_lbl.winfo_exists()): return
            loading_lbl.destroy()
        except tk.TclError: return
        if not apps: tk.Label(self.hud_container, text="Aucune fenêtre active détectée.", bg=BG_PANEL, fg=TEXT_DIM, font=("Consolas", 9)).pack(pady=20); return

        grid_frame = tk.Frame(self.hud_container, bg=BG_PANEL)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.columnconfigure((0, 1, 2), weight=1)

        for idx, app in enumerate(apps):
            r, c = idx // 3, idx % 3
            tile = tk.Frame(grid_frame, bg=BG_CARD, width=86, height=92, highlightbackground=BORDER_COLOR, highlightthickness=1)
            tile.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            tile.grid_propagate(False)

            tk.Button(tile, text="✕", bg=RED_LED, fg="white", font=("Consolas", 7, "bold"), relief="flat", bd=0, padx=2, pady=0, command=lambda p=app["pid"], n=app["name"]: self.kill_app_from_hud(p, n)).place(x=3, y=3, width=16, height=16)

            icon_img = None
            if PIL_AVAILABLE and app["icon"] and os.path.exists(app["icon"]):
                try: icon_img = ImageTk.PhotoImage(Image.open(app["icon"]).resize((32, 32), Image.Resampling.LANCZOS)); self.hud_icon_refs.append(icon_img)
                except Exception: pass

            if icon_img: tk.Label(tile, image=icon_img, bg=BG_CARD).place(x=27, y=18)
            else: tk.Label(tile, text="💻", font=("Consolas", 18), bg=BG_CARD, fg=CYAN).place(x=27, y=14)
            tk.Label(tile, text=app["name"][:9], bg=BG_CARD, fg="white", font=("Consolas", 8, "bold")).place(x=2, y=62, width=82)

    def kill_app_from_hud(self, pid, name):
        try:
            subprocess.run(f'taskkill /F /T /PID {pid}', shell=True, capture_output=True)
            self.say(f"{name} neutralisé !", "excited", hold=3)
            self.root.after(300, self.refresh_hud_apps)
        except Exception as e: self.say(f"Erreur fermeture : {e}", "surprised")

    # ==========================================
    # CONSOLE & TERMINAL (SYS, HELP, INFO, ETC.)
    # ==========================================
    def build_panel(self):
        self.win = tk.Toplevel(self.root)
        self.win.title("CAPRI // NEURAL TERMINAL")
        self.win.configure(bg=BG_PANEL)
        self.win.minsize(480, 500)
        self.win.resizable(True, True)   # étirable dans les deux sens
        self.win.protocol("WM_DELETE_WINDOW", self.close_panel)

        header = tk.Frame(self.win, bg=BG_PANEL)
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(header, text="◆ CAPRI OS // V4.6 TERMINAL", bg=BG_PANEL, fg=CYAN, font=("Consolas", 11, "bold")).pack(side="left")
        tk.Button(header, text="✕", command=self.close_panel, bg=BG_PANEL, fg=PINK, relief="flat", font=("Consolas", 12, "bold"), bd=0).pack(side="right")

        nav_frame = tk.Frame(self.win, bg=BG_PANEL)
        nav_frame.pack(fill="x", padx=10, pady=6)
        self.tab_buttons, self.tab_frames = {}, {}

        # 6 onglets avec HELP et INFORMATION
        tabs = [
            ("sys", "⚡ SYSTÈME"),
            ("help", "📖 HELP"),
            ("info", "ℹ️ INFO"),
            ("games", "🎮 JEUX"),
            ("ai", "🧠 IA"),
            ("cmd", "⚙️ CMD"),
            ("contacts", "👥 CONTACTS")
        ]

        for tab_id, tab_label in tabs:
            btn = tk.Button(nav_frame, text=tab_label, relief="flat", font=("Consolas", 8, "bold"), bg=BG_CARD, fg=TEXT_DIM, bd=0, padx=6, pady=5, command=lambda tid=tab_id: self.switch_tab(tid))
            btn.pack(side="left", padx=2, expand=True, fill="x")
            self.tab_buttons[tab_id] = btn
            self.tab_frames[tab_id] = tk.Frame(self.win, bg=BG_PANEL)

        self._build_sys_tab(self.tab_frames["sys"])
        self._build_help_tab(self.tab_frames["help"])
        self._build_info_tab(self.tab_frames["info"])
        self._build_games_tab(self.tab_frames["games"])
        self._build_ai_tab(self.tab_frames["ai"])
        self._build_cmd_tab(self.tab_frames["cmd"])
        self._build_contacts_tab(self.tab_frames["contacts"])

        self.switch_tab("sys")
        self.win.update_idletasks()
        self.win.geometry(f"560x680+{max(0, self.rx - 575)}+{max(0, self.ry - 50)}")
        self.win.withdraw()

    @staticmethod
    def _wrap_label(lbl):
        """Le texte se replie selon la largeur disponible (fenêtre redimensionnable)."""
        lbl.bind("<Configure>", lambda e: e.widget.configure(wraplength=max(150, e.width - 8)))
        return lbl

    def switch_tab(self, active_id):
        for tid, frame in self.tab_frames.items():
            if tid == active_id:
                frame.pack(fill="both", expand=True, padx=14, pady=8)
                self.tab_buttons[tid].configure(bg=PINK, fg="white")
            else:
                frame.pack_forget()
                self.tab_buttons[tid].configure(bg=BG_CARD, fg=TEXT_DIM)

    # ------------------------------------------
    # NOUVEL ONGLET : HELP (COMMANDES VOCALES)
    # ------------------------------------------
    def _build_help_tab(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=4)

        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="MANUEL DES COMMANDES VOCALES", bg=BG_CARD, fg=CYAN, font=("Consolas", 10, "bold")).pack(side="left")

        canvas = tk.Canvas(card, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_CARD)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        inner_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=380)
        # Le contenu suit la largeur de la fenêtre quand on l'étire
        canvas.bind("<Configure>", lambda e, c=canvas, i=inner_id: c.itemconfigure(i, width=max(200, e.width)))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
        scrollbar.pack(side="right", fill="y", padx=(0, 6), pady=6)

        categories = [
            ("🔴 SYSTÈME & ARRÊT", [
                ("« Éteins-toi » / « Arrête-toi »", "Ferme Capri et le HUD C# proprement."),
                ("« Ouvre la console »", "Affiche ce terminal système de commandes."),
                ("« Ferme la console »", "Replie ce terminal en arrière-plan."),
                ("« Réduis tout » / « Bureau »", "Minimise tout et affiche le bureau Windows.")
            ]),
            ("🌐 NAVIGATION & RECHERCHE", [
                ("« Cherche sur Google [recherche] »", "Ouvre Opera et lance la recherche Google."),
                ("« Cherche sur Opera [recherche] »", "Recherche via Google dans un onglet Opera."),
                ("« Cherche sur YouTube [recherche] »", "Recherche directement sur YouTube."),
                ("« Clique sur le premier lien »", "Ouvre automatiquement le 1er résultat web/vidéo."),
                ("« Ferme l'onglet »", "Ferme l'onglet ouvert actif (Ctrl+W)."),
                ("« Active le VPN »", "Clique le badge VPN puis le bouton Power.")
            ]),
            ("🎧 DISCORD & APPELS", [
                ("« Appelle [contact] »", "Lance un appel Discord (contacts réglés dans l'onglet CONTACTS)."),
                ("« Raccroche » / « Quitte le vocal »", "Coupe l'appel en cours."),
                ("« Mute » / « Coupe mon micro »", "Bascule ton micro Discord (Ctrl+Maj+M)."),
                ("« Envoie un message à [nom] »", "Ouvre la discussion pour dicter ton message.")
            ]),
            ("🪟 GESTION DES FENÊTRES", [
                ("« Mets [appli] à gauche / à droite »", "Cale la fenêtre sur la moitié d'écran voulue."),
                ("« Mets [appli] au milieu »", "Centre la fenêtre à l'écran."),
                ("« Mets [appli] en grand écran »", "Maximise la fenêtre."),
                ("« Enlève le grand écran »", "Restaure la taille normale de fenêtre.")
            ]),
            ("🔊 MULTIMÉDIA & SON", [
                ("« Monte le son » / « Baisse le son »", "Ajuste le volume sonore principal."),
                ("« Coupe le son » / « Muet »", "Coupe ou réactive le son Windows."),
                ("« Mets en pause » / « Play »", "Met en pause ou relance la musique."),
                ("« Musique suivante »", "Passe à la piste musicale suivante.")
            ]),
            ("🎲 FUN & DIVERS", [
                ("« Pile ou face »", "Tire au sort Pile ou Face."),
                ("« Lance un dé »", "Donne un chiffre au hasard entre 1 et 6."),
                ("« Comment ça va ? »", "Prend des nouvelles de l'humeur de Capri.")
            ])
        ]

        for cat_title, cmds in categories:
            lbl_cat = tk.Label(scroll_frame, text=cat_title, bg=BG_CARD, fg=PINK, font=("Consolas", 9, "bold"))
            lbl_cat.pack(anchor="w", padx=6, pady=(10, 3))

            for trigger, desc in cmds:
                row = tk.Frame(scroll_frame, bg=BG_INPUT, highlightbackground=BORDER_COLOR, highlightthickness=1)
                row.pack(fill="x", padx=6, pady=2)
                tk.Label(row, text=trigger, bg=BG_INPUT, fg=CYAN, font=("Consolas", 8, "bold")).pack(anchor="w", padx=6, pady=(3, 1))
                self._wrap_label(tk.Label(row, text=desc, bg=BG_INPUT, fg="#e2e8f0", font=("Consolas", 8), wraplength=360, justify="left", anchor="w")).pack(anchor="w", fill="x", padx=6, pady=(0, 4))

    # ------------------------------------------
    # NOUVEL ONGLET : INFO (ARCHITECTURE & FONCTIONNEMENT)
    # ------------------------------------------
    def _build_info_tab(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=4)

        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="ARCHITECTURE TECHNIQUE // CAPRI OS", bg=BG_CARD, fg=CYAN, font=("Consolas", 10, "bold")).pack(side="left")

        canvas = tk.Canvas(card, bg=BG_CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_CARD)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        inner_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=380)
        # Le contenu suit la largeur de la fenêtre quand on l'étire
        canvas.bind("<Configure>", lambda e, c=canvas, i=inner_id: c.itemconfigure(i, width=max(200, e.width)))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
        scrollbar.pack(side="right", fill="y", padx=(0, 6), pady=6)

        sections = [
            ("🎤 1. RECONNAISSANCE VOCALE (AUDIO)", [
                "• SpeechRecognition + Google Speech API : conversion de la parole en texte (fr-FR).",
                "• Wake-Word continu : thread en écoute permanente détectant 'Capri', avec filtre de bruit dynamique et seuils d'énergie adaptatifs.",
                "• Push-To-Talk (F8) : écoute sécurisée via détection asynchrone des touches Windows (GetAsyncKeyState).",
                "• Verrou vocal thread-safe : exclusion mutuelle évitant les collisions de micro entre l'écoute de veille et la dictée."
            ]),
            ("⚡ 2. COMMUNICATION INTER-PROCESSUS (HUD C#)", [
                "• Socket TCP Local (Port 45789) : Capri (Python) communique en boucle locale avec le HUD WPF (C#).",
                "• Payload JSON temps réel : transmet le texte à taper, l'état (speaking, idle, ennuie, eteint) et la durée d'affichage.",
                "• Cycle de vie synchronisé : le script Python démarre et termine automatiquement le sous-processus CapriDesktop."
            ]),
            ("👁️ 3. VISION & AUTOMATISATION (PYAUTOGUI)", [
                "• Détection d'images (OpenCV + PyScreeze) : reconnaissance de motifs pour repérer le badge VPN, le bouton Power et l'appel Discord.",
                "• Gestion d'exceptions sécurisée : filtrage de ImageNotFoundException pour empêcher tout crash en cas d'élément introuvable.",
                "• Contrôle d'onglets Opera : automatisation des raccourcis natifs (Ctrl+T, Ctrl+W, Ctrl+V, Entrée)."
            ]),
            ("🖥️ 4. GESTION DES FENÊTRES WINDOWS (USER32)", [
                "• User32.dll / Kernel32.dll : inspection des fenêtres actives via EnumWindows et QueryFullProcessImageNameW.",
                "• Répulsion de focus (AttachThreadInput) : restauration et focus forcé des fenêtres cibles.",
                "• Ancrage d'écran (MoveWindow / SW_MAXIMIZE) : réorganisation millimétrée des fenêtres (gauche, droite, centre)."
            ]),
            ("🎨 5. INTERFACE & ANIMATION", [
                "• HUD C# WPF : rendu vectoriel cyberpunk avec bordure adaptative (ratio 1:1, 16:9), scanlines holographiques et effet machine à écrire.",
                "• Moteur de sprite Python (Tkinter Canvas) : animation de particules et cycle d'humeur en direct."
            ])
        ]

        for sec_title, bullets in sections:
            lbl_sec = tk.Label(scroll_frame, text=sec_title, bg=BG_CARD, fg=PINK, font=("Consolas", 9, "bold"))
            lbl_sec.pack(anchor="w", padx=6, pady=(10, 3))

            box = tk.Frame(scroll_frame, bg=BG_INPUT, highlightbackground=BORDER_COLOR, highlightthickness=1)
            box.pack(fill="x", padx=6, pady=2)
            for bullet in bullets:
                self._wrap_label(tk.Label(box, text=bullet, bg=BG_INPUT, fg="#cbd5e1", font=("Consolas", 8), wraplength=360, justify="left", anchor="w")).pack(anchor="w", fill="x", padx=8, pady=2)

    def _build_sys_tab(self, parent):
        srv_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        srv_card.pack(fill="x", pady=5)
        top_row = tk.Frame(srv_card, bg=BG_CARD)
        top_row.pack(fill="x", padx=12, pady=8)
        self.srv_status_lbl = tk.Label(top_row, text="● VÉRIFICATION...", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold"))
        self.srv_status_lbl.pack(side="left")
        tk.Button(top_row, text="■ Arrêter", command=self.stop_server_from_panel, bg=BG_INPUT, fg=PINK, relief="flat", font=("Consolas", 8), bd=0, padx=8, pady=3).pack(side="right", padx=(4, 0))
        tk.Button(top_row, text="▶ Démarrer", command=self.launch_server_background, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8), bd=0, padx=8, pady=3).pack(side="right")
        self.srv_auto_var = tk.BooleanVar(value=bool(self.config.get("serveur_auto", False)))
        tk.Checkbutton(srv_card, text="Démarrer le serveur à distance avec Capri", variable=self.srv_auto_var, command=self.toggle_server_auto,
                       bg=BG_CARD, fg=TEXT_DIM, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground=CYAN,
                       font=("Consolas", 8), bd=0, highlightthickness=0).pack(anchor="w", padx=10, pady=(0, 8))
        self.update_server_status_badge()

        mic_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        mic_card.pack(fill="x", pady=5)
        hdr_mic = tk.Frame(mic_card, bg=BG_CARD)
        hdr_mic.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(hdr_mic, text="PÉRIPHÉRIQUE D'ENTRÉE (MICRO)", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(side="left")
        tk.Button(hdr_mic, text="⟳ Actualiser", command=self.populate_microphones, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8), bd=0, padx=6, pady=2).pack(side="right")

        self.mic_var = tk.StringVar()
        self.mic_dropdown = ttk.Combobox(mic_card, textvariable=self.mic_var, state="readonly", font=("Consolas", 9))
        self.mic_dropdown.pack(fill="x", padx=12, pady=(2, 10))
        self.mic_dropdown.bind("<<ComboboxSelected>>", self.on_microphone_selected)
        self.mic_mapping = {}
        self.populate_microphones()

        hud_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        hud_card.pack(fill="x", pady=5)
        tk.Label(hud_card, text="MONITEUR HARDWARE LIVE", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.hud_canvas = tk.Canvas(hud_card, bg=BG_CARD, height=90, highlightthickness=0)
        self.hud_canvas.pack(fill="x", padx=12, pady=(0, 8))
        self.update_hardware_hud()

        tk.Button(parent, text="📂  DÉPLOYER LE HUD DES APPLIS OUVERTES", command=self.open_apps_hud, bg=VIOLET, fg="white", relief="flat", font=("Consolas", 9, "bold"), bd=0, pady=7).pack(fill="x", pady=5)

        vol_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        vol_card.pack(fill="x", pady=5)
        tk.Label(vol_card, text="CONTRÔLEUR AUDIO", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=12, pady=(6, 2))
        vol_box = tk.Frame(vol_card, bg=BG_CARD)
        vol_box.pack(fill="x", padx=10, pady=(0, 8))

        for text, act, icon in (("− BAISSER", "down", "🔉"), ("MUET", "mute", "🔇"), ("+ MONTER", "up", "🔊")):
            tk.Button(vol_box, text=f"{icon} {text}", command=lambda a=act: self.volume(a), bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", padx=3, expand=True, fill="x")

    def populate_microphones(self):
        self.mic_mapping.clear()
        options = ["Par défaut (Système Windows)"]
        self.mic_mapping["Par défaut (Système Windows)"] = None
        if VOCAL_AVAILABLE:
            try:
                for idx, name in enumerate(sr.Microphone.list_microphone_names()):
                    clean_name = f"[{idx}] {name}"
                    options.append(clean_name); self.mic_mapping[clean_name] = idx
            except Exception as e: options.append(f"Erreur détection : {e}")

        self.mic_dropdown["values"] = options
        saved_idx, matched = self.config.get("mic_index"), False
        if saved_idx is not None:
            for label, idx in self.mic_mapping.items():
                if idx == saved_idx: self.mic_var.set(label); matched = True; break
        if not matched: self.mic_var.set("Par défaut (Système Windows)")

    def on_microphone_selected(self, event=None):
        chosen_label = self.mic_var.get()
        idx = self.mic_mapping.get(chosen_label)
        self.config["mic_index"] = idx
        save_json(DATA_CONFIG, self.config)
        self.say(f"Micro configuré : {chosen_label.split(']', 1)[-1].strip()[:20]}" if idx is not None else "Micro par défaut activé !", "happy", hold=3)

    def update_server_status_badge(self):
        alive = self.server_alive_cache
        self.srv_status_lbl.configure(text="● SERVEUR REMOTE CONNECTÉ" if alive else "○ SERVEUR ARRÊTÉ", fg=GREEN_LED if alive else RED_LED)
        if self.win.winfo_exists(): self.win.after(3000, self.update_server_status_badge)

    def update_hardware_hud(self):
        cv = self.hud_canvas
        cv.delete("all")
        cpu, ram, used, total = getattr(self, "current_hardware", (0, 0, 0.0, 0.0))

        cv.create_text(0, 10, text=f"CPU : {cpu}%", anchor="w", fill=CYAN, font=("Consolas", 9, "bold"))
        cv.create_rectangle(0, 26, 340, 36, fill=BG_INPUT, outline="")
        cv.create_rectangle(0, 26, max(4, int(3.4 * min(cpu, 100))), 36, fill=CYAN, outline="")

        cv.create_text(0, 52, text=f"RAM : {ram}% ({used} Go / {total} Go)", anchor="w", fill=PINK, font=("Consolas", 9, "bold"))
        cv.create_rectangle(0, 68, 340, 78, fill=BG_INPUT, outline="")
        cv.create_rectangle(0, 68, max(4, int(3.4 * min(ram, 100))), 78, fill=PINK, outline="")

        if self.win.winfo_exists(): self.win.after(2000, self.update_hardware_hud)

    def _build_games_tab(self, parent):
        info_card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        info_card.pack(fill="both", expand=True, pady=6)
        hdr = tk.Frame(info_card, bg=BG_CARD)
        hdr.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(hdr, text="JEUX ET LOGICIELS", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(side="left")
        tk.Button(hdr, text="＋ Ajouter", command=self.add_game, bg=PINK, fg="white", relief="flat", font=("Consolas", 8, "bold"), bd=0, padx=8, pady=3).pack(side="right")

        self.gcanvas = tk.Canvas(info_card, bg=BG_CARD, highlightthickness=0)
        self.gcanvas.pack(fill="both", expand=True, padx=8, pady=6)
        self.gframe = tk.Frame(self.gcanvas, bg=BG_CARD)
        self.gwin = self.gcanvas.create_window((0, 0), window=self.gframe, anchor="nw")
        self.gframe.bind("<Configure>", lambda e: self.gcanvas.configure(scrollregion=self.gcanvas.bbox("all")))
        self.gcanvas.bind("<Configure>", lambda e: self.gcanvas.itemconfig(self.gwin, width=e.width))
        self.refresh_games()

    def _build_ai_tab(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="x", pady=6)
        tk.Label(card, text="CERVEAU NEURONAL (IA)", bg=BG_CARD, fg=CYAN, font=("Consolas", 10, "bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.ai_var = tk.BooleanVar(value=self.config.get("ai_mode", False))
        tk.Checkbutton(card, text="ACTIVER MODE IA CLOUD", variable=self.ai_var, bg=BG_CARD, fg=PINK, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground="white", font=("Consolas", 9, "bold"), command=self.save_config).pack(anchor="w", padx=14, pady=6)

        def key_field(label, cfg_key):
            tk.Label(card, text=label, bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(0, 2))
            e = tk.Entry(card, bg=BG_INPUT, fg="white", insertbackground=CYAN, relief="flat", font=("Consolas", 10), show="•")
            e.pack(fill="x", padx=14, pady=(0, 10), ipady=5)
            e.insert(0, self.config.get(cfg_key, ""))
            def _save(_=None, e=e, k=cfg_key):
                self.config[k] = e.get().strip(); save_json(DATA_CONFIG, self.config)
            e.bind("<FocusOut>", _save)
            e.bind("<Return>", _save)
            return e
        tk.Label(card, text="Capri essaie dans l'ordre : Groq → Mistral → Gemini", bg=BG_CARD, fg=CYAN,
                 font=("Consolas", 8)).pack(anchor="w", padx=14, pady=(6, 8))
        self.groq_entry = key_field("CLÉ API GROQ (gratuite, très rapide) :", "groq_key")
        self.mistral_entry = key_field("CLÉ API MISTRAL (gratuite) :", "mistral_key")

        tk.Label(card, text="CLÉ API GEMINI :", bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(0, 2))
        self.api_entry = tk.Entry(card, bg=BG_INPUT, fg="white", insertbackground=CYAN, relief="flat", font=("Consolas", 10))
        self.api_entry.pack(fill="x", padx=14, pady=(0, 14), ipady=5)
        self.api_entry.insert(0, self.config.get("api_key", ""))
        self.api_entry.bind("<FocusOut>", lambda e: self.save_api_key())

        tk.Label(card, text="CLÉ API ASKNEWS (actualités) :", bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(0, 2))
        self.news_entry = tk.Entry(card, bg=BG_INPUT, fg="white", insertbackground=CYAN, relief="flat", font=("Consolas", 10), show="•")
        self.news_entry.pack(fill="x", padx=14, pady=(0, 14), ipady=5)
        self.news_entry.insert(0, self.config.get("asknews_key", ""))
        self.news_entry.bind("<FocusOut>", lambda e: self.save_news_key())

    def _build_cmd_tab(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=6)
        tk.Label(card, text="RÉPONSES PERSONNALISÉES", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        self.cmd_list = tk.Listbox(card, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 9), bd=0, highlightthickness=0)
        self.cmd_list.pack(fill="both", expand=True, padx=12, pady=6)

        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.pack(fill="x", padx=12, pady=10)
        tk.Button(btn_row, text="＋ Créer Déclencheur", command=self.add_custom_cmd, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(btn_row, text="✕ Supprimer", command=self.del_custom_cmd, bg=BG_INPUT, fg=PINK, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", expand=True, fill="x", padx=2)
        self.update_cmd_list()

    # ------------------------------------------
    # ONGLET CONTACTS (alias vocaux -> pseudo Discord)
    # ------------------------------------------
    def _build_contacts_tab(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER_COLOR, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=6)
        tk.Label(card, text="CONTACTS DISCORD", bg=BG_CARD, fg=CYAN, font=("Consolas", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(card, text="Quand tu dis un des noms, Capri cherche le pseudo Discord.\nEx. : lucas, lukas, lulu, luca  →  gougouz",
                 bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8), justify="left").pack(anchor="w", padx=12, pady=(0, 4))
        self.contacts_list = tk.Listbox(card, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 9), bd=0, highlightthickness=0, activestyle="none")
        self.contacts_list.pack(fill="both", expand=True, padx=12, pady=6)
        self.contacts_list.bind("<Double-Button-1>", lambda e: self.edit_contact())

        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.pack(fill="x", padx=12, pady=10)
        tk.Button(btn_row, text="＋ Ajouter", command=self.add_contact, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(btn_row, text="✎ Modifier", command=self.edit_contact, bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(btn_row, text="✕ Supprimer", command=self.del_contact, bg=BG_INPUT, fg=PINK, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=5).pack(side="left", expand=True, fill="x", padx=2)
        self.update_contacts_list()

    def update_contacts_list(self):
        if not hasattr(self, "contacts_list"): return
        self.contacts_list.delete(0, "end")
        for c in self.contacts:
            alias = ", ".join(c.get("alias", [])) or "(aucun alias)"
            self.contacts_list.insert("end", f"{c['pseudo']}  ←  {alias}")

    def _save_contacts(self):
        save_json(DATA_CONTACTS, self.contacts)
        rebuild_aliases(self.contacts)
        self.update_contacts_list()

    def _ask_contact(self, pseudo="", alias=None):
        pseudo = simpledialog.askstring("Contact", "Pseudo Discord exact (ex. gougouz) :", parent=self.win, initialvalue=pseudo)
        if not (pseudo and pseudo.strip()): return None
        texte = simpledialog.askstring("Alias", "Noms que tu diras, séparés par des virgules\n(ex. lucas, lukas, lulu, luca) :",
                                       parent=self.win, initialvalue=", ".join(alias or []))
        if texte is None: return None
        mots = [m.strip() for m in texte.split(",") if m.strip()]
        return {"pseudo": pseudo.strip(), "alias": list(dict.fromkeys(mots))}

    def add_contact(self):
        if (c := self._ask_contact()):
            self.contacts = [x for x in self.contacts if norm(x["pseudo"]) != norm(c["pseudo"])] + [c]
            self._save_contacts()

    def edit_contact(self):
        if not (sel := self.contacts_list.curselection()): return
        old = self.contacts[sel[0]]
        if (c := self._ask_contact(old["pseudo"], old.get("alias", []))):
            self.contacts[sel[0]] = c
            self._save_contacts()

    def del_contact(self):
        if not (sel := self.contacts_list.curselection()): return
        del self.contacts[sel[0]]
        self._save_contacts()

    def save_api_key(self): self.config["api_key"] = self.api_entry.get().strip(); save_json(DATA_CONFIG, self.config)
    def save_config(self): self.config["ai_mode"] = self.ai_var.get(); save_json(DATA_CONFIG, self.config)
    def save_news_key(self): self.config["asknews_key"] = self.news_entry.get().strip(); save_json(DATA_CONFIG, self.config)

    def add_game(self):
        if not (path := filedialog.askopenfilename(parent=self.win)): return
        if not (name := simpledialog.askstring("Nom", "Nom du jeu ou application ?", parent=self.win, initialvalue=Path(path).stem)): return
        self.games.append({"name": name, "path": path})
        save_json(DATA_GAMES, self.games); self.refresh_games()

    def remove_game(self, g):
        self.games = [x for x in self.games if x is not g]
        save_json(DATA_GAMES, self.games); self.refresh_games()

    def refresh_games(self):
        for wd in self.gframe.winfo_children(): wd.destroy()
        self.gframe.columnconfigure((0, 1), weight=1, uniform="g")
        for i, g in enumerate(self.games):
            b = tk.Button(self.gframe, text=g["name"][:16], command=lambda g=g: self.launch_game(g), bg=BG_INPUT, fg=CYAN, relief="flat", font=("Consolas", 8, "bold"), bd=0, pady=6)
            b.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
            b.bind("<Button-3>", lambda e, g=g: self.remove_game(g))

    def launch_game(self, g):
        self.wake()
        try: start_program(g["path"]); self.say(f"Lancement de {g['name']} !", "excited")
        except Exception as e: self.say(f"Erreur : {e}", "surprised")

    def add_custom_cmd(self):
        if not (trigger := simpledialog.askstring("Trigger", "Mot déclencheur ?", parent=self.win)): return
        if not (response := simpledialog.askstring("Réponse", "Réponse de Capri ?", parent=self.win)): return
        self.config.setdefault("custom_cmds", {})[norm(trigger)] = response
        save_json(DATA_CONFIG, self.config); self.update_cmd_list()

    def del_custom_cmd(self):
        if not (sel := self.cmd_list.curselection()): return
        del self.config["custom_cmds"][self.cmd_list.get(sel[0]).split(" : ")[0]]
        save_json(DATA_CONFIG, self.config); self.update_cmd_list()

    def update_cmd_list(self):
        self.cmd_list.delete(0, tk.END)
        for t, r in self.config.get("custom_cmds", {}).items(): self.cmd_list.insert(tk.END, f"{t} : {r}")

    def volume(self, action):
        self.wake()
        if change_volume(action):
            self.say({"up": "Son monté !", "down": "Son baissé.", "mute": "Silence absolu !"}.get(action, "Audio modifié !"), "happy", hold=3)

    def submit(self, _=None):
        if not (text := fix_names(self.entry.get().strip())): return
        self.entry.delete(0, "end")
        self.toggle_entry(False)
        self.process_command(text)

    # ==========================================
    # LANCEUR DE COMMANDES SÉCURISÉ (ANTI-SPAM)
    # ==========================================
    def process_command(self, text, confirmed=False):
        self.wake()
        self.last_command_time = time.time()
        self.bored_triggered = False

        if not self.exec_lock.acquire(blocking=False):
            self.say("Attends une seconde, je suis déjà occupée !", "surprised", hold=2)
            return False

        self.is_executing = True

        def _worker():
            handled = False
            try: handled = bool(self._process_command_logic(text, confirmed))
            except Exception as e: handle_crash(type(e), e, e.__traceback__)
            finally:
                self.is_executing = False
                self.exec_lock.release()
            if not handled:
                self.clear_say()

        try:
            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            self.is_executing = False
            self.exec_lock.release()
            return False
        return True

    def _process_command_logic(self, text, confirmed=False):
        """Retourne True si la commande a été comprise et exécutée, False sinon."""
        cleaned = norm(text)
        for prefix in ["capri ", "dis capri ", "hey capri ", "ok capri "]:
            if cleaned.startswith(prefix): cleaned = cleaned[len(prefix):].strip()

        # Nettoyage des tirets pour gérer "arrête-toi", "arrête toi", "éteint-toi", etc.
        cmd_clean = cleaned.replace("-", " ")

        # 0. Un message Discord est attendu : ce qui suit EST le message
        #    (avant, « appelle-moi ce soir » lançait un appel au lieu d'être envoyé).
        if self.pending_discord_action:
            if time.time() - self.pending_since <= 60:
                friend_name, discord_hwnd = self.pending_discord_action
                self.pending_discord_action = None
                if cmd_clean in ["annule", "annuler", "laisse tomber", "rien", "oublie"]:
                    self.say("Message annulé.", "happy", hold=2)
                    return True
                self.send_discord_message(friend_name, discord_hwnd, text)
                return True
            self.pending_discord_action = None

        # 1. PRIORITÉ ABSOLUE : Appels, Mute, Quitter vocal
        if self.handle_discord_voice_commands(cleaned):
            return True

        # 2. Arrêt du programme (fermeture de Capri ET du HUD C#)
        #    Seules les phrases qui visent clairement Capri l'éteignent
        #    (« arrête le VPN » ou « éteins la musique » ne l'éteignent plus).
        is_shutdown = (
            any(re.search(rf"\b{p}\b", cmd_clean) for p in [
                "arrete toi", "eteins toi", "eteint toi", "ferme toi", "desactive toi", "mode off"
            ])
            or cmd_clean in ["quitte", "quitter", "stop", "bye", "au revoir", "eteins", "eteint", "arrete",
                             "arrete capri", "eteins capri", "ferme capri", "quitte capri"]
        ) and "vpn" not in cmd_clean

        if is_shutdown:
            self.say("Déconnexion... À plus !", "eteint", 2)
            time.sleep(1.8)
            self.kill_csharp_hud()
            try:
                self.ui(self.root.destroy)
            except Exception:
                pass
            time.sleep(0.2)
            os._exit(0)
            return True

        # 3. Activation / Désactivation du VPN
        if "vpn" in cmd_clean and any(v in cmd_clean for v in ["active", "activer", "lance", "lancer", "mets", "met", "allume", "connecte", "coupe", "desactive", "arrete", "eteins"]):
            self.toggle_opera_vpn()
            return True
        elif cmd_clean in ["active vpn", "lance vpn", "mets vpn", "vpn on", "vpn"]:
            self.toggle_opera_vpn()
            return True

        # 4. Fermeture de l'onglet actif (Ctrl + W)
        if any(w in cleaned for w in ["ferme l onglet", "fermer l onglet", "ferme cet onglet", "ferme onglet", "fermer onglet", "fermer cet onglet"]):
            if PYAUTOGUI_AVAILABLE:
                if self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
                    force_focus_window(self.last_external_hwnd)
                    time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'w')
                self.say("Onglet fermé !", "happy", hold=2)
                return True
            else:
                self.say("Pyautogui requis pour fermer l'onglet !", "surprised")
                return True

        # 5. Ouverture / Fermeture de la console système de Capri
        if any(w in cleaned for w in ["ouvre la console de commande", "ouvre la console de commandes", "ouvre la console", "affiche la console", "console de commande", "console de commandes", "ouvre le terminal"]):
            self.ui(self.open_panel)
            self.say("Console système déployée !", "excited", hold=3)
            return True

        if any(w in cleaned for w in ["ferme la console", "fermer la console", "masque la console", "cache la console"]):
            self.ui(self.close_panel)
            self.say("Console repliée !", "happy", hold=2)
            return True

        # 6. Clic sur le premier lien / résultat de recherche
        if any(w in cleaned for w in [
            "premier lien", "premiere video", "premier resultat", "premier site", "premiere page",
            "1er lien", "1ere video", "1er resultat", "1er site"
        ]) or (
            any(v in cleaned for v in ["clique", "cliquer", "ouvre", "ouvrir", "lance", "lancer", "mets", "met", "va"])
            and any(f in cleaned for f in ["premier", "premiere", "1er", "1ere"])
            and not any(msg_w in cleaned for msg_w in ["message", "msg", "ami", "contact", "appel"])
        ):
            self.click_first_search_link()
            return True

        is_question_about_person = bool(re.search(r"\bcomment\s+va\b", cleaned))

        if not is_question_about_person:
            intent, target_contact, msg_body = extract_message_intent(text)
            if intent == "SEND": self.send_direct_discord_message(target_contact, msg_body); return True
            elif intent == "INIT": self.prepare_discord_discussion(target_contact); return True

        if is_question_about_person:
            person = re.sub(r".*?\bcomment\s+va\s+", "", cleaned).strip(" ?.")
            self.say(f"Je ne sais pas comment va {resolve_contact(person)}, demande-lui !", "curious", hold=3)
            return True

        if re.search(r"\bcomment\s+(?:est\s+ce\s+que\s+)?ca\s+va\b", cleaned) or cleaned in ["ca va", "comment vas tu"]:
            self.say("Systèmes à 100%, ventilateurs au calme ! Et toi ?", "excited", hold=3)
            return True

        # 6 bis. Actualités (AskNews) : « les news », « actus sur la F1 », « quoi de neuf sur Nvidia »
        m_news = re.search(
            r"^(?:donne moi |dis moi |c est quoi |quelles sont |montre moi )?(?:les |des |la |l )?"
            r"(?:news|actus?|actualites?|infos|nouvelles|dernieres nouvelles)"
            r"(?:\s+(?:sur|de|du|des|d|a propos de|concernant|pour)\s+(.+))?\s*\??$", cleaned
        ) or re.search(r"^quoi de neuf(?:\s+(?:sur|dans|chez|avec|en)\s+(.+))?\s*\??$", cleaned)
        if m_news:
            topic = (m_news.group(1) or "").strip(" ?.")
            if topic in ["jour", "moment", "aujourd hui", "la journee", "ajd"]: topic = ""
            self.tell_news(topic)
            return True

        # 7. Recherches Web ("cherche sur google/opera/youtube <recherche>")
        m_search = re.search(
            r"^(?:recherche|cherche|trouve|fais une recherche)\s+(?:sur|dans)\s+(google|opera|opera gx|internet|le net|le web|youtube)\s*(?::|,)?\s+(.+)$",
            cleaned
        )
        if not m_search:
            m_search = re.search(
                r"^(?:recherche|cherche|trouve|fais une recherche)\s+(.+?)\s+(?:sur|dans)\s+(google|opera|opera gx|internet|le net|le web|youtube)$",
                cleaned
            )
            if m_search:
                query, engine = m_search.group(1).strip(), m_search.group(2).lower()
            else:
                query, engine = None, None
        else:
            engine, query = m_search.group(1).lower(), m_search.group(2).strip()

        if query:
            clean_search = query.strip(":,.?!- ")
            if clean_search:
                if "youtube" in engine:
                    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_search)}"
                else:
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_search)}"
                self.open_in_opera_tab(search_url, label=clean_search)
                return True

        closing = bool(re.match(r"^(?:ferme|fermer|quitte|quitter|tue)\b", cleaned))
        position_words = ["gauche", "droite", "milieu", "centre", "ecran", "deplace", "cale", "place"]
        if (not closing and "youtube" in cleaned.split()
                and any(v in cleaned.split() for v in ["ouvre", "ouvrir", "lance", "lancer", "mets", "met", "va"])
                and not any(w in cleaned for w in position_words)):
            self.open_in_opera_tab("youtube"); return True
        if any(w in cleaned for w in ["ouvre un onglet", "nouvel onglet", "ouvre onglet"]):
            self.open_in_opera_tab("google"); return True

        for site_key in KNOWN_SITES:
            if re.search(rf"\b{re.escape(site_key)}\b", cleaned) and any(v in cleaned for v in ["ouvre", "lance", "onglet", "mets"]) and not closing:
                self.open_in_opera_tab(site_key); return True

        if any(w in cleaned for w in ["met en pause", "mets en pause", "pause la musique", "reprends la musique"]) or "play" in cleaned.split():
            change_volume("playpause"); self.say("Lecture / Pause basculée !", "happy", hold=2); return True
        if any(w in cleaned for w in ["musique suivante", "chanson suivante", "morceau suivant"]):
            change_volume("next"); self.say("Piste suivante !", "happy", hold=2); return True
        if any(w in cleaned for w in ["musique precedente", "chanson precedente", "morceau precedent"]):
            change_volume("prev"); self.say("Piste précédente !", "happy", hold=2); return True

        if any(w in cleaned for w in ["capture d ecran", "screenshot", "imprime ecran"]):
            if not PYAUTOGUI_AVAILABLE: self.say("Installe pyautogui ('pip install pyautogui') !", "surprised"); return True
            pyautogui.hotkey('win', 'shift', 's'); self.say("Capture d'écran ouverte !", "happy", hold=2); return True
        if any(w in cleaned for w in ["minimise tout", "affiche le bureau", "reduis tout"]):
            if not PYAUTOGUI_AVAILABLE: self.say("Installe pyautogui ('pip install pyautogui') !", "surprised"); return True
            pyautogui.hotkey('win', 'd'); self.say("Bureau affiché !", "happy", hold=2); return True
        if any(w in cleaned for w in ["pile ou face", "lance une piece"]):
            self.say(f"Résultat : {random.choice(['Pile !', 'Face !'])}", "excited", hold=3); return True
        if any(w in cleaned for w in ["lance un de", "fais un de"]):
            self.say(f"Le dé indique : {random.randint(1, 6)} 🎲", "excited", hold=3); return True

        sub_commands = [c.strip() for c in re.sub(r"\b(puis|ensuite|et apres|apres|et)\b", "|", cleaned).replace(",", "|").replace(";", "|").split("|") if len(c.strip()) > 2]
        if len(sub_commands) > 1:
            # Avant, une question à l'IA contenant « et », « puis » ou une virgule
            # était découpée en sous-commandes et n'arrivait jamais à l'IA.
            if self.run_chained_commands(sub_commands): return True
            return self.ask_ai(text) if self.config.get("ai_mode") else False

        _, understood = self.execute_single_sub_command(cleaned, context_app=None, standalone=True)
        if not understood and self.config.get("ai_mode"):
            return self.ask_ai(text)
        return understood

    # ==========================================
    # ACTUALITÉS (ASKNEWS)
    # ==========================================
    def tell_news(self, topic=""):
        if not ASKNEWS_AVAILABLE:
            self.say("Installe le module actus : pip install asknews", "surprised", hold=4); return
        key = (self.config.get("asknews_key") or os.environ.get("ASKNEWS_API_KEY") or "").strip()
        if not key:
            self.say("Ajoute ta clé AskNews dans la console (onglet IA) !", "surprised", hold=4); return
        query = topic or "actualité en France aujourd'hui"
        self.say(f"Je scanne les news{' sur ' + topic if topic else ''}…", "curious", hold=10)
        try:
            ask = AskNewsSDK(api_key=key, scopes=["news"])
            resp = ask.news.search_news(query=query, n_articles=5, method="nl")
            articles = list(getattr(resp, "as_dicts", None) or [])
            context = getattr(resp, "as_string", "") or ""
        except Exception as e:
            self.say(f"Erreur AskNews : {str(e)[:120]}", "surprised", hold=5); return
        if not articles and not context.strip():
            self.say("Rien trouvé dans les news là-dessus.", "bored", hold=4); return

        # Résumé par l'IA si une clé est configurée, sinon les titres
        if self.ai_providers():
            try:
                prompt = ("Tu es Capri, l'assistante cyberpunk de l'utilisateur. Résume en français, en 2 phrases courtes, "
                          f"les infos les plus importantes{' sur ' + topic if topic else ''} dans ces articles. "
                          "Pas de liste, pas de liens.\n\n" + context[:12000])
                r = self.llm(prompt)
                text = (getattr(r, "text", "") or "").strip()
                if text:
                    self.say("📰 " + text[:420], "excited", hold=max(6, min(18, len(text) * 0.06))); return
            except Exception:
                pass
        titles = []
        for a in articles[:3]:
            t = getattr(a, "eng_title", None) or getattr(a, "title", None) or (a.get("title") if isinstance(a, dict) else None)
            if t: titles.append(str(t))
        msg = " | ".join(titles) if titles else context.strip().split("\n")[0][:300]
        self.say("📰 " + msg[:420], "excited", hold=12)

    # ==========================================
    # MODE IA (GEMINI)
    # ==========================================
    def _gemini_generate(self, key, prompt, deadline=None):
        """Appelle directement l'API Gemini d'AI Studio (sans passer par le SDK, qui envoie
        les nouvelles clés « AQ. » vers Vertex AI). Choisit un autre modèle si besoin."""
        import urllib.request, urllib.error
        base = "https://generativelanguage.googleapis.com/v1beta"

        deadline = deadline or (time.time() + 30)

        def call(url, payload=None, timeout=20):
            left = deadline - time.time()
            if left < 1.5:
                raise RuntimeError("TIMEOUT Gemini met trop de temps à répondre")
            timeout = min(timeout, left)
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                         headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                try: msg = json.loads(body)["error"]["message"]
                except Exception: msg = body[:200]
                raise RuntimeError(f"{e.code} {msg}") from None
            except (TimeoutError, socket.timeout, urllib.error.URLError, OSError) as e:
                # pas de réponse à temps : traité comme une surcharge (on change de modèle)
                raise RuntimeError(f"504 Pas de réponse de Gemini ({e})") from None

        def generate(model):
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 400}}
            # Réponses courtes : on coupe la « réflexion » des modèles qui le permettent (bien plus rapide)
            if "2.5" in model:
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
            elif "flash" in model:
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
            try:
                res = call(f"{base}/models/{model}:generateContent", body)
            except RuntimeError as e:
                if not str(e).startswith("400") or "thinking" not in str(e).lower():
                    raise
                body["generationConfig"].pop("thinkingConfig", None)   # option refusée par ce modèle
                res = call(f"{base}/models/{model}:generateContent", body)
            parts = (res.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            return type("Rep", (), {"text": "".join(p.get("text", "") for p in parts)})()

        busy = ("503", "500", "429", "504")   # surcharge / quota / délai : temporaire
        model = self.config.get("ai_model") or "gemini-flash-latest"
        for attempt in range(2):
            try:
                return generate(model)
            except RuntimeError as e:
                code = str(e)[:3]
                if str(e).startswith("TIMEOUT"):
                    raise
                if code in busy and code != "504" and attempt == 0:
                    time.sleep(1.5); continue          # on réessaie une fois (sauf si ça a déjà trop traîné)
                if code not in busy and code != "404":
                    raise
                break
        # Modèle surchargé ou indisponible : on essaie les autres modèles du compte
        bad = ("image", "tts", "audio", "live", "embedding", "vision", "thinking", "exp", "preview")
        names = [m["name"].split("/")[-1] for m in call(f"{base}/models?pageSize=200", timeout=10).get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in names if "gemini" in n and "flash" in n and not any(b in n for b in bad)]
        candidates = flash or [n for n in names if "gemini" in n]
        def version(n):
            nums = re.findall(r"\d+(?:\.\d+)?", n)
            return float(nums[0]) if nums else 0.0
        # les « lite » en dernier recours (plus légers, souvent moins chargés)
        candidates.sort(key=lambda n: ("lite" not in n, "latest" in n, version(n)), reverse=True)
        candidates = [n for n in candidates if n != model]
        last = RuntimeError("Gemini est surchargé en ce moment, réessaie dans un instant !")
        for name in candidates[:6]:
            if deadline - time.time() < 3:
                raise RuntimeError("TIMEOUT Gemini est trop lent ou surchargé")
            try:
                rep = generate(name)
                if "lite" not in name:            # on retient un bon modèle, pas un repli « lite »
                    self.config["ai_model"] = name
                    save_json(DATA_CONFIG, self.config)
                return rep
            except RuntimeError as e:
                if str(e)[:3] not in busy and not str(e).startswith("404"):
                    last = e
        raise last

    def _openai_compatible(self, url, key, models, prompt, deadline=None, cfg_key=None):
        """Groq et Mistral utilisent le même format d'API (compatible OpenAI).
        Si les modèles prévus n'existent plus (Groq en retire souvent), on demande la liste
        des modèles actifs du compte et on retient celui qui marche dans config (cfg_key)."""
        import urllib.request, urllib.error
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "Capri/1.0"}
        deadline = deadline or (time.time() + 30)
        last, tried, gone = None, set(), 0

        def attempt(model):
            nonlocal last, gone
            left = deadline - time.time()
            if left < 1.5:
                raise last or RuntimeError("TIMEOUT pas de réponse à temps")
            body = {"model": model, "max_tokens": 1000, "temperature": 0.8,
                    "messages": [{"role": "user", "content": prompt}]}
            if "gpt-oss" in model:
                body["reasoning_effort"] = "low"     # modèle « raisonneur » : réflexion courte
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=min(20, left)) as r:
                    res = json.loads(r.read().decode("utf-8"))
                text = res["choices"][0]["message"].get("content") or ""
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # modèles « raisonneurs »
                if text: return type("Rep", (), {"text": text})()
                last = RuntimeError(f"{model} : réponse vide")
            except urllib.error.HTTPError as e:
                body_txt = e.read().decode("utf-8", "replace")
                last = RuntimeError(f"{e.code} {body_txt[:160]}")
                if e.code in (401, 403):
                    raise last                     # clé invalide : inutile d'essayer d'autres modèles
                if e.code in (400, 404) and ("model" in body_txt.lower()):
                    gone += 1                      # modèle retiré ou inconnu
            except Exception as e:
                last = RuntimeError(f"504 {e}")
            return None

        for model in models:
            if model in tried: continue
            tried.add(model)
            if (rep := attempt(model)): return rep

        # Modèles prévus introuvables : on prend ceux que le compte propose vraiment
        if gone:
            try:
                req = urllib.request.Request(url.rsplit("/chat/", 1)[0] + "/models", headers=headers)
                with urllib.request.urlopen(req, timeout=max(1, min(8, deadline - time.time()))) as r:
                    data = json.loads(r.read().decode("utf-8")).get("data", [])
                bad = ("whisper", "tts", "guard", "embed", "audio", "vision", "ocr", "moderation", "compound", "orpheus", "prompt")
                names = [m.get("id", "") for m in data if m.get("active", True)]
                names = [n for n in names if n and not any(b in n.lower() for b in bad) and n not in tried]
                # préférence : gpt-oss (production chez Groq), puis les « small » / « instant », puis le reste
                names.sort(key=lambda n: (("gpt-oss" not in n), ("small" not in n and "instant" not in n), n))
                for model in names[:4]:
                    tried.add(model)
                    if (rep := attempt(model)):
                        if cfg_key:
                            self.config[cfg_key] = model
                            save_json(DATA_CONFIG, self.config)
                        return rep
            except Exception as e:
                if not str(e).startswith("TIMEOUT"):
                    last = last or RuntimeError(f"504 {e}")
                else:
                    last = e
        raise last or RuntimeError("Aucun modèle disponible")

    def ai_providers(self):
        """Fournisseurs configurés, du plus rapide au plus lent."""
        cfg, env = self.config, os.environ
        out = []
        if (k := (cfg.get("groq_key") or env.get("GROQ_API_KEY") or "").strip()):
            out.append(("Groq", lambda p, d, k=k: self._openai_compatible(
                "https://api.groq.com/openai/v1/chat/completions", k,
                [cfg.get("groq_model") or "openai/gpt-oss-120b", "openai/gpt-oss-20b"], p, d, "groq_model")))
        if (k := (cfg.get("mistral_key") or env.get("MISTRAL_API_KEY") or "").strip()):
            out.append(("Mistral", lambda p, d, k=k: self._openai_compatible(
                "https://api.mistral.ai/v1/chat/completions", k,
                [cfg.get("mistral_model") or "mistral-small-latest", "open-mistral-nemo"], p, d, "mistral_model")))
        if (k := (cfg.get("api_key") or env.get("GEMINI_API_KEY") or "").strip()):
            out.append(("Gemini", lambda p, d, k=k: self._gemini_generate(k, p, d)))
        return out

    def llm(self, prompt):
        """Essaie chaque IA configurée jusqu'à obtenir une réponse."""
        providers = self.ai_providers()
        if not providers:
            raise RuntimeError("NOKEY")
        # Délai total de 35 s : avant, Gemini pouvait essayer jusqu'à 6 modèles de secours,
        # 20 s chacun, et Capri restait bloquée sur « Je réfléchis… » pendant des minutes.
        deadline = time.time() + 35
        errors = []
        for i, (name, fn) in enumerate(providers):
            left = deadline - time.time()
            if left < 2:
                errors.append(f"{name}: pas eu le temps"); continue
            # chaque IA a sa part du temps restant, la dernière prend tout ce qui reste
            share = left if i == len(providers) - 1 else max(8, left / (len(providers) - i))
            try:
                rep = fn(prompt, time.time() + share)
                if (getattr(rep, "text", "") or "").strip():
                    return rep
                errors.append(f"{name}: réponse vide")
            except Exception as e:
                errors.append(f"{name}: {str(e)[:80]}")
        log_ia_error(" | ".join(errors))
        raise RuntimeError(" | ".join(errors))

    def ask_ai(self, question):
        """Répond avec l'IA (Groq, Mistral ou Gemini) quand aucune commande locale ne correspond."""
        if not self.ai_providers():
            self.say("Ajoute une clé IA (Groq, Mistral ou Gemini) dans la console, onglet IA !", "surprised", hold=5); return True
        self.say("Je réfléchis…", "curious", hold=10)
        try:
            prompt = (
                "Tu es Capri, l'assistante de bureau de l'utilisateur : une petite IA cyberpunk, enjouée et complice. "
                "Réponds en français, en 2 phrases maximum (ta réponse s'affiche dans une petite bulle). "
                "Tu ne peux pas agir sur le PC dans cette réponse : réponds seulement.\n\n"
                f"Utilisateur : {question}"
            )
            resp = self.llm(prompt)
            answer = (getattr(resp, "text", "") or "").strip()
            if not answer:
                self.say("Mon cerveau neuronal n'a rien renvoyé…", "surprised", hold=3)
            else:
                self.say(answer[:400], "happy", hold=max(4, min(15, len(answer) * 0.06)))
        except Exception as e:
            self.say(f"Erreur IA : {str(e)[:160]}", "surprised", hold=6)
        return True

    def run_chained_commands(self, sub_commands):
        context_app, any_understood = None, False
        for cmd in sub_commands:
            context_app, understood = self.execute_single_sub_command(cmd, context_app=context_app, standalone=False)
            any_understood = any_understood or understood
            time.sleep(0.35)
        if any_understood:
            self.say("Toutes tes fenêtres sont en place !", "excited", hold=3)
        return any_understood

    def parse_position_target(self, cmd, context_app):
        direction = None
        if "gauche" in cmd: direction = "left"
        elif "droite" in cmd: direction = "right"
        # « enlève le grand écran » contient « grand écran » : on teste la sortie du plein écran d'abord
        elif any(p in cmd for p in ["enleve le grand", "enleve le plein", "quitte le grand", "quitte le plein", "sors du grand", "sors du plein", "reduis", "taille normale", "mode fenetre"]): direction = "unfullscreen"
        elif any(p in cmd for p in ["grand ecran", "plein ecran", "maximise", "agrandis"]): direction = "fullscreen"
        elif any(p in cmd for p in ["milieu", "centre"]): direction = "center"
        if not direction: return None, None

        cleaned_cmd = cmd
        for v in ["mets-le", "mets-la", "mets le", "mets la", "met le", "met la", "place-le", "place-la", "place le", "place la", "cale-le", "cale-la", "cale le", "cale la", "deplace-le", "deplace-la", "deplace le", "deplace la", "mets", "met", "place", "cale", "positionne", "glisse", "deplace", "deplacer", "déplace", "déplacer"]:
            cleaned_cmd = re.sub(rf"\b{v}\b", "", cleaned_cmd)

        # verbes de taille (sinon « enlève le grand écran » cherchait une appli nommée « enleve le »)
        for v in ["enleve le", "enleve", "quitte le", "quitte", "sors du", "sors", "reduis", "taille normale", "mode fenetre", "en mode fenetre", "maximise", "agrandis"]:
            cleaned_cmd = re.sub(rf"\b{v}\b", "", cleaned_cmd)

        for d in ["a gauche de mon ecran","a droite de mon ecran", "gauche de mon ecran", "droite de mon ecran", "sur mon ecran", "de mon ecran", "a gauche", "a droite", "au milieu", "au centre", "en grand ecran", "en plein ecran", "grand ecran", "plein ecran", "gauche", "droite", "centre", "milieu"]:
            cleaned_cmd = re.sub(rf"\b{d}\b", "", cleaned_cmd)

        app_target = cleaned_cmd.strip()
        return (context_app or "active_window") if not app_target or app_target in ["le", "la", "l", "les", "ce", "cette", "ça", "ca"] else app_target, direction

    def execute_single_sub_command(self, cmd, context_app=None, standalone=True):
        cmd_norm = norm(cmd)
        cmd_clean = cmd_norm.replace("-", " ")

        if re.search(r"\b(appelle|appeler|call|appel)\b", cmd_norm.replace("-", " ")):
            raw_target = re.sub(r"\b(appelle|appeler|call|appel)\b", "", cmd_norm).strip()
            target = resolve_contact(raw_target)
            self.call_discord_contact(target)
            return "discord", True
        if re.search(r"\bmute\b", cmd_norm) or "coupe mon micro" in cmd_norm:
            self.discord_toggle_mute()
            return "discord", True
        if any(w in cmd_norm for w in ["raccroche", "quitte le vocal"]):
            self.discord_leave_voice()
            return "discord", True

        # VPN dans les commandes enchaînées
        if "vpn" in cmd_clean and any(v in cmd_clean for v in ["active", "activer", "lance", "lancer", "mets", "met", "allume", "connecte", "coupe", "desactive"]):
            self.toggle_opera_vpn()
            return "opera", True

        # Fermer l'onglet dans une chaîne de commandes
        if any(w in cmd_norm for w in ["ferme l onglet", "fermer l onglet", "ferme cet onglet", "ferme onglet"]):
            if PYAUTOGUI_AVAILABLE:
                if self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
                    force_focus_window(self.last_external_hwnd)
                    time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'w')
                if standalone: self.say("Onglet fermé !", "happy", hold=2)
                return context_app, True

        # Ouvrir la console dans une chaîne de commandes
        if any(w in cmd_norm for w in ["ouvre la console", "ouvre le terminal", "affiche la console", "console de commande"]):
            self.ui(self.open_panel)
            if standalone: self.say("Console système déployée !", "excited", hold=3)
            return context_app, True

        # Clic premier lien dans une chaîne de commandes
        if any(w in cmd_norm for w in ["premier lien", "premier resultat", "premiere video", "premier site", "1er lien", "1er resultat"]) or (
            any(v in cmd_norm for v in ["clique", "cliquer", "ouvre", "ouvrir", "lance", "lancer", "mets", "met", "va"])
            and any(f in cmd_norm for f in ["premier", "premiere", "1er", "1ere"])
            and not any(msg_w in cmd_norm for msg_w in ["message", "msg", "ami", "contact", "appel"])
        ):
            self.click_first_search_link()
            return "opera", True

        # Recherche web dans les commandes enchaînées
        m_sub_search = re.search(
            r"^(?:recherche|cherche|trouve)\s+(?:sur|dans)\s+(google|opera|opera gx|internet|le net|youtube)\s*(?::|,)?\s+(.+)$",
            cmd_norm
        ) or re.search(
            r"^(?:recherche|cherche|trouve)\s+(.+?)\s+(?:sur|dans)\s+(google|opera|opera gx|internet|le net|youtube)$",
            cmd_norm
        )
        if m_sub_search:
            g1, g2 = m_sub_search.group(1), m_sub_search.group(2)
            if g1 in ["google", "opera", "opera gx", "internet", "le net", "youtube"]:
                engine, query = g1, g2
            else:
                query, engine = g1, g2
            clean_search = query.strip(":,.?!- ")
            if clean_search:
                search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_search)}" if "youtube" in engine else f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_search)}"
                self.open_in_opera_tab(search_url, label=clean_search)
                return "opera", True

        if ("youtube" in cmd.split() and any(v in cmd.split() for v in ["ouvre", "lance", "onglet", "mets"])
                and not any(w in cmd for w in ["gauche", "droite", "milieu", "centre", "ecran"])):
            self.open_in_opera_tab("youtube"); return "opera", True

        if any(cmd.startswith(p) for p in ["ouvre ", "ouvrir ", "lance ", "lancer ", "demarre "]):
            app_name = cmd.split(maxsplit=1)[1].strip()
            hwnd = self.open_or_focus_app(app_name)
            if hwnd or self.last_launch_ok:
                if standalone: self.say(f"{app_name.capitalize()} prêt !", "excited")
                return app_name, True
            return context_app, False

        if (any(cmd.startswith(p) for p in ["ferme ", "fermer ", "quitte ", "tue "])
                and not any(w in cmd for w in ["grand ecran", "plein ecran", "mode fenetre"])):
            target = cmd.split(maxsplit=1)[1].strip()
            if target in ["le", "la", "l"]: target = context_app or "discord"
            if self.kill_process_by_name(target):
                if standalone: self.say(f"{target.capitalize()} fermé !", "excited")
                return target, True
            return context_app, False

        app_target, direction = self.parse_position_target(cmd, context_app)
        if direction:
            target_hwnd, resolved_name = None, app_target
            if app_target != "active_window" and app_target is not None:
                target_hwnd, resolved_name = find_window_by_name(app_target)
                if not target_hwnd: target_hwnd = self.open_or_focus_app(app_target)
            elif self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
                target_hwnd, resolved_name = self.last_external_hwnd, "Fenêtre"

            if target_hwnd:
                move_window_position(target_hwnd, direction)
                if standalone: self.say(f"{str(resolved_name or 'Fenêtre').capitalize()} déplacé !", "happy")
                return app_target, True

        if standalone:
            words = set(cmd.split())
            vol = words & {"volume", "son"}
            if vol and words & {"monte", "up"}: self.volume("up"); return context_app, True
            elif vol and words & {"baisse", "down"}: self.volume("down"); return context_app, True
            elif vol and words & {"mute", "muet", "coupe", "silence"}: self.volume("mute"); return context_app, True

            if cmd in self.config.get("custom_cmds", {}):
                self.say(self.config["custom_cmds"][cmd], "happy"); return context_app, True

            reply = self.offline_brain_response(cmd, words)
            if reply:
                self.say(reply, "happy"); return context_app, True

        return context_app, False

    def open_or_focus_app(self, app_name):
        self.last_launch_ok = False
        norm_name = norm(app_name)
        if norm_name in ["discorde", "discort", "dis corde"]: app_name = "discord"

        hwnd, _ = find_window_by_name(app_name)
        if hwnd: force_focus_window(hwnd); self.last_launch_ok = True; return hwnd

        if (found_game := find_game(self.games, app_name)):
            try: start_program(found_game["path"]); self.last_launch_ok = True
            except Exception: pass
        elif norm(app_name) in COMMON_APPS:
            self.last_launch_ok = launch_common(COMMON_APPS[norm(app_name)])
        elif can_launch(app_name):
            try: os.system(f'start "" "{app_name}"'); self.last_launch_ok = True
            except Exception: pass
        else:
            return None

        for _ in range(12):
            time.sleep(0.3)
            hwnd, _ = find_window_by_name(app_name)
            if hwnd: force_focus_window(hwnd); return hwnd
        return None

    # ------------------------------------------
    # DISCORD : messages, appels, vocal, mute
    # ------------------------------------------
    def discord_keys(self, name):
        custom = self.config.get("discord_hotkeys", {})
        custom = custom.get(name) if isinstance(custom, dict) else None
        return list(custom) if isinstance(custom, (list, tuple)) and custom else list(DISCORD_HOTKEYS[name])

    def discord_open_dm(self, contact_name):
        """Ctrl+K -> tape/colle le nom -> Entrée."""
        time.sleep(0.35); pyautogui.hotkey('ctrl', 'k'); time.sleep(0.3)
        if contact_name.isascii():
            pyautogui.write(contact_name, interval=0.04)
        else:
            self.set_clipboard_safe(contact_name)
            time.sleep(0.1); pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5); pyautogui.press('enter'); time.sleep(0.4)

    def click_call_button(self):
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI n'est pas installé !", "surprised")
            return False

        image_path = RESSOURCES / "call_btn.png"
        try:
            button = pyautogui.locateOnScreen(str(image_path), confidence=0.8)
            if button:
                pyautogui.click(pyautogui.center(button))
                return True
            self.say("Je ne vois pas le bouton d'appel !", "surprised")
            return False
        except Exception as e:
            self.say(f"Erreur de détection du bouton d'appel : {e}", "surprised")
            return False

    def click_stopcall_button(self):
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI n'est pas installé !", "surprised")
            return False

        image_path = RESSOURCES / "stopcall.png"
        if not image_path.is_file():
            self.say("Image stopcall.png introuvable à côté de capri.py !", "surprised")
            return False

        try:
            button = pyautogui.locateOnScreen(str(image_path), confidence=0.8)
            if button:
                pyautogui.click(pyautogui.center(button))
                return True
            self.say("Je ne trouve pas le bouton pour raccrocher !", "surprised")
            return False
        except Exception as e:
            self.say(f"Erreur de détection du bouton raccrocher : {e}", "surprised")
            return False

    def call_discord_contact(self, contact_raw):
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI n'est pas installé !", "surprised")
            return False

        contact = resolve_contact(contact_raw)
        self.discord_open_dm(contact)
        time.sleep(1.5)

        if self.click_call_button():
            self.say(f"Appel lancé avec {contact} !", "excited", hold=3)
            return True
        return False

    def discord_toggle_mute(self):
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI n'est pas installé !", "surprised")
            return False

        hwnd = find_discord_window()
        if not hwnd:
            self.say("Je ne trouve pas la fenêtre Discord !", "surprised")
            return False

        force_focus_window(hwnd)
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "shift", "m")
        self.discord_muted = not self.discord_muted
        self.say("Micro Discord basculé", "happy", hold=3)
        return True

    def discord_leave_voice(self):
        if not PYAUTOGUI_AVAILABLE:
            self.say("PyAutoGUI n'est pas installé !", "surprised")
            return False

        hwnd = find_discord_window()
        if not hwnd:
            self.say("Je ne trouve pas la fenêtre Discord !", "surprised")
            return False

        force_focus_window(hwnd)
        time.sleep(0.6)

        if self.click_stopcall_button():
            self.say("J'ai raccroché !", "happy", hold=3)
            return True
        return False

    def handle_discord_voice_commands(self, cmd):
        target = extract_call_target(cmd)
        if target:
            self.call_discord_contact(target)
            return True

        action = detect_discord_voice_action(cmd)
        if action == "leave":
            self.discord_leave_voice()
            return True
        if action == "mute":
            self.discord_toggle_mute()
            return True
        return False

    def send_direct_discord_message(self, contact_name, message):
        if not PYAUTOGUI_AVAILABLE: self.say("Installe pyautogui ('pip install pyautogui') !", "surprised"); return
        hwnd = self.open_or_focus_app("discord")
        if not hwnd: self.say("Impossible d'ouvrir Discord !", "surprised"); return

        self.discord_open_dm(contact_name)

        self.set_clipboard_safe(format_discord_purple_message(message))

        time.sleep(0.15); pyautogui.hotkey('ctrl', 'v'); time.sleep(0.15); pyautogui.press('enter')
        self.say(f"Message envoyé à {contact_name} !", "excited", hold=3)

    def prepare_discord_discussion(self, contact_name):
        if not PYAUTOGUI_AVAILABLE: return
        hwnd = self.open_or_focus_app("discord")
        if not hwnd: self.say("Impossible d'ouvrir Discord !", "surprised"); return

        self.discord_open_dm(contact_name)

        self.pending_discord_action = (contact_name, hwnd)
        self.pending_since = time.time()
        self.say(f"Discussion avec {contact_name} ouverte ! Que veux-tu lui envoyer ?", "excited", hold=8)
        self.toggle_entry(True)

        if not VOCAL_AVAILABLE: return

        # Sans ce drapeau, l'écoute « Capri » reprenait le micro pendant la dictée
        # et jetait le message (il ne contient pas le mot « Capri »).
        self.dictating = True

        def listen_sub():
            try:
                time.sleep(1.0)
                r, mic_index = sr.Recognizer(), self.get_selected_mic_index()
                r.dynamic_energy_threshold, r.pause_threshold = True, 1.0
                r.operation_timeout = 10
                with self.vocal_lock:
                    with sr.Microphone(device_index=mic_index) as source:
                        r.adjust_for_ambient_noise(source, duration=0.25)
                        audio = r.listen(source, timeout=5.0, phrase_time_limit=14.0)

                dictated = fix_names(r.recognize_google(audio, language="fr-FR"))
                if self.pending_discord_action:
                    # attend la fin de la commande en cours pour ne pas être refusé (« déjà occupée »)
                    for _ in range(50):
                        if not self.exec_lock.locked(): break
                        time.sleep(0.1)
                    self.process_command(dictated, confirmed=True)
            except Exception: pass
            finally:
                self.dictating = False

        threading.Thread(target=listen_sub, daemon=True).start()

    def send_discord_message(self, friend_name, discord_hwnd, message):
        if not PYAUTOGUI_AVAILABLE: return
        force_focus_window(discord_hwnd)
        time.sleep(0.2)

        self.set_clipboard_safe(format_discord_purple_message(message))

        time.sleep(0.1); pyautogui.hotkey('ctrl', 'v'); time.sleep(0.1); pyautogui.press('enter')
        self.say(f"Message envoyé à {friend_name} !", "happy", hold=4)

    def kill_process_by_name(self, name):
        name_clean, closed = norm(name), False
        if len(name_clean) < 3: return False
        alias = COMMON_APPS.get(name_clean, "")
        if "discord" in alias.lower(): alias = "discord"
        if alias and (" " in alias or "\\" in alias): alias = ""
        needles = {n.replace(" ", "") for n in {name_clean, alias} if n}
        # Le nom du processus doit correspondre (« opera » -> opera.exe), jamais un simple morceau
        # de nom : « ferme win » ne doit pas viser winlogon.exe, etc.
        if PSUTIL_AVAILABLE:
            for p in psutil.process_iter(['name', 'pid']):
                try:
                    if p.info['pid'] == os.getpid(): continue
                    pname = (p.info['name'] or "").lower()
                    base = pname[:-4] if pname.endswith(".exe") else pname
                    if base in PROTECTED_PROCESSES: continue
                    if base in needles or any(base.startswith(n) and len(n) >= 4 for n in needles):
                        p.terminate(); closed = True
                except Exception: pass
        if not closed:
            for n in needles:
                if n in PROTECTED_PROCESSES or not re.fullmatch(r"[a-z0-9_.-]+", n): continue
                if subprocess.run(["taskkill", "/F", "/T", "/IM", f"{n}.exe"], capture_output=True).returncode == 0:
                    closed = True
        return closed

    def offline_brain_response(self, norm_text, words):
        if any(w in words for w in {"salut", "yo", "hello", "bonjour", "coucou"}): return random.choice(["Yo ! Que puis-je faire pour toi ?", "En ligne ! Dis-moi tout.", "Prête !"])
        if any(w in words for w in {"cpu", "ram", "perf", "perfs"}):
            cpu, ram, used, total = getattr(self, "current_hardware", (0, 0, 0.0, 0.0))
            return f"CPU : {cpu}% | RAM : {ram}% ({used} Go / {total} Go)."
        if any(w in words for w in {"heure", "temps"}): return f"Il est {time.strftime('%Hh%M')}."
        return None

    def on_press(self, e): self.dx, self.dy, self.moved = e.x, e.y, False
    def on_drag(self, e): self.moved = True; self.rx, self.ry = e.x_root - self.dx, e.y_root - self.dy; self.root.geometry(f"+{self.rx}+{self.ry}")
    def on_release(self, e):
        if self.moved: return
        if e.x > W - 80 and e.y > CH - 25: return self.toggle_panel()
        self.wake(); self.say(random.choice(["Hé !", "Besoin d'un coup de main ?"]), "surprised", hold=3)

    def pick_pose(self, now):
        pool = IDLE if random.random() < 0.65 else FUN if self.mood == "happy" else MOOD_POSES.get(self.mood, IDLE)
        self.pose = random.choice([p for p in pool if p != self.pose] or pool)
        self.pose_until = now + (random.uniform(8, 15) if self.mood == "happy" else 6)

    def draw(self, t, now):
        cv = self.cv
        cx = W / 2 + (random.randint(-3, 3) if self.glitch > 0 else 0)
        talking = bool(self.text) and self.shown < len(self.text) and now < self.text_until
        bob = 2 * math.sin(t * 2) + (2 * abs(math.sin(t * 14)) if talking else 0)

        for p in self.parts:
            p[1] -= p[2]
            if p[1] < 0: p[0], p[1], p[2] = random.randint(8, W - 8), CH, random.uniform(0.4, 1.4)
            cv.create_rectangle(p[0], p[1], p[0] + 2, p[1] + 2, fill=CYAN if int(p[0]) % 2 == 0 else PINK, outline="")

        cv.create_image(cx, BASE_Y - bob, image=self.sprites[self.pose], anchor="s")

        if self.glitch > 0: cv.create_line(cx - 35, BASE_Y - 70, cx + 35, BASE_Y - 70, fill=PINK, width=2); self.glitch -= 1

        cv.create_rectangle(W - 74, CH - 18, W - 4, CH - 2, fill=BG_PANEL, outline=VIOLET)
        cv.create_text(W - 8, CH - 8, text="[ CONSOLE ]", anchor="se", fill=CYAN, font=("Consolas", 8, "bold"))

        if self.text and now < self.text_until:
            self.shown += 1.4
            t_id = cv.create_text(W / 2, 18, text=self.text[:int(self.shown)], width=W - 30, fill="#e8fbff", font=("Consolas", 9, "bold"), anchor="n")
            if (bbox := cv.bbox(t_id)):
                x1, y1, x2, y2 = bbox
                cv.create_rectangle(x1-8, y1-4, x2+8, y2+4, fill=BG_PANEL, outline=PINK, width=1)
                cv.create_polygon(W/2-4, y2+4, W/2+4, y2+4, W/2, y2+12, fill=BG_PANEL, outline=PINK)
            cv.tag_raise(t_id)

    def tick(self):
        try:
            self._drain_ui_queue()
            now = time.time()

            # Déclenchement de l'animation d'ennui après 50s sans demande
            if not self.is_executing and not self.bored_triggered and (now - self.last_command_time > 50):
                self.bored_triggered = True
                self.say("Je m'ennuie choom, tu veux pas faire quelque chose de plus excitant ?", mood="ennuie", hold=10)

            # « sleepy » reste jusqu'au réveil (wake) : sinon le « zzz... » se répétait toutes les 6 s
            if now > self.mood_until and self.mood not in ("happy", "sleepy"): self.mood = "happy"
            if now - self.last_input > 150 and self.mood != "sleepy": self.say("zzz...", "sleepy", hold=6)
            if self.mood != self.last_mood or now > self.pose_until: self.last_mood = self.mood; self.pick_pose(now)
            if random.random() < 0.01: self.glitch = random.randint(2, 5)
            self.cv.delete("all")
            self.draw(now - self.t0, now)
        except Exception as e:
            handle_crash(type(e), e, e.__traceback__)
        finally:
            try: self.root.after(35, self.tick)
            except Exception: pass

    def open_panel(self): self.win.deiconify()
    def close_panel(self): self.win.withdraw()
    def toggle_panel(self):
        self.wake(); self.close_panel() if self.win.state() == "normal" else self.open_panel()

    def run(self):
        self.tick()
        try: self.root.mainloop()
        except Exception as e: handle_crash(type(e), e, e.__traceback__)

def find_game(games, text):
    if not games: return None
    named = [(norm(g["name"]), g) for g in games if norm(g["name"])]
    for n, g in named:
        if n in text: return g
    return next(g for n, g in named if n == matches[0]) if (matches := difflib.get_close_matches(text, [n for n, _ in named], n=1, cutoff=0.5)) else None

def main():
    Capri().run()

if __name__ == "__main__":
    main()
