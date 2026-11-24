# Capri — assistante de bureau

Capri est une petite assistante animée pour Windows : commandes vocales (F8),
lancement d'applis et de jeux, mode IA (Gemini), actualités (AskNews),
contrôle du PC à distance depuis le téléphone et « mode cours » (transcription
de visio, alerte quand on dit ton prénom).

## Installation (utilisateurs)

1. Va dans l'onglet **Releases** du dépôt et télécharge `CapriSetup.exe`.
2. Lance-le et suis l'assistant. Python et toutes les bibliothèques sont inclus :
   il n'y a rien d'autre à installer.
3. Au premier lancement, ouvre la console de Capri et colle tes propres clés API
   (onglet IA). Elles restent sur ton PC, dans `%USERPROFILE%\.capri\`.

> Windows SmartScreen peut afficher « Windows a protégé votre ordinateur » car
> l'installateur n'est pas signé. Clique sur **Informations complémentaires →
> Exécuter quand même**.

### Clés et services facultatifs

| Fonction | Ce qu'il faut |
|---|---|
| Mode IA | Clé API Gemini (Google AI Studio) |
| Actualités | Clé API AskNews |
| Réponses du mode cours | Clé API Anthropic (`anthropic_api_key`) |
| Contrôle à distance hors Wi-Fi | [ngrok](https://ngrok.com/download) : place `ngrok.exe` à côté de `Capri.exe` ou dans `%USERPROFILE%\.capri\` |
| Notifications téléphone | Appli ntfy + `ntfy_topic` |

Les réglages du serveur (clé d'accès générée automatiquement, PIN, ntfy, prénom)
sont dans `%USERPROFILE%\.capri\serveur_config.json`. Voir `config.example.json`.

### Contacts Discord

Dans la console de Capri, onglet **👥 CONTACTS**, associe un pseudo Discord aux noms
que tu prononces. Exemple : `lucas, lukas, lulu, luca` → `gougouz`. Ensuite
« Appelle Lucas » ou « Envoie un message à Lulu » contacte `gougouz`.
Les contacts sont enregistrés dans `%USERPROFILE%\.capri\contacts.json`.

### Raccourcis

- **F8** (maintenu) : parler à Capri
- **Serveur Capri** (menu Démarrer) : lance le serveur de contrôle à distance et
  affiche la clé d'accès à saisir sur le téléphone.

Le serveur de contrôle à distance est **désactivé par défaut**. Dans la console
(onglet ⚡ SYSTÈME) : boutons **Démarrer / Arrêter**, et case « Démarrer le serveur
à distance avec Capri » pour qu'il se lance automatiquement.

## Lancer depuis le code (développeurs)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python lanceur.py            :: l'assistante
python lanceur.py --serveur  :: le serveur seul
```

## Construire l'installateur

Prérequis : Python 3.12, [Inno Setup 6](https://jrsoftware.org/isdl.php) et, pour le HUD, le [.NET SDK 8](https://dotnet.microsoft.com/download/dotnet/8.0).

```bat
build.bat
```

- `dist\Capri\Capri.exe` : la version portable
- `installer\Output\CapriSetup.exe` : l'installateur à publier dans une Release GitHub

### HUD C# CapriDesktop

Le dossier `CapriDesktop/` contient le HUD WPF (bulle animée, .NET 8).
`build.bat` le compile automatiquement si le [.NET SDK 8](https://dotnet.microsoft.com/download/dotnet/8.0)
est installé, et l'installateur l'inclut. Il est publié en « autonome » : les
utilisateurs n'ont pas besoin d'installer .NET. Sans lui, Capri fonctionne quand même.

En développement, `python lanceur.py` lance le HUD depuis `CapriDesktop/`
(l'exe compilé s'il existe, sinon `dotnet run`).

## Structure

| Fichier | Rôle |
|---|---|
| `lanceur.py` | Point d'entrée de `Capri.exe` (`--serveur` pour le serveur) |
| `capri.py` | L'assistante (interface, vocal, IA, commandes) |
| `serveur.py` | Serveur Flask de contrôle à distance |
| `mode_cours.py` | Transcription de cours et alertes |
| `chemins.py` | Chemins compatibles script / `.exe` |
| `Capri.spec` | Recette PyInstaller |
| `installer/Capri.iss` | Script de l'installateur Inno Setup |
| `CapriDesktop/` | HUD C# WPF (projet .NET 8) |
