@echo off
title ARCH - Lancement Complet
cd /d %~dp0

REM ✅ Lancement du serveur Flask
start "ARCH Serveur" python arch.py

REM ✅ Lancement de l’analyse de tensions (optionnel)
REM start "ARCH Tensions" python detecteur_trames.py

REM ✅ Ouverture de l’interface HTML (optionnel)
REM start "" "bbgpt_ui_typo_chatgpt.html"



