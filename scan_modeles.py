from google import genai

import json, os
from pathlib import Path

# La clé n'est plus écrite ici : elle vient de la variable GEMINI_API_KEY
# ou de la clé enregistrée dans la console de Capri (~/.capri/config.json).
def lire_cle():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    try:
        return json.loads((Path.home() / ".capri" / "config.json").read_text(encoding="utf-8")).get("api_key", "")
    except Exception:
        return ""

MA_CLE_API = lire_cle()
if not MA_CLE_API:
    raise SystemExit("Aucune clé API : mets-la dans la console de Capri (onglet IA) ou dans GEMINI_API_KEY.")

try:
    print("🚀 Connexion au Netrun de Google...")
    client = genai.Client(api_key=MA_CLE_API)
    
    print("\n--- MODÈLES DISPONIBLES ---\n")
    
    # Version ultra-simplifiée pour éviter toute erreur d'attribut
    for model in client.models.list():
        print(f"✅ {model.name}")
            
    print("\n✨ Fin du scan. Copie-moi la liste !")

except Exception as e:
    print(f"\n❌ ERREUR : {e}")
    
