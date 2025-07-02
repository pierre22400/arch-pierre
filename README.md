# arch-pierre
Serveur ARCH personnel pour Render

Ce dépôt contient le serveur Flask personnel pour ARCH, destiné à un déploiement sur Render.

## 🔧 Déploiement Render

1. Créer un Web Service sur [Render.com](https://render.com/)
2. Connecter ce dépôt via GitHub
3. Configurer :

   - **Build command** :  
     ```
     pip install -r requirements.txt
     ```

   - **Start command** :  
     ```
     python arch.py
     ```

4. Ajouter les **variables d’environnement** dans Render :

   - `OPENAI_API_KEY` → ta clé GPT‑4o
   - `MISTRAL_API_KEY` → ta clé Mistral

5. Déployer.  
   Render te donnera une URL publique du type : https://arch-pierre.onrender.com

   
## 📁 Contenu

- `arch.py` — Le serveur Flask principal
- `requirements.txt` — Les dépendances Python
- `fiches/` — Dossier où seront enregistrées les fiches ARCH

