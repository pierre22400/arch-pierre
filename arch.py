import glob
import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
app = Flask(__name__)
#CORS(app, resources={r"/*": {"origins": "http://localhost:8000"}})
CORS(app)
import os
import json
from datetime import datetime
sys.path.append(os.path.dirname(__file__))
import time
import traceback
import spacy
from balises_utils import (
    générer_tags_systeme,
    generer_resume_arch,         # ✅ fallback si résumé échoue
    generer_balises_mistral,     # ✅ fallback si balises échouent
    afficher_matrice_console,
    generer_balises_typologiques,
    generer_resume_et_balises_unifie
 )
from tension_utils import detection_trame_possible
from arch_loader import charger_fiche_valide




nlp = spacy.load("fr_core_news_md")

from dotenv import load_dotenv

load_dotenv()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")


def trouver_tiddlywiki_recent():
    import os
    dossier = os.path.expanduser(r"C:\Users\DENIS\Downloads")
    fichiers = glob.glob(os.path.join(dossier, "TiddlyDEVELOPPEMENT*.html"))
    if not fichiers:
        return None
    return max(fichiers, key=os.path.getmtime)

# 📁 Configuration mémoire principale ARCH
DOSSIER_PAR_DEFAUT = os.path.join(os.getcwd(), "ARCH_MEMOIRE")
MEMORY_FOLDER = os.getenv("ARCH_MEMOIRE_FOLDER", DOSSIER_PAR_DEFAUT)
DOSSIER_FICHES = os.path.join(MEMORY_FOLDER, "fiches")

# Création des dossiers nécessaires
os.makedirs(MEMORY_FOLDER, exist_ok=True)
os.makedirs(DOSSIER_FICHES, exist_ok=True)

LEXIQUE_PATH = os.path.join(MEMORY_FOLDER, "lexique_commandes.json")

if not os.path.exists(LEXIQUE_PATH):
    print("⚠️ lexique_commandes.json introuvable, création d’un fichier vide.")
    with open(LEXIQUE_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f)

try:
    with open(LEXIQUE_PATH, "r", encoding="utf-8") as f:
        lexique_commandes = json.load(f)
except Exception as e:
    print("❌ Erreur de chargement du lexique :", str(e))
    lexique_commandes = {}


# 💡 Définir ici pour que toutes les routes y aient accès
etat_arch = {
    "phase": "inactive",  # valeurs possibles : inactive, phase1, phase2, ...
    "derniere_action": None
}

from tiddlywiki_extractor_robuste import extraire_tiddler_depuis_html


@app.route('/')
def index():
    return send_from_directory('.', 'bbgpt_ui_typo_chatgpt.html')

@app.route("/arch/chemin_heuristique", methods=["GET"])
def chemin_heuristique():
    chemin = naviguer_selon_heuristique(dossier=MEMORY_FOLDER)
    return jsonify(chemin)
def formater_prompt_structuré(chemin):
    prompt = "Tu es BBGPT, un agent cognitif contraint par une méthode heuristique.\n"
    prompt += "Voici un parcours structuré de blocs à interpréter selon cette méthode.\n\n"

    for i, étape in enumerate(chemin, 1):
        tag = étape["étape"]["tag"]
        action = étape["étape"]["action"]
        prompt += f"Étape {i}: {tag} → {action}\n"
        for bloc in étape["blocs"]:
            titre = bloc.get("titre", "Sans titre")
            contenu = bloc.get("contenu", "").strip()
            prompt += f"  • {titre} : {contenu[:300]}{'...' if len(contenu) > 300 else ''}\n"
        prompt += "\n"

    prompt += "Ta tâche est de produire une réponse en respectant l'ordre des étapes et leur logique :\n"
    prompt += "- Collecter les hypothèses\n"
    prompt += "- Relier les preuves\n"
    prompt += "- Produire une synthèse finale\n"

    return prompt

@app.route("/arch/prompt_heuristique", methods=["GET"])
def prompt_heuristique():
    try:
        chemin = naviguer_selon_heuristique(dossier=MEMORY_FOLDER)
      
        if isinstance(chemin, dict) and "erreur" in chemin:
            print("❌ Erreur détectée :", chemin["erreur"])
            return jsonify({"erreur": chemin["erreur"]}), 400

        if not chemin or all(len(etape.get("blocs", [])) == 0 for etape in chemin):
            print("⚠️ Aucun bloc détecté dans les étapes")
            return jsonify({"erreur": "Aucun bloc mémoire trouvé pour la méthode heuristique."}), 400

        if etat_arch.get("phase") != "phase1":
            print("❌ BBGPT non activé — phase non définie")
            return jsonify({"erreur": "Phase non activée. Veuillez lancer le moteur."}), 400

        prompt = formater_prompt_structuré(chemin)
        print("📝 prompt généré :", prompt)
        return jsonify({"prompt": prompt})

    except Exception as e:
        print("💥 Exception dans prompt_heuristique :", str(e))
        return jsonify({"erreur": f"Erreur interne : {str(e)}"}), 500



# Chargement du lexique des commandes
LEXIQUE_PATH = os.path.join(MEMORY_FOLDER, "lexique_commandes.json")
try:
    with open(LEXIQUE_PATH, 'r', encoding='utf-8') as f:
        LEXIQUE_COMMANDES = json.load(f)
except Exception as e:
    LEXIQUE_COMMANDES = {}
    print(f"Erreur de chargement du lexique : {e}")

os.makedirs(MEMORY_FOLDER, exist_ok=True)

def analyse_texte(texte):
    lignes = texte.strip().split('\n')
    analyse = [{"ligne": i + 1, "contenu": ligne.strip()} for i, ligne in enumerate(lignes) if ligne.strip()]
    return analyse

def attribuer_vitalité(texte, analyse, statut="actif", vitalité=1.0, tags=None):
    """
    Crée une entrée mémoire BBGPT avec vitalité heuristique.
    """
    if tags is None:
        tags = []

    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    mémoire = {
        "horodatage": horodatage,
        "statut": statut,
        "vitalité": vitalité,
        "tags": tags,
        "texte": texte,
        "analyse": analyse
    }

    return mémoire

def sauvegarder_memoire(texte, analyse, dossier=DOSSIER_FICHES, statut="actif", vitalité=1.0, tags=None):
    """
    Sauvegarde une analyse dans un fichier mémoire enrichi (avec vitalité).
    """
    if not os.path.exists(dossier):
        os.makedirs(dossier)

    memoire = attribuer_vitalité(texte, analyse, statut, vitalité, tags)

    nom_fichier = f"{memoire['horodatage']}.json"
    chemin_fichier = os.path.join(dossier, nom_fichier)

    with open(chemin_fichier, 'w', encoding='utf-8') as f:
        json.dump(memoire, f, ensure_ascii=False, indent=2)

    return nom_fichier
def naviguer_selon_heuristique(dossier=None):
    if dossier is None:
        dossier = MEMORY_FOLDER

    methode_path = os.path.join(dossier, "methode_heuristique.json")
    if not os.path.exists(methode_path):
        return {"erreur": "Fichier methode_heuristique.json introuvable."}

    try:
        with open(methode_path, "r", encoding="utf-8") as f:
            methode = json.load(f)
    except Exception as e:
        return {"erreur": f"Erreur de lecture de la méthode heuristique : {str(e)}"}
   
    blocs = []
    for nom_fichier in os.listdir(dossier):
        if nom_fichier.endswith(".json") and nom_fichier != "methode_heuristique.json":
            chemin = os.path.join(dossier, nom_fichier)
            with open(chemin, "r", encoding="utf-8") as f:
                try:
                    bloc = json.load(f)
                    bloc["_fichier"] = nom_fichier
                    blocs.append(bloc)
                except Exception:
                    pass

    chemin = []
    for étape in methode.get("étapes", []):
        tag = étape.get("tag")
        if not tag:
            continue
        blocs_filtrés = [b for b in blocs if tag in b.get("tags", [])]
        chemin.append({
            "étape": étape,
            "blocs": blocs_filtrés
        })

    return chemin

@app.route('/interpreter_commande', methods=['POST'])
def interpreter_commande():
    data = request.get_json()
    texte = data.get("commande", "")  # correspond au champ dans l'interface
    analyse = analyse_texte(texte)
    fichier = sauvegarder_memoire(texte, analyse)
    return jsonify({
        "retour": f"Commande analysée et enregistrée dans : {fichier}"
    })

@app.route('/analyser', methods=['POST'])
def analyser():
    data = request.get_json()
    texte = data.get('texte', '')
    analyse = analyse_texte(texte)
    return jsonify({"analyse": analyse})

@app.route('/memoire/<nom>', methods=['GET'])
def lire_memoire(nom):
    chemin = os.path.join(DOSSIER_FICHES, nom)
    if not os.path.exists(chemin):
        return jsonify({"erreur": "Fichier introuvable"}), 404
    try:
        with open(chemin, 'r', encoding='utf-8') as f:
            contenu = json.load(f)
    except Exception as e:
        return jsonify({"erreur": f"Erreur de lecture JSON : {str(e)}"}), 500

    if "matrice_cognitive" not in contenu:
        contenu["matrice_cognitive"] = []

    return jsonify(contenu)

def lire_memo_r_depuis_fichier(nom_fichier):
    chemin = os.path.join(DOSSIER_FICHES, nom_fichier)
    if not os.path.exists(chemin):
        raise FileNotFoundError("Fichier introuvable : " + nom_fichier)

    with open(chemin, 'r', encoding='utf-8') as f:
        fiche = json.load(f)

    memo_r = fiche.get("memo_r", {})
    fragments = memo_r.get("fragments", [])
    return fragments

def explorer_memo_r_console(nom_fichier, balise_cible=None, score_min=0):
    try:
        fragments = lire_memo_r_depuis_fichier(nom_fichier)
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return

        print(f"\n🔎 Exploration de {nom_fichier} — filtre : balise={balise_cible or '—'}, score ≥ {score_min}\n")

    nb = 0
    for frag in fragments:
        texte = frag.get("texte", "").strip()
        balises = frag.get("balises", [])
        score = frag.get("score", 0)
        elements_visuels = frag.get("éléments_visuels", "")
        justification = frag.get("justification_balise", "")

        if not texte:
            continue
        if balise_cible and balise_cible not in balises:
            continue
        if score < score_min:
            continue

        print(f"🧠 {frag.get('id', '?')} – Score : {score}")
        print(f"✏️  {texte}")
        print(f"🏷️  {', '.join(balises)}")
        if elements_visuels:
            print(f"🎨 Élément visuel : {elements_visuels}")
        if justification:
            print(f"📝 Justification : {justification}")
        print()
        nb += 1

    print(f"✅ {nb} fragment(s) affiché(s)\n")




@app.route('/memoire/mettre_a_jour', methods=['POST'])
def api_mettre_a_jour_vitalite():
    data = request.json
    nom_fichier = data.get("nom_fichier")
    vitalite = data.get("vitalite")
    statut = data.get("statut")

    chemin = os.path.join(MEMORY_FOLDER, nom_fichier)

    ok, message = mettre_a_jour_vitalite(chemin, nouvelle_vitalite=vitalite, nouveau_statut=statut)
    return jsonify({"success": ok, "message": message})

@app.route('/memoire/lister', methods=['GET'])
def lister_memoire():
    dossier = DOSSIER_FICHES
    fichiers = []

    if os.path.exists(dossier):
        for nom_fichier in os.listdir(dossier):
            if nom_fichier.endswith(".json"):
                chemin = os.path.join(dossier, nom_fichier)
                try:
                    with open(chemin, 'r', encoding='utf-8') as f:
                        contenu = json.load(f)
                        fichiers.append({
                            "title": contenu.get("title", ""),
                            "texte": contenu.get("texte", ""),
                            "nom": nom_fichier,
                            "statut": contenu.get("statut", "?"),
                            "vitalité": contenu.get("vitalité", "?"),
                            "tags": contenu.get("tags", [])
                        })
                except Exception as e:
                    print(f"❌ Erreur de lecture du fichier {nom_fichier} :", e)

    print("📦 Moments figés retournés :", len(fichiers))
    return jsonify(fichiers)

@app.route("/memoire/fiche/<titre>", methods=["GET"])
def recuperer_fiche_par_titre(titre):
    try:
        fichiers = os.listdir(DOSSIER_FICHES)
        for nom_fichier in fichiers:
            chemin = os.path.join(DOSSIER_FICHES, nom_fichier)
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = json.load(f)
                if contenu.get("title") == titre:
                    return jsonify(contenu)
        return jsonify({"erreur": "Fiche non trouvée"}), 404
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500

@app.route("/arch/sauvegarder_trame", methods=["POST"])
def sauvegarder_trame():
    trame = request.get_json()
    if not trame or "id" not in trame:
        return jsonify({"message": "Trame invalide"}), 400

    dossier_trames = os.path.join(MEMORY_FOLDER, "trames_arch")
    os.makedirs(dossier_trames, exist_ok=True)

    nom_fichier = f"{trame['id']}.json"
    chemin = os.path.join(dossier_trames, nom_fichier)

    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(trame, f, ensure_ascii=False, indent=2)

    return jsonify({"message": f"Trame sauvegardée sous {nom_fichier}"}), 200

@app.route("/arch/audit_balises", methods=["GET"])
def audit_balises():
    inventaire = {}
    for fichier in os.listdir(DOSSIER_FICHES):
        if fichier.endswith(".json"):
            chemin = os.path.join(DOSSIER_FICHES, fichier)
            try:
                with open(chemin, encoding="utf-8") as f:
                    fiche = json.load(f)
                    for tag in fiche.get("tags", []) + fiche.get("tags_systeme", []):
                        inventaire[tag] = inventaire.get(tag, 0) + 1
            except:
                continue
    return jsonify({"balises": inventaire})

@app.route("/arch/interpreter_trame", methods=["POST"])
def interpreter_trame():
    data = request.get_json()
    trame_id = data.get("id", "")
    prompt = data.get("prompt", "")

    if not trame_id or not prompt:
        return jsonify({"resultat": "Paramètres manquants"}), 400

    # 🔮 Réponse simulée
    resultat = f"(Mock BBGPT) Synthèse : la trame {trame_id} pose une question sur « {prompt[:40]}... », elle mobilise 3 blocs. Résultat : une dynamique entre intuition et preuve."

    return jsonify({"resultat": resultat})

@app.route("/arch/lancer_phase", methods=["POST"])
def lancer_phase():
    data = request.get_json()
    phase = data.get("phase")
    etat_arch["phase"] = phase
    etat_arch["derniere_action"] = f"Phase {phase} lancée."

    # ✅ TRACE
    print("✅ PHASE ACTIVÉE :", etat_arch)

    return jsonify({"etat": etat_arch})


@app.route('/arch/console', methods=['POST'])
def arch_console():
    data = request.json
    commande = data.get("commande", "")

    resultat = interpreter_commande(commande)

    if resultat.get("action") is None:
        return jsonify({"retour": f"❌ {resultat.get('erreur')}"})

    action = resultat["action"]
    cible = resultat["cible"]
    arguments = resultat.get("arguments", [])

    # Réponse simulée pour cette étape
    return jsonify({
        "retour": f"✅ Action détectée : {action} | Cible : {cible} | Arguments : {arguments}"
    })

@app.route('/arch/graphe_vitalite', methods=['GET'])
def graphe_vitalite():
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
    import datetime

    dossier = MEMORY_FOLDER
    fichiers = []

    if os.path.exists(dossier):
        for nom_fichier in os.listdir(dossier):
            if nom_fichier.endswith(".json"):
                chemin = os.path.join(dossier, nom_fichier)
                try:
                    with open(chemin, 'r', encoding='utf-8') as f:
                        contenu = json.load(f)
                        vitalite = contenu.get("vitalité", 0)
                        horodatage = contenu.get("horodatage", nom_fichier.split('.')[0])
                        try:
                            date = datetime.strptime(horodatage, "%Y-%m-%d_%H-%M-%S")
                        except:
                            date = datetime.now()
                        fichiers.append((date, vitalite))
                except:
                    continue

    fichiers.sort()
    if not fichiers:
        return "Aucune donnée", 404

    dates = [f[0] for f in fichiers]
    vitalites = [f[1] for f in fichiers]
    couleurs = plt.cm.coolwarm(np.array(vitalites))

    plt.figure(figsize=(10, 5))
    plt.scatter(dates, vitalites, c=couleurs, s=80, edgecolors='black')
    plt.plot(dates, vitalites, color='gray', linestyle='--', alpha=0.5)
    plt.title("Vitalité mémoire BBGPT")
    plt.xlabel("Date et heure")
    plt.ylabel("Vitalité")
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    from io import BytesIO
    import base64
    img_io = BytesIO()
    plt.savefig(img_io, format='png')
    img_io.seek(0)

    return app.response_class(img_io.read(), mimetype='image/png')

def extraire_objets_memoriels_prioritaires(dossier=MEMORY_FOLDER, top_n=5):
    objets = []

    if os.path.exists(dossier):
        for nom in os.listdir(DOSSIER_FICHES):
            if nom.endswith(".json"):
                chemin = os.path.join(DOSSIER_FICHES, nom)
                try:
                    with open(chemin, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("statut") == "actif":
                            vitalite = data.get("vitalité", 0.0)
                            objets.append((vitalite, nom, data.get("tags", [])))
                except:
                    continue

    objets.sort(reverse=True)  # tri décroissant de vitalité
    return objets[:top_n]

def parser_commande(commande):
    commande = commande.strip().lower()
    mots = commande.split()

    if not mots:
        return {"action": None, "erreur": "Commande vide"}

    verbe = mots[0]
    arguments = mots[1:]

    for cle, infos in LEXIQUE_COMMANDES.items():
        if verbe == cle or verbe in infos.get("alias", []):
            return {
                "action": infos["action"],
                "cible": infos["cible"],
                "arguments": arguments,
                "verbe": verbe
            }

    return {"action": None, "erreur": f"Verbe inconnu : {verbe}"}


@app.route('/arch/prioritaires', methods=['GET'])
def lister_objets_prioritaires():
    top = extraire_objets_memoriels_prioritaires()
    reponse = [{"vitalité": v, "nom": n, "tags": t} for v, n, t in top]
    return jsonify(reponse)

def mettre_a_jour_vitalite_bayesienne(fichier_json, p_h=0.5, taux_global_succes=0.5):
    try:
        with open(fichier_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        activations = data.get("activations", 0)
        success = data.get("success", 0)

        if activations == 0:
            return False  # Pas assez de données pour mettre à jour

        # Calculs bayésiens
        p_e_given_h = success / activations
        p_e = taux_global_succes
        p_h_given_e = (p_e_given_h * p_h) / p_e if p_e > 0 else p_h

        # Mise à jour de la vitalité
        data["vitalité"] = round(min(max(p_h_given_e, 0.0), 1.0), 3)
        data["statut"] = (
            "actif" if data["vitalité"] >= 0.7 else
            "moribond" if data["vitalité"] >= 0.3 else
            "obsolète"
        )

        with open(fichier_json, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        return str(e)

def mettre_a_jour_toute_vitalite_bayesienne(dossier=MEMORY_FOLDER, p_h=0.5, taux_global_succes=0.5):
    if not os.path.exists(dossier):
        return 0

    total = 0
    for nom in os.listdir(DOSSIER_FICHES):
        if nom.endswith(".json"):
            chemin = os.path.join(DOSSIER_FICHES, nom)
            resultat = mettre_a_jour_vitalite_bayesienne(chemin, p_h, taux_global_succes)
            if resultat is True:
                total += 1

    return total
@app.route('/arch/ajuster_vitalites', methods=['POST'])
def ajuster_vitalites():
    nb = mettre_a_jour_toute_vitalite_bayesienne()
    return jsonify({"mise_a_jour": nb})

@app.route("/arch/explorer_memo_r", methods=["GET"])
def explorer_memo_r():
    nom_fichier = request.args.get("fichier", "").strip()
    balise_cible = request.args.get("balise", "").strip()
    score_min = int(request.args.get("score_min", 0))

    try:
        fragments = lire_memo_r_depuis_fichier(nom_fichier)
    except Exception as e:
        return jsonify({"erreur": str(e)}), 400

    résultats = []
    for frag in fragments:
        texte = frag.get("texte", "").strip()
        balises = frag.get("balises", [])
        score = frag.get("score", 0)

        if not texte:
            continue
        if balise_cible and balise_cible not in balises:
            continue
        if score < score_min:
            continue

        résultats.append({
            "id": frag.get("id", "?"),
            "texte": texte,
            "balises": balises,
            "score": score
        })

    return jsonify({
        "fragments": résultats,
        "total": len(résultats)
    })


@app.route('/analyser_commande', methods=['POST'])
def analyser_commande():
    data = request.get_json()
    commande = data.get("commande", "").strip()

    try:
        with open(LEXIQUE_PATH, encoding="utf-8") as f:
            lexique = json.load(f)
    except Exception as e:
        return jsonify({"retour": f"Erreur de lecture du lexique : {e}"})

    mots = commande.split()
    if not mots:
        return jsonify({"retour": "Commande vide."})

    verbe_utilise = mots[0]
    cible = " ".join(mots[1:]) if len(mots) > 1 else ""

    for item in lexique:
        if verbe_utilise in item.get("alias", []):
            action = item.get("action")
            if action == "open_tiddler":
                chemin = trouver_tiddlywiki_recent()
                if not chemin:
                    return jsonify({"retour": "Aucun fichier TiddlyWiki trouvé."})
                texte, erreur = extraire_tiddler_depuis_html(cible, chemin)
                if erreur:
                    return jsonify({"retour": erreur})
                return jsonify({"retour": texte})
            else:
                return jsonify({"retour": f"Action '{action}' reconnue mais pas encore implémentée."})

    return jsonify({"retour": f"Verbe inconnu : {verbe_utilise}"})


#@app.route('/ping')
#def ping():
 #   return jsonify({"statut": "ARCH actif"})

@app.route('/nettoyer_html', methods=['POST'])
def nettoyer_html():
    data = request.get_json()
    html = data.get("html", "")

    # Simulation du "nettoyage" du HTML sans OpenAI
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    texte_propre = soup.get_text(separator="\n").strip()

    return jsonify({"texte": texte_propre})

@app.route('/extraire_et_nettoyer', methods=['POST'])
def extraire_et_nettoyer():
    data = request.get_json()
    nom_tiddler = data.get("titre", "").strip()

    if not nom_tiddler:
        return jsonify({"erreur": "Titre de tiddler manquant"}), 400

    chemin_html = "TiddlyDEVELOPPEMENT.html"  # adapte ce chemin si besoin

    contenu_brut, erreur = extraire_tiddler_depuis_html(nom_tiddler, chemin_html)
    if erreur:
        return jsonify({"erreur": erreur}), 404

    # Nettoyage local via BeautifulSoup
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(contenu_brut, 'html.parser')
    texte_propre = soup.get_text(separator="\n").strip()

    return jsonify({"texte": texte_propre})

@app.route('/analyser_tiddler', methods=['POST'])
def analyser_tiddler():
    data = request.get_json()
    texte = data.get("texte", "").strip()

    if not texte:
        return jsonify({"erreur": "Texte manquant"}), 400

    # Simulation : traitement local simulé par règles simples
    nombre_mots = len(texte.split())
    resume = texte[:300] + "..." if len(texte) > 300 else texte
    analyse_simulee = {
        "résumé": resume,
        "longueur": f"{nombre_mots} mots",
        "note": "Lecture simulée réussie par ARCH (sans GPT)"
    }

    return jsonify(analyse_simulee)

@app.route("/generer_tiddler_json", methods=["POST"])
def generer_tiddler_json():
    data = request.get_json()
    titre = data.get("titre", "").strip()
    texte = data.get("texte", "").strip()
    if not titre or not texte:
        return jsonify({"erreur": "Titre ou texte manquant"}), 400

    tiddler = {
        "title": titre,
        "texte": texte,
        "tags": "",
        "created": datetime.now().strftime("%Y%m%d%H%M")
    }

    # Crée le dossier si besoin
    os.makedirs(MEMORY_FOLDER, exist_ok=True)

    # Format du nom de fichier
    nom_fichier = os.path.join(MEMORY_FOLDER, f"{titre.replace(' ', '_')}.json")

    # Écriture du fichier
    with open(nom_fichier, "w", encoding="utf-8") as f:
        json.dump(tiddler, f, ensure_ascii=False, indent=2)

    return jsonify({"fichier": nom_fichier})

# ✅ Index mémoire RAM au démarrage
index_fiches_minimales = {}

def construire_index_memoire(dossier=DOSSIER_FICHES):
    global index_fiches_minimales
    index_fiches_minimales = {}  # reset

    for nom in os.listdir(dossier):
        if not nom.endswith(".json"):
            continue
        chemin = os.path.join(dossier, nom)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                fiche = json.load(f)
        except:
            continue  # skip fichier illisible

        fragments = fiche.get("matrice_cognitive", [])
        nb_fragments = len([f for f in fragments if isinstance(f, dict) and "fragment" in f])

        balises = set()
        for frag in fragments:
            if isinstance(frag, dict):
                for famille in ["structurelle", "conceptuelle", "référentielle", "vitale"]:
                    for b in frag.get(famille, []):
                        balises.add(b)

        index_fiches_minimales[nom] = {
            "title": fiche.get("title", ""),
            "statut": fiche.get("statut", "?"),
            "vitalité": fiche.get("vitalité", 0.0),
            "tags": fiche.get("tags", []),
            "tags_systeme": fiche.get("tags_systeme", []),
            "nb_fragments": nb_fragments,
            "balises": sorted(list(balises))
        }



@app.route("/arch/sauvegarder_fiche", methods=["POST"])
def sauvegarder_fiche():
    try:
        data = request.get_json(force=True)
        texte = data.get("texte", "")
        tags = data.get("tags", [])
        reference = data.get("reference", "")

        if not texte:
            return jsonify({"erreur": "Texte vide"}), 400

        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        titre = f"FICHE_ARCH_{horodatage}.json"

        print("📌 Analyse en cours...")
        analyse = analyse_texte(texte)

        print("📌 Génération des tags système...")
        tags_systeme = générer_tags_systeme(texte)

        print("📌 Fragmentation + Résumé + Balises typologiques...")
        doc = nlp(texte)
        fragments = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]

        # 📌 Résumé + Balises typologiques + Nommage fiche (appel unifié GPT‑4o)
        try:
            print("📌 Appel unifié résumé + balises typologiques + nommage automatique…")
            fragments_clean = fragments
            resume, meta_resume, matrice_cognitive, titre_fiche = generer_resume_et_balises_unifie(fragments_clean)

            if not resume or not matrice_cognitive:
                print("❌ Erreur dans le traitement unifié. Fiche incomplète.")
                return jsonify({"erreur": "Échec du traitement unifié résumé + balises."}), 500

        except Exception as e:
            print("⚠️ Erreur traitement unifié :", str(e))
            return jsonify({"erreur": f"Erreur traitement GPT-4o : {str(e)}"}), 500

        print("📌 Affichage console de la matrice...")
        try:
            afficher_matrice_console(matrice_cognitive)
        except Exception as e:
            print("⚠️ Erreur dans afficher_matrice_console :", str(e))
            print("❌ ERREUR dans /arch/sauvegarder_fiche :", str(e))
            print(traceback.format_exc())
            return jsonify({"erreur": f"Erreur serveur : {str(e)}"}), 500

        print("📌 Construction de la mémoire raisonnée...")
        memo_r = {"fragments": []}
        for fragment in matrice_cognitive:
            fragment_id = fragment.get("id")
            fragment_texte = fragment.get("fragment", "").strip()
            if not fragment_id or not fragment_texte:
                continue

            structurelle = fragment.get("structurelle", []) or []
            conceptuelle = fragment.get("conceptuelle", []) or []
            référentielle = fragment.get("référentielle", []) or []
            vitale = fragment.get("vitale", []) or []
            if isinstance(vitale, str):
                vitale = [vitale]

            balises = structurelle + conceptuelle + référentielle + vitale

            memo_r["fragments"].append({
                "id": fragment_id,
                "texte": fragment_texte,
                "balises": balises,
                "score": fragment.get("score", 0),
                "éléments_visuels": fragment.get("éléments_visuels", ""),
                "justification_balise": fragment.get("justification_balise", ""),
                "structurelle": structurelle,
                "conceptuelle": conceptuelle,
                "référentielle": référentielle,
                "vitale": vitale
            })

try:
    # ... traitement des fragments ...
    memo_r = {"fragments": []}
    for fragment in matrice_cognitive:
        # ...
        memo_r["fragments"].append({...})

except Exception as e:
    print("Erreur lors de la construction de la mémoire raisonnée :", e)
    return jsonify({"erreur": str(e)}), 500

# Partie hors du try : traitement du titre
# 1. On part du titre manuel si présent (prioritaire)
titre_utilisateur = titre.strip()

# 2. Sinon on prend le titre généré par GPT‑4o
titre_final = titre_utilisateur or titre_fiche

# 3. Débogage doublons éventuels (suffixes : (2), (3)...)
titres_existants = [f.get("nommage_fiche", "") for f in fiches if isinstance(f, dict)]

suffixe = ""
n = 2
while titre_final + suffixe in titres_existants:
    suffixe = f" ({n})"
    n += 1
nommage_fiche = titre_final + suffixe
    memo_r["fragments"].append({...})
        fiche = {
            "title": titre,
            "nommage_fiche": nommage_fiche,
            "texte": texte,
            "reference": reference,
            "tags": tags,
            "tags_systeme": tags_systeme,
            "created": horodatage,
            "vitalité": 1.0,
            "statut": "actif",
            "analyse": analyse,
            "matrice_cognitive": matrice_cognitive,
            "memo_r": memo_r,
            "resume": resume,
            "meta_resume": meta_resume
        }

        nom_fichier = os.path.join(DOSSIER_FICHES, titre)
        with open(nom_fichier, "w", encoding="utf-8") as f:
            json.dump(fiche, f, ensure_ascii=False, indent=2)

        print(f"✅ Sauvegarde OK : {titre} — {len(matrice_cognitive)} fragments dans la matrice.")
        return jsonify({
            "message": "Fiche enrichie enregistrée",
            "fichier": nom_fichier,
            "matrice": matrice_cognitive,
            "tag_manuels_fiche": ", ".join(tags)
        })

    except Exception as e:
        print("❌ ERREUR dans /arch/sauvegarder_fiche :", str(e))
        return jsonify({"erreur": f"Erreur serveur : {str(e)}"}), 500


@app.route('/balises/tester', methods=['POST'])
def tester_balises_avance():
    from balises_utils import analyser_texte_en_fragments
    data = request.get_json(force=True)
    texte = data.get("texte", "")

    if not texte.strip():
        return jsonify({"erreur": "Texte vide"}), 400

    fragment = analyser_texte_en_fragments(texte)
    return jsonify(fragment)

@app.route("/arch/generer_resume", methods=["POST"])
def route_generer_resume():
    try:
        data = request.get_json(force=True)
        fiche = data.get("fiche", {})

        
        generer_resume_arch(fiche)

        return jsonify({
            "status": "ok",
            "resume": fiche.get("resume", ""),
            "meta_resume": fiche.get("meta_resume", "")
        })

    except Exception as e:
        return jsonify({"erreur": str(e)}), 500



if __name__ == '__main__':
    try:
        os.makedirs(DOSSIER_FICHES, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Erreur pendant la création du dossier des fiches : {e}")

    print("🧠 Construction du cache mémoire minimale...")
    construire_index_memoire()
    print(f"📦 {len(index_fiches_minimales)} fiches indexées en RAM.")
    
    for nom_fichier, infos in index_fiches_minimales.items():
        print(f"— {nom_fichier} | statut: {infos['statut']}, vitalité: {infos['vitalité']}, "
              f"fragments: {infos['nb_fragments']}, balises: {', '.join(infos['balises'])}")

def detection_trame_possible(matrices, seuil_urgence=3, seuil_rupture=2):
    """
    Détecte une tension cognitive transversale sur plusieurs matrices de fragments.
    matrices = [matrice1, matrice2, ...], chaque matrice = liste de fragments (dict)
    """
    # Fusionne tous les fragments en une seule liste
    fragments = []
    for mat in matrices:
        fragments.extend(mat)

    # Comptage des balises majeures
    compteur = {}
    for frag in fragments:
        for cle in ("structurelle", "conceptuelle", "vitale"):
            val = frag.get(cle)
            if isinstance(val, list):
                for tag in val:
                    compteur[tag] = compteur.get(tag, 0) + 1
            elif isinstance(val, str):
                compteur[val] = compteur.get(val, 0) + 1

    # Détection de sur-représentation
    tensions = []
    if compteur.get("#urgence", 0) >= seuil_urgence:
        tensions.append("Sur-représentation de #urgence")
    if compteur.get("#rupture", 0) >= seuil_rupture:
        tensions.append("Multiples #rupture détectées")
    if compteur.get("#modèle", 0) > 0 and compteur.get("#rupture", 0) > 0:
        tensions.append("Présence simultanée de #modèle et #rupture")

    # Contradiction entre #urgence et #dormance
    if compteur.get("#urgence", 0) > 0 and compteur.get("#dormance", 0) > 0:
        tensions.append("Tension polarité : #urgence vs #dormance")

    # Analyse sommaire des justifications
    contradictions = []
    justifications = [frag.get("justification_balise", "") for frag in fragments if frag.get("justification_balise")]
    for i, justif1 in enumerate(justifications):
        for justif2 in justifications[i+1:]:
            if justif1 and justif2 and (("pas" in justif1 and "mais" in justif2) or ("opposé" in justif1 and "différent" in justif2)):
                contradictions.append((justif1, justif2))

    # Rapport console
    print("\n🕵️‍♂️ Détection de tensions ARCH sur", len(fragments), "fragments :")
    if tensions:
        print("⚡ Tensions détectées :", tensions)
    else:
        print("— Aucune tension typologique majeure détectée.")
    if contradictions:
        print(f"❗ {len(contradictions)} contradictions entre fragments détectées (détail masqué).")

    

    return {"tensions": tensions, "contradictions": contradictions}


@app.route("/test/detection_tension", methods=["GET"])
def test_detection_tension_route():
    from arch_loader import charger_fiche_valide
    from detection_trame_possible import detection_trame_possible

    # 📁 Charge les 2 fiches spécifiques
    chemins = [
        "ARCH_MEMOIRE/fiches/FICHE_ARCH_20250628_214922_453033.json",
        "ARCH_MEMOIRE/fiches/FICHE_ARCH_20250630_115032_938590.json"
    ]
    matrices = [charger_fiche_valide(c) for c in chemins]

    # 🧠 Lance la détection (avec print dans la console)
    resultats = detection_trame_possible(matrices)

    # 🔄 Retourne un résumé JSON dans le navigateur
    return {
        "fragments": sum(len(m) for m in matrices),
        "tensions": resultats["tensions"],
        "nb_contradictions": len(resultats["contradictions"])
    }

@app.route("/arch/detecter_tension_fiches", methods=["POST"])
def detecter_tension_fiches():
    data = request.get_json(force=True)
    noms_fichiers = data.get("noms_fichiers", [])

    if not noms_fichiers or not isinstance(noms_fichiers, list):
        return jsonify({"erreur": "Liste de fichiers manquante ou invalide."}), 400

    matrices = []
    erreurs = []
    for nom in noms_fichiers:
        try:
            fragments = lire_memo_r_depuis_fichier(nom)
            matrices.append(fragments)
        except Exception as e:
            erreurs.append(f"{nom} : {str(e)}")

    if not matrices:
        return jsonify({"erreur": "Aucune matrice valide chargée.", "détails": erreurs}), 400

    # 🧠 Appel à la fonction d’analyse de tension
    resultats = detection_trame_possible(matrices)

    return jsonify({
        "fragments": sum(len(m) for m in matrices),
        "tensions": resultats["tensions"],
        "nb_contradictions": len(resultats["contradictions"]),
        "erreurs": erreurs
    })


if __name__ == "__main__":
    try:
        os.makedirs(DOSSIER_FICHES, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Erreur pendant la création du dossier des fiches : {e}")

    print("🧠 Construction du cache mémoire minimale...")
    construire_index_memoire()
    print(f"📦 {len(index_fiches_minimales)} fiches indexées en RAM.")

    print("🚀 Lancement de l’interface ARCH (Flask)...")
    app.run(debug=True)

 



