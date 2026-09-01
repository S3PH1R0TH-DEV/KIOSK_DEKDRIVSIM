#!/bin/bash
echo "==============================================================="
echo "        DEK-DRIVSIM CYBERCAFE - DEMARRAGE DU SERVEUR           "
echo "==============================================================="
echo ""
echo "Veuillez sélectionner une action :"
echo "1) Lancer le Serveur Unifié (Port 5000)"
echo "2) Lancer la suite de tests de validation"
echo "3) Quitter"
echo ""
read -p "Saisir votre choix (1-3) : " choix

case $choix in
    1)
        echo "Lancement du Serveur Unifié DEK-DRIVSIM..."
        python cybercafe_manager/app.py
        ;;
    2)
        echo "Exécution des tests d'intégration..."
        python test_cybercafe.py
        echo ""
        python test_server_run.py
        ;;
    *)
        echo "Fermeture."
        exit 0
        ;;
esac
