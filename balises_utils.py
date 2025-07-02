import os
import re
import spacy
import yake
import json
import requests
from termcolor import colored
from dotenv import load_dotenv
# Charger automatiquement la clé depuis un .env local
load_dotenv()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODELES_ARCH = {
    "ARCH_NOTE": "mistral-medium-latest"
}
# Chargement global de spaCy
nlp = spacy.load("fr_core_news_md")



def extraire_json(texte):
    """
    Extrait la première structure JSON valide d’un texte brut (souvent encadrée par ```json ... ``` ou bruitée).
    """
    try:
        # Supprime décorations Markdown éventuelles
        texte = texte.strip()
        if texte.startswith("```json"):
            texte = texte[7:]
        if texte.endswith("```"):
            texte = texte[:-3]
        # Supprime tout avant le premier {
        start = texte.find("{")
        texte = texte[start:]
        return json.loads(texte)
    except Exception as e:
        print("⚠️ Erreur dans extraire_json :", str(e))
        return {}



# Pondérations officielles des balises
PONDERATIONS_BALISES = {
    "#pivot": 2,
    "#conclusion": 2,
    "#détour": 1,
    "#enchaînement": 1,

    "#idée_clé": 3,
    "#rupture": 3,
    "#hypothèse": 2,
    "#modèle": 2,

    "#causalité": 2,
    "#finalité": 2,
    "#temps": 1,
    "#lieu": 1,

    "#émergence": 4,
    "#urgence": 3,
    "#à_relire": 2,
    "#dormance": 1
}

PROMPT_RESUME_ARCH_V1 = """
Tu es un assistant de cognition augmentée.

Tu vas recevoir une fiche textuelle. Elle peut contenir un ou plusieurs paragraphes, ou une suite de fragments discontinus. Ton objectif est double :

1. Produire un **résumé structuré**, fluide et fidèle, entre 400 et 500 tokens mais surtout pas moins.
Ce résumé ne doit pas se contenter de condenser, mais doit restituer l’architecture logique du texte, ses tensions internes (paradoxe, incertitude, opposition, émergence…) et ses enchaînements sémantiques (cause, conséquence, contraste, hypothèse).  
   ➤ S’il y a des contrastes ou des limites dans le propos, formule-les clairement.  
   ➤ Si une idée paraît cruciale ou ambivalente, donne-lui un relief particulier.
   ➤ Fais comme si tu écrivais pour un système de cognition réflexive, et non pour un lecteur humain.
   ➤ N’imite pas mécaniquement les exemples. 
   ➤ Tu peux varier la longueur (jusqu’à 500 tokens) et la tension cognitive selon la complexité du texte. 
   ➤ Si une opposition, une limite ou un paradoxe apparaît, mets-le en valeur.

2. Produire ensuite un **méta-résumé**, en deux lignes maximum. Ce méta-résumé ne doit **jamais redire le résumé**, mais capter la **dynamique de pensée** du texte (polarité, déséquilibre, tension implicite, synthèse incomplète). Il doit être stylisé, mais sobre.

Ta réponse doit être au format JSON strict, comme ceci :
{
  "resume": "…",
  "meta_resume": "…"
}

Langue : français.  
N’utilise jamais de bullet points.  
N’ajoute ni titre, ni commentaire autour du JSON.  


—

À toi maintenant. Voici la fiche à analyser :"
—


"""


PROMPT_UNIFIE_ARCH_V1 = """
Tu es un agent cognitif expert en cognition augmentée.

Tu vas recevoir une fiche déjà fragmentée. Chaque fragment correspond à une unité de sens issue d’une segmentation algorithmique (type YAKE). Tu ne dois pas les modifier, ni les reformuler.

Ta mission est double :

1. Produire un **résumé structuré** fidèle et fluide (400 à 500 tokens, jamais moins). Tu dois reconstituer le fil logique implicite du texte en concaténant mentalement les fragments.  
   ➤ Ce résumé doit refléter les tensions internes (paradoxes, oppositions, contrastes, émergences…).  
   ➤ Il ne doit pas être une simple condensation, mais une **mise en architecture** du propos.  
   ➤ Tu écris pour un système de cognition réflexive. Pas de simplification inutile.  
   ➤ Si une idée est ambivalente, souligne-la. Si une opposition est latente, explicite-la.

2. Produire un **méta-résumé**, en deux lignes maximum.  
   ➤ Il ne doit **jamais répéter le résumé**.  
   ➤ Il doit faire sentir la **dynamique mentale ou la polarité du propos** (instabilité, tension implicite, déséquilibre, esquive…).  
   ➤ Il doit être stylisé, mais sobre.

3. **Attribuer un balisage typologique multistrate** à chaque fragment (sans modifier leur contenu).

Ta réponse finale doit être au **format JSON strict**, structuré ainsi :
{
  "resume": "…",
  "meta_resume": "…",
  "fragments": [
    {
      "fragment_id": "F001",
      "structurelle": "#…",
      "conceptuelle": "#…",
      "référentielle": ["#…"],
      "vitale": "#…",
      "éléments_visuels": "…",
      "justification_balise": "…"
    },
    …
  ]
}

⚠️ Respecte exactement ce format (7 clés pour chaque fragment).  
Langue : français.  
Aucune décoration Markdown. Pas de texte avant ou après le JSON. Pas de commentaire. Aucune bullet point.

—

Voici maintenant les fragments (n’en modifie aucun) :
"""




def générer_tags_systeme(texte):
    mots_cles = ["mémoire", "modèle", "heuristique", "temps", "interaction"]
    return [mot for mot in mots_cles if mot in texte.lower()]

def consolider_tags_groupes(groupes):
    return groupes  # Simulation

def fusionner_tags(tags_manuels, tags_systeme):
    return list(set(tags_manuels)) + [t for t in tags_systeme if t not in tags_manuels]

def extraire_tags_lexicaux(texte, langue="fr", nb_mots_max=5):
    kw_extractor = yake.KeywordExtractor(lan=langue, n=1, top=nb_mots_max)
    mots_cles = kw_extractor.extract_keywords(texte)
    return [mot for mot, score in mots_cles]

def analyser_fragment(fragment, tag_manuels_fiche):
    doc = nlp(fragment)

    verbes = list(set([token.lemma_ for token in doc if token.pos_ == "VERB"]))

    noms_propres = set()
    for ent in doc.ents:
        if ent.label_ == "PER":
            noms_propres.add(ent.text)
    for token in doc:
        if token.pos_ == "PROPN":
            noms_propres.add(token.text)

    tags_lexicaux = extraire_tags_lexicaux(fragment)

    balises_structurelles = ["#pivot"] if "ramassa" in fragment else []
    balises_conceptuelles = ["#idée_clé"] if "chant" in fragment else []
    balises_référentielles = ["#lieu"] if "barricade" in fragment else []
    balises_vitales = ["#émergence"] if "sourire" in fragment else []

    return {
        "fragment": fragment,
        "tags_lexicaux": tags_lexicaux,
        "noms_propres": list(noms_propres),
        "verbes": verbes,
        "structurelle": balises_structurelles,
        "conceptuelle": balises_conceptuelles,
        "référentielle": balises_référentielles,
        "vitale": balises_vitales,
        "tag_manuels_fiche": tag_manuels_fiche
    }

def calculer_score_balises(balises):
    """
    Calcule un score à partir des balises fournies.
    balises = {
        "structurelle": [...],
        "conceptuelle": [...],
        "référentielle": [...],
        "vitale": [...]
    }
    """
    total = 0
    for famille in ["structurelle", "conceptuelle", "référentielle", "vitale"]:
        for tag in balises.get(famille, []):
            total += PONDERATIONS_BALISES.get(tag, 0)
    return total


def generer_matrice_cognitive(texte, tag_manuels_fiche):
    """
    Génère une matrice cognitive multistrate à partir d’un texte brut.
    - Segmente en fragments
    - Extrait : tags lexicaux (YAKE), noms propres, verbes
    - Applique les balises typées
    - Injecte tag_manuels_fiche dans chaque fragment
    """
    doc = nlp(texte)
    matrice = []

    
     #élimination du bruit dans les fragments. Le chiffre donne le nombre de caractères qui donne un fragment exploitable
    fragments = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 10]
    for i, fragment in enumerate(fragments):
        doc_fragment = nlp(fragment)
        id_frag = f"F{i+1:03d}"

        # YAKE
        tags_lexicaux = extraire_tags_lexicaux(fragment)

        # Noms propres (PROPN)
        noms_propres = [token.text for token in doc_fragment if token.pos_ == "PROPN"]

        # Verbes
        verbes = [token.lemma_ for token in doc_fragment if token.pos_ == "VERB"]

        # Score pondéré
        balises_dict = {
            "structurelle": structurelle,
            "conceptuelle": conceptuelle,
            "référentielle": référentielle,
            "vitale": vitale
        }
        score = calculer_score_balises(balises_dict)

        matrice.append({
            "id": id_frag,
            "fragment": fragment,
            "tags_lexicaux": tags_lexicaux,
            "noms_propres": noms_propres,
            "verbes": verbes,
            "structurelle": structurelle,
            "conceptuelle": conceptuelle,
            "référentielle": référentielle,
            "vitale": vitale,
            "tag_manuels_fiche": tag_manuels_fiche,
            "score": score,
            "moteur_utilisé": "GPT‑4.1 Mini (simulé)",
            "niveau_confiance": 0.95,
            "appel_externe_prévu": False,
            "agent_final_suggéré": "Aucun",
            "justification_balise": "",
            "éléments_visuels": []
        })
    
    return matrice


def generer_resume_arch(fiche):
    contenu = fiche.get("texte", "").strip()
    if not contenu:
        raise ValueError("Fiche vide : champ 'texte' introuvable ou vide")

    messages = [
        {
            "role": "user",
            "content": PROMPT_RESUME_ARCH_V1.strip()
        },
        {
            "role": "user",
            "content": contenu
        }
    ]

    try:
        print("🧠 Appel principal : GPT-4o pour résumé structuré...")
        result = appel_gpt4o(messages)
        print("🧾 [DEBUG] Résultat LLM avant parsing :", repr(result))

        # --- Nettoyage Markdown éventuel avant parsing JSON ---
        if result.strip().startswith("```json"):
            result = result.strip()[7:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()
        elif result.strip().startswith("```"):
            result = result.strip()[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

        try:
            resume_data = json.loads(result)
        except Exception as err_json:
            print("❌ Erreur parsing JSON (GPT-4o résumé) :", err_json)
            print("🧾 Réponse brute :", result)
            raise RuntimeError(f"Erreur parsing JSON résumé (GPT-4o) : {err_json}")

        fiche["resume"] = resume_data.get("resume", "")
        fiche["meta_resume"] = resume_data.get("meta_resume", "")
        fiche["moteur_resume"] = "GPT‑4o"

    except Exception as e:
        print("⚠️ Erreur GPT‑4o, fallback Mistral activé :", str(e))
        try:
            resume_data = generer_resume_mistral(contenu)
            fiche["resume"] = resume_data.get("resume", "")
            fiche["meta_resume"] = resume_data.get("meta_resume", "")
            fiche["moteur_resume"] = "Mistral"
        except Exception as e2:
            print("❌ Erreur fallback Mistral :", str(e2))
            fiche["resume"] = "Erreur lors du résumé."
            fiche["meta_resume"] = "N/A"
            fiche["moteur_resume"] = "Erreur"
  # ➡️ AJOUTE cette ligne à la toute fin :
    return fiche

def generer_resume_mistral(contenu):
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [
        {
            "role": "user",
            "content": PROMPT_RESUME_ARCH_V1.strip()
        },
        {
            "role": "user",
            "content": contenu
        }
    ]

    data = {
        "model": "mistral-medium-latest",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1500,
        "top_p": 1.0
    }

    response = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    result_json = response.json()
    resume_data_str = result_json["choices"][0]["message"]["content"]
    print("🧾 [DEBUG] Résultat Mistral avant parsing :", repr(resume_data_str))

    # Ajout du parsing robuste :
    try:
        resume_data = json.loads(resume_data_str)
    except Exception as err_json:
        print("❌ Erreur parsing JSON (Mistral résumé) :", err_json)
        print("🧾 Réponse brute :", resume_data_str)
        raise RuntimeError(f"Erreur parsing JSON résumé (Mistral) : {err_json}")
    return resume_data

def generer_balises_mistral(fragments):
    """
    Envoie une liste de fragments textuels à Mistral pour générer un balisage typologique structuré.
    Retourne une liste de dictionnaires avec 7 clés par fragment.
    """
    import os
    import json
    import requests

    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
    if not MISTRAL_API_KEY:
        raise RuntimeError("Clé API Mistral manquante")

    if not fragments:
        return []

    prompt_instructions = """
Tu es un agent cognitif expert en analyse textuelle.
Ta mission est d’analyser chaque fragment reçu et d’attribuer un balisage multistrate dans un format JSON strictement normé.

Ta réponse doit être une liste JSON (array), contenant un objet par fragment avec exactement 7 clés dans l’ordre suivant :

1. "fragment_id" : Code identifiant du fragment (ex. "F001", "F002", etc.).
2. "structurelle" : Une balise parmi : #introduction, #enchaînement, #pivot, #détour, #conclusion, #fragment_incomplet.
3. "conceptuelle" : Une balise parmi : #idée_clé, #modèle, #hypothèse, #description, #événement, #rupture, #néant.
4. "référentielle" : Liste de balises parmi : #temps, #lieu, #causalité (peut être vide).
5. "vitale" : Une balise parmi : #urgence, #émergence, #dormance.
6. "éléments_visuels" : Métaphore ou image stylisée représentant le fragment.
7. "justification_balise" : 2 à 3 lignes justifiant les choix précédents.

Langue : français.
Format de sortie : JSON strict sans titre ni décor.

Voici les fragments à analyser :
""".strip()

    texte_fragments = "\n".join([f'{i+1}. {frag}' for i, frag in enumerate(fragments)])

    messages = [
        {"role": "user", "content": prompt_instructions},
        {"role": "user", "content": texte_fragments}
    ]

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "mistral-medium",
        "temperature": 0.2,
        "messages": messages
    }

    try:
        response = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"]

        # Nettoyage des balises markdown éventuelles
        if result.strip().startswith("```json"):
            result = result.strip()[7:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()
        elif result.strip().startswith("```"):
            result = result.strip()[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

        print("🧾 Réponse Mistral (nettoyée) :", result)
        print("🧾 [DEBUG] Résultat balises Mistral avant parsing :", repr(result))

        try:
            balises_mistral = json.loads(result)
        except Exception as err_json:
            print("❌ Erreur parsing JSON (Mistral balises) :", err_json)
            print("🧾 Réponse brute :", result)
            raise RuntimeError(f"Erreur parsing JSON balises typologiques (Mistral) : {err_json}")

        return balises_mistral

    except Exception as e:
        print("❌ Erreur appel Mistral balises :", e)
        raise


def generer_resume_et_balises_unifie(fragments):
    """
    Envoie les fragments à GPT‑4o dans un seul appel unifié (résumé structuré + balises typologiques).
    Retourne : (resume, meta_resume, liste_balises)
    """

    prompt = [
        {"role": "user", "content": PROMPT_UNIFIE_ARCH_V1.strip()},
        {"role": "user", "content": json.dumps(fragments, ensure_ascii=False, indent=2)}
    ]

    try:
        print("📌 Appel GPT‑4o unifié (résumé + balises typologiques)…")
        resultat = appel_gpt4o(prompt, max_tokens=4000)
        print("📥 Réponse reçue ✅")
    except Exception as e:
        print(f"⚠️ GPT‑4o indisponible, bascule vers Mistral… ({e})")
        try:
            resultat = appel_mistral(prompt, max_tokens=4000)
        except Exception as fallback_e:
            print(f"❌ Échec Mistral également : {fallback_e}")
            return None, None, []

    try:
        # Adaptatif selon le type de retour (dict déjà parsé ou string à parser)
        if isinstance(resultat, dict):
            data = resultat
        else:
            data = extraire_json(resultat)

        resume = data.get("resume", "").strip()
        meta_resume = data.get("meta_resume", "").strip()
        fragments_balises = data.get("fragments", [])
        titre_fiche = data.get("titre_fiche", "").strip()
        return resume, meta_resume, fragments_balises, titre_fiche
        


    except Exception as parse_error:
        print(f"❌ Erreur de parsing JSON unifié : {parse_error}")
        return None, None, []


def afficher_matrice_console(matrice):
    """
    Affiche proprement une matrice cognitive avec couleurs selon les balises.
    """
    print("\n🧠 MATRICE COGNITIVE – AFFICHAGE CONSOLE")
    for fragment in matrice:
        id_frag = fragment.get("id", "???")
        texte = fragment.get("fragment", "").strip()
        if not texte:
            continue

        print(f"\n🔹 fragment {id_frag} : {colored(texte, 'cyan')}")
        
        tags_struct = ", ".join(fragment.get("structurelle", []))
        tags_concept = ", ".join(fragment.get("conceptuelle", []))
        tags_ref = ", ".join(fragment.get("référentielle", []))
        tags_vie = ", ".join(fragment.get("vitale", []))

        if tags_struct:
            print(colored(f"🟠 Structurelle : {tags_struct}", 'yellow'))
        if tags_concept:
            print(colored(f"🔵 Conceptuelle : {tags_concept}", 'blue'))
        if tags_ref:
            print(colored(f"🟣 Référentielle : {tags_ref}", 'magenta'))
        if tags_vie:
            print(colored(f"🔴 Vitale : {tags_vie}", 'red'))

        # Score en gris clair
        score = fragment.get("score", 0)
        print(colored(f"Score heuristique : {score}", 'white'))

def explorer_matrice_console(matrice, score_min=None, tag_contenu=None, afficher_tout=False):
    """
    Exploration console ciblée de la matrice cognitive.
    - score_min : n'affiche que les fragments avec score ≥ score_min
    - tag_contenu : n'affiche que les fragments contenant ce tag (dans structurelle, conceptuelle, référentielle ou vitale)
    - afficher_tout : ignore tous les filtres
    """
    print("\n🔍 EXPLORATION DE LA MATRICE COGNITIVE\n")

    nb = 0
    for fragment in matrice:
        texte = fragment.get("fragment", "").strip()
        score = fragment.get("score", 0)
        id_frag = fragment.get("id", "??")

        tous_les_tags = fragment.get("structurelle", []) + fragment.get("conceptuelle", []) + fragment.get("référentielle", []) + fragment.get("vitale", [])

        if afficher_tout:
            pass
        elif tag_contenu:
            if tag_contenu not in tous_les_tags:
                continue
        elif score < score_min:
            continue

        print(f"🧩 fragment {id_frag} – Score : {score}")
        print(f"✏️  {texte}")
        if tous_les_tags:
            print(f"🏷️ Tags : {', '.join(tous_les_tags)}")
        print()
        nb += 1

    print(f"✅ {nb} fragment(s) affiché(s)\n")


def appel_gpt4o(messages, model="gpt-4o", temperature=0.4, max_tokens=600):
    url = "https://api.openai.com/v1/chat/completions"
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    # Affichage debug pour voir le JSON envoyé
    print("📤 Envoi à OpenAI :\n", json.dumps(data, indent=2, ensure_ascii=False))

    try:
        response = requests.post(url, headers=headers, json=data, timeout=40)
        print("📥 Statut HTTP :", response.status_code)
        print("📥 Réponse brute :", response.text[:500])

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI HTTP {response.status_code} : {response.text}")

        # Vérification : la réponse doit être un vrai JSON
        try:
            reponse_json = response.json()
        except Exception as e:
            print("❌ Erreur parsing JSON :", e)
            print("🧾 Réponse brute :", response.text)
            raise RuntimeError(f"Erreur parsing JSON : {e}")

        # Vérification : la clé attendue existe
        if ("choices" not in reponse_json or
            not isinstance(reponse_json["choices"], list) or
            "message" not in reponse_json["choices"][0] or
            "content" not in reponse_json["choices"][0]["message"]):
            raise RuntimeError(f"Réponse inattendue de OpenAI : {response.text}")

        return reponse_json["choices"][0]["message"]["content"]

    except Exception as e:
        print("❌ Exception lors de l'appel GPT‑4o :", str(e))
        raise RuntimeError(f"Erreur appel OpenAI GPT-4o : {e}")

def generer_balises_typologiques(fragments):
    """
    Applique GPT‑4o pour extraire les balises typologiques de chaque fragment.
    Fallback Mistral si l’appel échoue.
    """
    import json
    fragments_clean = [
        {"id": f"F{i+1:03d}", "contenu": frag.strip()}
        for i, frag in enumerate(fragments)
        if frag.strip()
    ]

    instruction = """
Tu es un agent cognitif expert en analyse textuelle.
Ta mission est d’analyser chaque fragment reçu et d’attribuer un balisage multistrate dans un format JSON strictement normé.

Ta réponse doit être une liste JSON (array), contenant un objet par fragment avec exactement 7 clés dans l’ordre suivant :

1. "fragment_id" : Code identifiant du fragment (ex. "F001", "F002", etc.).
2. "structurelle" : Une balise parmi : #introduction, #enchaînement, #pivot, #détour, #conclusion, #fragment_incomplet.
3. "conceptuelle" : Une balise parmi : #idée_clé, #modèle, #hypothèse, #description, #événement, #rupture, #néant.
4. "référentielle" : Liste de balises parmi : #temps, #lieu, #causalité (peut être vide).
5. "vitale" : Une balise parmi : #urgence, #émergence, #dormance.
6. "éléments_visuels" : Métaphore ou image stylisée représentant le fragment.
7. "justification_balise" : 2 à 3 lignes justifiant les choix précédents.

Langue : français.
Format de sortie : JSON strict sans titre ni décor.
"""

    prompt = [
        {"role": "user", "content": instruction},
        {"role": "user", "content": json.dumps(fragments_clean, ensure_ascii=False, indent=2)}
    ]

    try:
        print("🔍 Appel GPT‑4o pour balises typologiques…")
        result = appel_gpt4o(prompt, max_tokens=3000)

        # --- Nettoyage éventuel des balises markdown
        if result.strip().startswith("```json"):
            result = result.strip()[7:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()
        elif result.strip().startswith("```"):
            result = result.strip()[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()

        print("🧾 [DEBUG] Résultat balises LLM avant parsing :", repr(result))
        try:
            fragments_annotes = json.loads(result)
        except Exception as err_json:
            print("❌ Erreur parsing JSON (GPT-4o balises) :", err_json)
            print("🧾 Réponse brute :", result)
            raise RuntimeError(f"Erreur parsing JSON balises typologiques (GPT-4o) : {err_json}")

        # Format standard
        matrice = []
        for i, original in enumerate(fragments_clean):
            balises = fragments_annotes[i] if i < len(fragments_annotes) else {}

            structurelle = [balises.get("structurelle")] if balises.get("structurelle") else []
            conceptuelle = [balises.get("conceptuelle")] if balises.get("conceptuelle") else []
            référentielle = balises.get("référentielle", [])
            vitale = [balises.get("vitale")] if balises.get("vitale") else []

            score = calculer_score_balises({
                "structurelle": structurelle,
                "conceptuelle": conceptuelle,
                "référentielle": référentielle,
                "vitale": vitale
            })

            matrice.append({
                "id": original["id"],
                "fragment": original["contenu"],
                "structurelle": structurelle,
                "conceptuelle": conceptuelle,
                "référentielle": référentielle,
                "vitale": vitale,
                "éléments_visuels": balises.get("éléments_visuels", ""),
                "justification_balise": balises.get("justification_balise", ""),
                "score": score,
                "moteur_utilisé": "GPT‑4o",
                "balises": balises
            })

        return matrice

    except Exception as e:
        print("⚠️ Erreur GPT‑4o pour balises typologiques :", str(e))
        print("🔁 Fallback Mistral activé.")
        return generer_balises_mistral([frag["contenu"] for frag in fragments_clean])


    except Exception as e:
        print("⚠️ Erreur GPT‑4o pour balises typologiques :", str(e))
        print("🔁 Fallback Mistral activé.")
        return generer_balises_mistral([frag["contenu"] for frag in fragments_clean])

def charger_fiche_json(nom_fichier):
    """
    Charge une fiche ARCH à partir d'un nom de fichier JSON.
    Retourne la matrice cognitive (champ "memo_r") ou une liste vide si erreur.
    """
    import os
    import json
    chemin = os.path.join("fiches", nom_fichier)
    if not os.path.exists(chemin):
        print(f"❌ Fichier introuvable : {chemin}")
        return []

    try:
        with open(chemin, "r", encoding="utf-8") as f:
            fiche = json.load(f)
        return fiche.get("memo_r", [])
    except Exception as e:
        print(f"❌ Erreur de chargement JSON : {e}")
        return []

