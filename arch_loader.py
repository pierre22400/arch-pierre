import json
import os

def extraire_fragments(fiche):
    """
    Récupère la liste de fragments depuis tous les champs classiques ARCH.
    Rend le code de détection robuste à toutes les variantes de structure JSON.
    """
    for cle in ("matrice_cognitive", "memo_r", "fragments"):
        val = fiche.get(cle, None)
        if val is None:
            continue
        if isinstance(val, list):
            return val
        if isinstance(val, dict) and isinstance(val.get("fragments"), list):
            return val["fragments"]
    return []

def charger_fiche_valide(chemin_complet):
    """
    Charge n'importe quelle fiche ARCH (quelle que soit sa structure),
    et retourne la liste des fragments utilisable directement dans le pipeline de détection.
    """
    try:
        with open(chemin_complet, "r", encoding="utf-8") as f:
            fiche = json.load(f)
        fragments = extraire_fragments(fiche)
        if not isinstance(fragments, list):
            print(f"❌ Structure inattendue dans : {chemin_complet}")
            return []
        return fragments
    except Exception as e:
        print(f"❌ Erreur de chargement : {e}")
        return []


def charger_toutes_fiches(dossier_fiches):
    """
    Parcourt le dossier donné et charge tous les fichiers JSON valides en tant que matrices de fragments.
    """
    matrices = []
    fichiers = [f for f in os.listdir(dossier_fiches) if f.endswith(".json")]
    print(f"📂 {len(fichiers)} fiches trouvées dans : {dossier_fiches}")
    for nom_fichier in fichiers:
        chemin = os.path.join(dossier_fiches, nom_fichier)
        fragments = charger_fiche_valide(chemin)
        if fragments:
            matrices.append(fragments)
    return matrices

