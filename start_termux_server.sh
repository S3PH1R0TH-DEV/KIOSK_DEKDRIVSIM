#!/bin/bash
echo "==============================================================="
echo "       DEK-DRIVSIM CYBERCAFE - DEMARRAGE INVIOLABLE (TERMUX)   "
echo "==============================================================="
echo ""

# 1. Demande à Android de NE JAMAIS mettre en veille Termux (WakeLock)
echo "1. Demande d'interdiction de mise en veille (WakeLock Android)..."
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock
    echo "   ✅ WakeLock activé avec succès."
else
    echo "   ⚠️ Outil termux-wake-lock absent, ignore."
fi

# 2. Vérifie si une instance tourne déjà et la ferme proprement
echo "2. Nettoyage des anciennes instances..."
if [ -f server.pid ]; then
    OLD_PID=$(cat server.pid)
    if kill -0 $OLD_PID 2>/dev/null; then
        echo "   ⚠️ Ancienne instance détectée (PID: $OLD_PID). Fermeture..."
        kill -9 $OLD_PID
    fi
    rm -f server.pid
fi

# Tente également de tuer tout processus python restant sur app.py au cas où
pkill -f "python.*app.py" &>/dev/null
sleep 1

# 3. Lancement du serveur en tâche de fond ultra-persistante (nohup)
echo "3. Lancement du Serveur Unifié en arrière-plan persistant (nohup)..."
nohup python cybercafe_manager/app.py > server_termux.log 2>&1 &

# Récupère instantanément le Process ID (PID) de la tâche d'arrière-plan
NEW_PID=$!

# Enregistre de manière permanente le PID dans un fichier
echo $NEW_PID > server.pid

sleep 2

# Vérifie si le processus tourne toujours
if kill -0 $NEW_PID 2>/dev/null; then
    echo "   ✅ Serveur démarré avec succès en tâche de fond (PID: $NEW_PID)."
    echo ""
    echo "==============================================================="
    echo "🔥 VOTRE SERVEUR EST DESORMAIS INCASSABLE ET ACTIF EN ARRIERE-PLAN !"
    echo "Vous pouvez fermer cette fenêtre Termux ou verrouiller votre téléphone."
    echo "Le serveur continuera de fonctionner en tâche de fond sans jamais couper."
    echo "==============================================================="
    echo ""
    echo "👉 Pour administrer votre salle depuis CE TÉLÉPHONE :"
    echo "   Ouvrez Chrome et allez sur : http://127.0.0.1:5000/admin"
    echo ""
    echo "👉 Pour arrêter proprement le serveur arrière-plan, lancez :"
    echo "   ./stop_termux_server.sh"
    echo "==============================================================="
else
    echo "   ❌ Échec du démarrage du serveur. Consultez le fichier 'server_termux.log' pour voir l'erreur."
fi
