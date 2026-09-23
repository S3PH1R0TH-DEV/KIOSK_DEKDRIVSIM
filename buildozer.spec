# =============================================================================
# DEK-DRIVSIM CyberCafe - Configuration Buildozer
# Toutes les clés ci-dessous existent réellement dans buildozer : une clé
# inconnue est ignorée SANS erreur ni avertissement, ce qui donne l'illusion
# d'une option active alors qu'elle n'a aucun effet sur l'APK produit.
# =============================================================================

[app]

# (str) Titre de votre application mobile
title = DEK-DRIVSIM

# (str) Nom du paquet système (sans espaces ni caractères spéciaux)
package.name = dekdrivsim

# (str) Domaine unique du paquet
package.domain = org.dekdrivsim

# (str) Dossier racine contenant le fichier "main.py"
source.dir = .

# (list) Extensions de fichiers à inclure lors du packaging
# woff2/ttf sont indispensables : sans eux les polices Font Awesome vendorisées
# ne sont pas embarquées et toutes les icônes de l'interface disparaissent.
source.include_exts = py,png,jpg,jpeg,html,js,css,db,xml,svg,ico,ttf,woff,woff2

# (list) Dossiers à exclure du packaging (poids inutile dans l'APK)
# p4a-recipes est de l'outillage de compilation, pas du code applicatif.
# android_assets ne sert qu'à buildozer (icône/presplash, lus directement via
# icon.filename et presplash.filename) : l'embarquer en plus dans l'app
# dupliquerait 1,9 Mo pour rien.
source.exclude_dirs = bin,.buildozer,uploads,__pycache__,certs,p4a-recipes,android_assets,dek-drivsim-pc,docs,scripts,.github

# (list) Fichiers à exclure
# presplash.png n'est référencé par aucun template : il ne sert que d'écran de
# démarrage, déjà fourni en version optimisée via android_assets/.
# dek_client_agent.py est l'agent kiosque Windows (ctypes/winreg) : aucune
# utilité embarqué dans l'APK Android.
source.exclude_patterns = test_*.py,*.sh,*.spec.template,README.md,cybercafe_manager/static/images/presplash.png,dek_client_agent.py

# (str) Version de l'application
version = 2.5

# =============================================================================
# ICONE ET ECRAN DE DEMARRAGE
# =============================================================================

icon.filename = %(source.dir)s/android_assets/icon.png
presplash.filename = %(source.dir)s/android_assets/presplash.png
android.presplash_color = #04050a

# =============================================================================
# DEPENDANCES
# =============================================================================

# Flask via p4a : on liste explicitement ses deps pure-python (pip) + markupsafe via recette locale
# sqlite3 est stdlib (pas pip) et blinker est optionnel (retire pour eviter conflit pip --platform android)
requirements = python3,kivy,pyjnius,android,setuptools,flask,jinja2,werkzeug,markupsafe,itsdangerous,click

orientation = portrait
fullscreen = 1

# =============================================================================
# PARAMETRES ANDROID
# =============================================================================

# Permissions déclarées dans le manifeste. Elles doivent couvrir tout ce que
# le code demande à l'exécution, sinon la demande est refusée d'office.
android.permissions = android.permission.INTERNET,android.permission.ACCESS_NETWORK_STATE,android.permission.ACCESS_WIFI_STATE,android.permission.WAKE_LOCK

# Maintient l'appareil éveillé pendant que le serveur tourne (ajoute WAKE_LOCK).
android.wakelock = True

# --- AUTORISATION DU TRAFIC HTTP EN CLAIR ---
# DESACTIVE (buildozer 1.5.0) : android.py fait
#   open(f).read().replace('"', '\\"') puis '--extra-manifest-application-arguments="{...}"'
# et Popen(liste) sans shell -> p4a injecte litteralement
#   "android:usesCleartextTraffic=\"true\"" dans AndroidManifest.xml => MergeFailureException.
# (Prouve par diagnostic CI 09/2026 sur dists/*/src/main/AndroidManifest.xml.)
# Contournement : cleartext injecte directement dans le template p4a en CI
# (patch _sdl_common/build/templates/AndroidManifest.tmpl.xml, voir workflow).
# usesCleartextTraffic=true seul autorise deja tout le HTTP local (WebView 127.0.0.1 + LAN),
# network_security_config.xml devient inutile. Fichiers gardes pour historique.
# android.res_xml = %(source.dir)s/network_security_config.xml
# android.extra_manifest_application_arguments = %(source.dir)s/manifest_application_args.xml

# (int) Version d'API Android cible pour la compilation (Android 14)
android.api = 34

# (int) Version d'API Android minimale supportée (Android 5.0 Lollipop)
android.minapi = 21

# (list) Architectures ciblées. Sans cette clé la valeur par défaut dépend de
# la version de buildozer installée : on la fige pour un résultat reproductible.
android.archs = arm64-v8a,armeabi-v7a

# (bool) Sauvegarde automatique des données de l'app
android.allow_backup = True

# (bool) Accepte automatiquement la licence du SDK Android de Google.
# Sans cette clé, le téléchargement des build-tools est refusé en mode
# non-interactif et la compilation s'arrête sur "Aidl not found".
android.accept_sdk_license = True

# =============================================================================
# OPTIONS DE COMPILATION
# =============================================================================

# (str) Dossier de recettes locales python-for-android.
# Contient la recette markupsafe : sans elle, p4a tente de récupérer un wheel
# Android pour ce paquet compilé, qui n'existe pas sur PyPI, et la
# compilation s'arrête sur "No matching distribution found for markupsafe".
p4a.local_recipes = %(source.dir)s/p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 0
