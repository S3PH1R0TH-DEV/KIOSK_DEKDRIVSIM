#!/bin/bash
echo "==============================================================="
echo "       DEK-DRIVSIM CYBERCAFE - ARRÊT DU SERVEUR (TERMUX)       "
echo "==============================================================="
echo ""

SERVER_STOPPED=false

# 1. Tentative d'arrêt via le fichier PID enregistré
if [ -f server.pid ]; then
    PID=$(cat server.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "Fermeture du serveur persistant via PID (PID: $PID)..."
        kill -9 $PID
        SERVER_STOPPED=true
    fi
    rm -f server.pid
fi

# 2. Sécurité de rechange : Recherche et arrêt de tout processus python sur app.py
# (Fonctionne même si lsof ou le fichier PID sont absents)
if [ "$SERVER_STOPPED" = false ]; then
    echo "Recherche de processus persistants en cours..."
    pkill -9 -f "python.*app.py" &>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Processus python app.py identifié et arrêté avec succès."
        SERVER_STOPPED=true
    else
        echo "❌ Aucun serveur actif détecté sur le port 5000."
    fi
else
    # S'assure que tout résidu est nettoyé
    pkill -9 -f "python.*app.py" &>/dev/null
fi

# 3. Relâche le WakeLock d'Android pour économiser la batterie du téléphone
if [ "$SERVER_STOPPED" = true ]; then
    if command -v termux-wake-unlock &> /dev/null; then
        termux-wake-unlock
        echo "WakeLock Android relâché (Économie d'énergie active)."
    fi
    echo "✅ Le serveur de votre cybercafé a été arrêté proprement."
fi

echo "==============================================================="
