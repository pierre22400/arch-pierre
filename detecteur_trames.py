#detecteur_trames.py
from arch import detection_trame_possible
from arch_loader import charger_toutes_fiches

# 📍 Spécifie ici le chemin du dossier contenant les fiches ARCH
DOSSIER = r"C:\Users\DENIS\Documents\Recherches\ARCH\ARCH_MEMOIRE\fiches"

# 📦 Chargement de toutes les matrices valides du dossier
matrices = charger_toutes_fiches(DOSSIER)

# 🧠 Lancement de la détection (seulement si au moins 2 fiches)
if len(matrices) >= 2:
    print(f"🗂️  {len(matrices)} matrices de fragments chargées, lancement de la détection des tensions…\n")
    detection_trame_possible(matrices)
else:
    print("⚠️  Pas assez de fiches valides pour détecter une tension.")
