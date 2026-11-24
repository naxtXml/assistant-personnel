"""Mode cours de Capri : enregistre le son du PC pendant une visio, le transcrit,
repère les tâches données par la prof (et y répond avec Claude), et alerte quand
ton prénom est prononcé (notif PC + notif téléphone via ntfy + événement pour l'app).

Dépendances :
    pip install soundcard soundfile numpy SpeechRecognition anthropic plyer

Réglages facultatifs dans config.json :
    "ntfy_topic": "mon-sujet-cours-xxxx"      -> notif sur le téléphone (app ntfy)
    "anthropic_api_key": "sk-ant-..."      -> réponses aux tâches (sinon variable ANTHROPIC_API_KEY)
    "prenom": "TonPrenom"           -> alerte quand la prof dit ce prénom (désactivée si vide)
"""

import json
import os
import queue
import re
import threading
import time
import unicodedata
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

try:  # le serveur doit pouvoir démarrer même sans ces modules
    import numpy as np
    import soundcard as sc
    import soundfile as sf
except ImportError:
    np = sc = sf = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import anthropic
except ImportError:
    anthropic = None

# ---------------------------------------------------------------- Réglages
FREQUENCE = 48000
BLOC_SECONDES = 1
DUREE_TRANSCRIPTION = 5          # s d'audio par envoi à la reconnaissance vocale
LANGUE = "fr-FR"
DELAI_ENTRE_ALERTES = 20         # s entre deux alertes « prénom »
MODELE_CLAUDE = "claude-sonnet-5-5"
SEGMENTS_CONTEXTE = 12           # ~60 s de transcription envoyés pour analyser une tâche
SEGMENTS_APRES_MOT_CLE = 3       # attend ~15 s après un mot-clé pour avoir la consigne complète

MOTS_CLES_TACHE = [
    r"exercices?", r"devoirs?", r"a faire", r"a rendre", r"rendre", r"consignes?",
    r"pour (la semaine|la prochaine fois|demain|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)",
    r"vous (devez|devrez|allez devoir|aurez a)", r"je vous demande", r"je veux que vous",
    r"il (faut|faudra) que vous", r"travail (a|pour)", r"lisez", r"faites", r"preparez",
    r"redigez", r"repondez", r"resumez", r"projet", r"dm", r"td", r"tp", r"evaluation",
    r"controle", r"date limite", r"deadline",
]
REGEX_TACHE = re.compile(r"\b(" + "|".join(MOTS_CLES_TACHE) + r")\b")

PROMPT_EXTRACTION = """Tu écoutes un cours en visio pour aider un étudiant, {prenom}.
Voici un extrait de la transcription automatique (elle peut contenir des erreurs) :

<transcription>
{contexte}
</transcription>

Tâches déjà enregistrées (ne pas les redonner) :
{deja}

La professeure donne-t-elle dans cet extrait une ou plusieurs NOUVELLES tâches à faire
(exercice, devoir, lecture, question à préparer, travail à rendre...) ?
Réponds uniquement en JSON, sans texte autour :
{{"taches": [{{"description": "consigne claire et complète", "echeance": "date ou délai, sinon null"}}]}}
Si aucune nouvelle tâche, réponds {{"taches": []}}."""

PROMPT_REPONSE = """Tu aides {prenom}, un étudiant, pendant son cours en visio.
La professeure vient de donner cette tâche :

« {description} »{echeance}

Contexte du cours (transcription automatique, peut contenir des erreurs) :
<transcription>
{contexte}
</transcription>

Réalise la tâche de façon complète et utile. Si elle ne peut pas être faite directement
(ex. lire un chapitre), donne un plan d'action concret et les points clés à retenir.
Réponds en français, de façon structurée et concise."""


# ---------------------------------------------------------------- Utilitaires
def normaliser(texte):
    t = unicodedata.normalize("NFD", texte)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def format_horodatage(secondes):
    return f"{int(secondes // 60):02d}:{int(secondes % 60):02d}"


def vers_mono_int16(donnees):
    mono = donnees.mean(axis=1) if donnees.ndim > 1 else donnees
    return (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def obtenir_micro_loopback():
    """Périphérique loopback des haut-parleurs/casque par défaut (= le son de la visio)."""
    speaker = sc.default_speaker()
    try:
        return sc.get_microphone(id=str(speaker.name), include_loopback=True), speaker.name
    except Exception:
        pass
    for mic in sc.all_microphones(include_loopback=True):
        if getattr(mic, "isloopback", False):
            return mic, mic.name
    return sc.default_microphone(), sc.default_microphone().name


def init_com_thread():
    """WASAPI (soundcard) a besoin de COM initialisé dans chaque thread sous Windows."""
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)
    except Exception:
        pass


# ---------------------------------------------------------------- Moteur
class MoteurCours:
    def __init__(self, dossier_sortie, config_getter):
        self.dossier = Path(dossier_sortie)
        self.config_getter = config_getter     # fonction qui relit config.json
        self._verrou = threading.Lock()
        self._evenements = deque(maxlen=3000)
        self._prochain_id = 1
        self.taches = []                       # [{id, horodatage, description, echeance, reponse}]
        self.actif = False
        self.statut = "Mode cours arrêté"
        self.debut = None
        self.fichiers = {}
        self._stop = threading.Event()

    # ----- Événements (lus par l'app via /cours/etat)
    def _publier(self, type_, **donnees):
        with self._verrou:
            ev = {"id": self._prochain_id, "type": type_, "heure": datetime.now().strftime("%H:%M:%S"), **donnees}
            self._prochain_id += 1
            self._evenements.append(ev)
            return ev

    def _statut(self, texte):
        self.statut = texte
        self._publier("statut", texte=texte)
        print(f"[cours] {texte}")

    def etat(self, depuis=0):
        with self._verrou:
            evts = [e for e in self._evenements if e["id"] > depuis]
            dernier = self._prochain_id - 1
        return {
            "actif": self.actif,
            "statut": self.statut,
            "debut": self.debut,
            "dernier_id": dernier,
            "evenements": evts[-300:],
            "taches": list(self.taches),
            "fichiers": {k: str(v) for k, v in self.fichiers.items()},
        }

    # ----- Démarrage / arrêt
    def demarrer(self):
        if self.actif:
            return False, "Le mode cours est déjà en route"
        if sc is None or sf is None:
            return False, "Modules manquants sur le PC : pip install numpy soundcard soundfile SpeechRecognition"
        cfg = self.config_getter() or {}
        self.prenom = str(cfg.get("prenom") or "").strip()
        # Sans prénom configuré, l'alerte « on t'appelle » est désactivée
        self.regex_prenom = re.compile(r"\b" + re.escape(normaliser(self.prenom)) + r"\b") if self.prenom else None
        self.ntfy_topic = str(cfg.get("ntfy_topic") or "").strip()
        cle = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=cle) if (anthropic and cle) else None

        self.dossier.mkdir(parents=True, exist_ok=True)
        base = self.dossier / f"cours_{datetime.now():%Y-%m-%d_%Hh%M}"
        self.fichiers = {"audio": base.with_suffix(".wav"), "texte": base.with_suffix(".txt"),
                         "taches": base.with_name(base.name + "_taches.md")}
        self.taches = []
        self._historique = deque(maxlen=SEGMENTS_CONTEXTE)
        self._attente = None
        self._derniere_alerte = 0.0
        self._file_audio = queue.Queue()
        self._file_taches = queue.Queue()
        self._stop.clear()
        self.actif = True
        self.debut = datetime.now().isoformat(timespec="seconds")

        threading.Thread(target=self._thread_enregistrement, daemon=True).start()
        if sr is not None:
            threading.Thread(target=self._thread_transcription, daemon=True).start()
            threading.Thread(target=self._thread_taches, daemon=True).start()
        else:
            self._publier("info", texte="SpeechRecognition absent : seul l'audio est enregistré.")
        if self.client is None:
            self._publier("info", texte="Pas de clé API Claude : les tâches seront notées sans réponse.")
        return True, "Mode cours démarré"

    def arreter(self):
        if not self.actif:
            return False, "Le mode cours n'est pas en route"
        self._stop.set()
        self._statut("Arrêt en cours, finalisation...")
        return True, "Arrêt demandé"

    # ----- Threads
    def _thread_enregistrement(self):
        init_com_thread()
        frames, tampon, frames_tampon = 0, [], 0
        seuil = FREQUENCE * DUREE_TRANSCRIPTION
        try:
            micro, nom = obtenir_micro_loopback()
            self._statut(f"🟢 Enregistrement en cours — {nom}")
            with micro.recorder(samplerate=FREQUENCE) as rec:
                canaux = micro.channels if isinstance(micro.channels, int) else 2
                with sf.SoundFile(str(self.fichiers["audio"]), mode="w", samplerate=FREQUENCE,
                                  channels=canaux, subtype="PCM_16") as wav:
                    while not self._stop.is_set():
                        d = rec.record(numframes=FREQUENCE * BLOC_SECONDES)
                        if d is None or len(d) == 0:
                            continue
                        wav.write(d)
                        frames += len(d)
                        if sr is not None:
                            tampon.append(d)
                            frames_tampon += len(d)
                            if frames_tampon >= seuil:
                                h = (frames - frames_tampon) / FREQUENCE
                                self._file_audio.put((vers_mono_int16(np.concatenate(tampon)), h))
                                tampon, frames_tampon = [], 0
                    if sr is not None and tampon:
                        h = (frames - frames_tampon) / FREQUENCE
                        self._file_audio.put((vers_mono_int16(np.concatenate(tampon)), h))
        except Exception as e:
            self._statut(f"❌ Erreur enregistrement : {e}")
        finally:
            if sr is not None:
                self._file_audio.put(None)
            self.actif = False
            duree = frames / FREQUENCE
            self._statut(f"⏹ Cours terminé ({duree / 60:.0f} min) — fichiers dans {self.dossier.name}"
                         if frames else "⏹ Arrêté — aucun son capté")

    def _thread_transcription(self):
        reco = sr.Recognizer()
        with open(self.fichiers["texte"], "a", encoding="utf-8") as journal:
            while True:
                item = self._file_audio.get()
                if item is None:
                    if self._attente is not None:
                        self._soumettre_contexte()
                    self._file_taches.put(None)
                    return
                audio, h = item
                try:
                    texte = reco.recognize_google(sr.AudioData(audio, FREQUENCE, 2), language=LANGUE).strip()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    self._statut("🔴 Pas d'internet pour la transcription (l'audio continue)")
                    continue
                except Exception:
                    continue
                if not texte:
                    continue
                appel = self._verifier_prenom(h, texte)
                self._publier("texte", t=format_horodatage(h), texte=texte, appel=appel)
                journal.write(f"[{format_horodatage(h)}] {texte}\n")
                journal.flush()
                self._detecter_tache(h, texte)

    def _verifier_prenom(self, h, texte):
        if not self.regex_prenom or not self.regex_prenom.search(normaliser(texte)):
            return False
        now = time.time()
        if now - self._derniere_alerte >= DELAI_ENTRE_ALERTES:
            self._derniere_alerte = now
            msg = f"[{format_horodatage(h)}] « {texte} »"
            self._publier("appel", t=format_horodatage(h), texte=texte)
            threading.Thread(target=self._notifier, args=(f"🔔 {self.prenom}, la prof t'appelle !", msg),
                             daemon=True).start()
        return True

    def _notifier(self, titre, message):
        try:
            from plyer import notification
            notification.notify(title=titre, message=message[:250], app_name="Capri — cours", timeout=10)
        except Exception:
            pass
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
        if self.ntfy_topic:
            try:
                req = urllib.request.Request(
                    f"https://ntfy.sh/{self.ntfy_topic}", data=message.encode("utf-8"),
                    headers={"Title": titre.encode("utf-8"), "Priority": "urgent", "Tags": "bell"})
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                print(f"[cours] ntfy : {e}")

    # ----- Tâches
    def _detecter_tache(self, h, texte):
        self._historique.append((h, texte))
        if REGEX_TACHE.search(normaliser(texte)):
            self._attente = SEGMENTS_APRES_MOT_CLE
        elif self._attente is not None:
            self._attente -= 1
            if self._attente <= 0:
                self._soumettre_contexte()

    def _soumettre_contexte(self):
        self._attente = None
        if not self._historique:
            return
        contexte = "\n".join(f"[{format_horodatage(h)}] {t}" for h, t in self._historique)
        self._file_taches.put((self._historique[0][0], contexte))

    def _thread_taches(self):
        while True:
            item = self._file_taches.get()
            if item is None:
                return
            h, contexte = item
            try:
                if self.client:
                    self._analyser(h, contexte)
                else:
                    self._enregistrer_tache(h, "Consigne possible (à vérifier)", None, contexte, None)
            except Exception as e:
                self._statut(f"⚠️ Analyse des tâches impossible : {e}")
                self._enregistrer_tache(h, "Consigne possible (analyse échouée)", None, contexte, None)

    def _demander(self, prompt, max_tokens):
        rep = self.client.messages.create(model=MODELE_CLAUDE, max_tokens=max_tokens,
                                          messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in rep.content if getattr(b, "type", "") == "text").strip()

    def _analyser(self, h, contexte):
        deja = "\n".join(f"- {t['description']}" for t in self.taches) or "(aucune)"
        brut = self._demander(PROMPT_EXTRACTION.format(prenom=self.prenom or "l'étudiant", contexte=contexte, deja=deja), 800)
        m = re.search(r"\{.*\}", brut, re.DOTALL)
        for tache in (json.loads(m.group(0)).get("taches", []) if m else []):
            desc = (tache.get("description") or "").strip()
            if not desc:
                continue
            ech = tache.get("echeance")
            self._statut(f"📝 Tâche détectée : {desc[:60]} — réponse en cours...")
            rep = self._demander(PROMPT_REPONSE.format(
                prenom=self.prenom or "l'étudiant", description=desc, contexte=contexte,
                echeance=f"\nÉchéance : {ech}" if ech else ""), 3000)
            self._enregistrer_tache(h, desc, ech, contexte, rep)
            self._statut("🟢 Enregistrement en cours" if self.actif else self.statut)

    def _enregistrer_tache(self, h, description, echeance, contexte, reponse):
        tache = {"id": len(self.taches) + 1, "t": format_horodatage(h), "description": description,
                 "echeance": echeance, "reponse": reponse, "extrait": contexte}
        self.taches.append(tache)
        self._publier("tache", **tache)
        chemin = self.fichiers["taches"]
        nouveau = not chemin.exists()
        with open(chemin, "a", encoding="utf-8") as f:
            if nouveau:
                f.write(f"# Tâches du cours — {datetime.now():%d/%m/%Y %H:%M}\n\n")
            f.write(f"## [{tache['t']}] {description}\n\n")
            if echeance:
                f.write(f"**Échéance :** {echeance}\n\n")
            if reponse:
                f.write(f"### Réponse\n\n{reponse}\n\n")
            f.write(f"<details><summary>Extrait</summary>\n\n```\n{contexte}\n```\n</details>\n\n---\n\n")
        if self.ntfy_topic:
            threading.Thread(target=self._ntfy_tache, args=(description,), daemon=True).start()

    def _ntfy_tache(self, description):
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{self.ntfy_topic}", data=description[:300].encode("utf-8"),
                headers={"Title": "📝 Nouvelle tâche du cours".encode("utf-8"), "Tags": "memo"})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
