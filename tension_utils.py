
#tension_utils.py
def detection_trame_possible(matrices, seuil_urgence=3, seuil_rupture=2):
    """
    Détecte une tension cognitive transversale sur plusieurs matrices de fragments.
    matrices = [matrice1, matrice2, ...], chaque matrice = liste de fragments (dict)
    """
    fragments = []
    for mat in matrices:
        fragments.extend(mat)

    # Comptage des balises majeures
    compteur = {}
    for frag in fragments:
        for tag in frag.get("structurelle", []) + frag.get("conceptuelle", []) + frag.get("vitale", []):
            compteur[tag] = compteur.get(tag, 0) + 1

    tensions = []
    if compteur.get("#urgence", 0) >= seuil_urgence:
        tensions.append("Sur-représentation de #urgence")
    if compteur.get("#rupture", 0) >= seuil_rupture:
        tensions.append("Multiples #rupture détectées")
    if compteur.get("#modèle", 0) > 0 and compteur.get("#rupture", 0) > 0:
        tensions.append("Présence simultanée de #modèle et #rupture")
    if compteur.get("#urgence", 0) > 0 and compteur.get("#dormance", 0) > 0:
        tensions.append("Tension polarité : #urgence vs #dormance")

    contradictions = []
    justifications = [frag.get("justification_balise", "") for frag in fragments if frag.get("justification_balise")]
    for i, justif1 in enumerate(justifications):
        for justif2 in justifications[i+1:]:
            if justif1 and justif2 and (("pas" in justif1 and "mais" in justif2) or ("opposé" in justif1 and "différent" in justif2)):
                contradictions.append((justif1, justif2))

    print(f"\n📊 Total fragments transmis à l’analyse : {len(fragments)}")
    if compteur:
        print("🧩 Balises rencontrées :", list(compteur.keys()))
    print("\n🕵️‍♂️ Détection de tensions ARCH sur", len(fragments), "fragments :")
    if tensions:
        print("⚡ Tensions détectées :", tensions)
    else:
        print("— Aucune tension typologique majeure détectée.")
    if contradictions:
        print(f"❗ {len(contradictions)} contradictions entre fragments détectées (détail masqué).")

    return {"tensions": tensions, "contradictions": contradictions}
