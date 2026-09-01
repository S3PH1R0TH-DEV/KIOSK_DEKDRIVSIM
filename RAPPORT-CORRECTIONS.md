# DEK-DRIVSIM — Rapport de correction

**Date :** 11 août 2026 · **Version produite :** 2.5
**Livrable :** `bin/DEK-DRIVSIM-2.5.apk` — 46,8 Mo, `arm64-v8a` + `armeabi-v7a`, Android 5.0+

---

## En deux phrases

Le projet ne compilait pas, et même compilé il n'aurait pas démarré : cinq défauts
indépendants se cumulaient, dont trois qui rendaient l'application inutilisable dès
le lancement. Tout est corrigé, l'APK a été compilé puis **réellement testé sur
Android** (installation, lancement, activation, navigation dans la console admin).

L'application ne demande plus aucune connexion Internet pour fonctionner.

---

## Ce qui ne marchait pas, et pourquoi

Les cinq points ci-dessous sont indépendants. Corriger un seul n'aurait rien changé :
le suivant aurait bloqué juste après.

### 1. La base de données n'était jamais créée

`init_db()` était écrite, complète et correcte… mais **jamais appelée**. Nulle part
dans le code applicatif, uniquement dans les tests.

Sur PC ça ne se voyait pas : le fichier `cybercafe_manager/cybercafe.db` existait déjà
dans le dépôt, avec ses tables. Sur Android, `app.py` redirige la base vers le dossier
privé de l'application (le seul emplacement où Android autorise l'écriture) — et ce
`cybercafe.db` livré dans les sources n'y est **jamais recopié**. La base y démarrait
donc systématiquement vide, et la première page demandée plantait :

```
sqlite3.OperationalError: no such table: device_roles
```

**Correctif :** `init_db()` est appelée à l'import du module. Elle est idempotente
(`CREATE TABLE IF NOT EXISTS`), donc sans effet sur une base déjà remplie.

### 2. La WebView ne pouvait pas se construire

Le code créait un `WebViewClient` personnalisé pour ignorer les erreurs de certificat :

```python
class CustomWebViewClient(PythonJavaClass):
    __javaclass__ = 'android/webkit/WebViewClient'
```

Cette construction ne peut pas fonctionner. `PythonJavaClass` s'appuie sur
`java.lang.reflect.Proxy`, qui ne sait proxifier que des **interfaces** — la
documentation de pyjnius est explicite : *« You can only implement Java interfaces.
You cannot sub-class a java object. »* Or `WebViewClient` est une classe. L'attribut
attendu est par ailleurs `__javainterfaces__`, pas `__javaclass__`.

Résultat : exception au `setWebViewClient()`, et écran noir.

**Correctif :** ce client sur-mesure servait uniquement à contourner le certificat
auto-signé. En repassant en HTTP local (voir §4), il n'a plus de raison d'être : un
`WebViewClient` standard suffit, et il s'instancie directement.

### 3. Deux dépendances Python manquaient

`requirements` listait `flask, jinja2, werkzeug, itsdangerous, blinker` mais pas
`click` ni `markupsafe`. La recette Flask de python-for-android **n'installe pas** ses
propres dépendances, elle se contente de les déclarer. Sans elles, `import flask` lève
`ModuleNotFoundError` et le serveur ne démarre jamais.

**Correctif :** les deux paquets ont été ajoutés. `markupsafe` a demandé un travail
supplémentaire (voir « Chaîne de compilation » plus bas).

### 4. Quatre options de `buildozer.spec` n'existaient pas

C'est le point le plus sournois. **Buildozer ignore silencieusement une clé qu'il ne
connaît pas** : aucune erreur, aucun avertissement. Ces quatre lignes, présentées dans
le fichier comme « inviolables », n'avaient donc strictement aucun effet :

| Clé utilisée | Réalité |
|---|---|
| `android.manifest.application_attributes` | n'existe pas |
| `android.manifest.attributes` | n'existe pas |
| `android.network_security_config` | n'existe pas |
| `android.foreground_service` | n'existe pas |

Vérifié directement dans le code source de buildozer 1.6.1. Conséquence : l'APK ne
contenait ni `usesCleartextTraffic`, ni configuration réseau — exactement ce que ces
lignes étaient censées garantir.

**Correctif :** les vraies clés équivalentes.

```ini
android.res_xml = %(source.dir)s/network_security_config.xml
android.extra_manifest_application_arguments = %(source.dir)s/manifest_application_args.xml
```

La première copie le XML dans `res/xml/`, la seconde injecte les attributs
correspondants dans la balise `<application>` du manifeste. C'est vérifiable dans
l'APK produit :

```
android:usesCleartextTraffic=true
android:networkSecurityConfig=@0x7f070000  →  res/xml/network_security_config.xml
```

### 5. Appel JNI depuis le mauvais thread

Ce défaut-ci n'était visible qu'à l'exécution, sur un vrai Android. Une fois tout le
reste corrigé, Flask démarrait bien mais la WebView échouait :

```
JavaException: ClassNotFoundException: org.jnius.NativeInvocationHandler
   DexPathList[[directory "."], nativeLibraryDirectories=[/system/lib64, ...]]
```

`run_on_ui_thread` construit lui-même un proxy Java. Appelé depuis un thread créé par
`threading.Thread`, ce thread est attaché à la JVM avec le **classloader système**, qui
n'a pas accès au code de l'application — d'où le `DexPathList` vide.

**Correctif :** un `@mainthread` fait repasser par le thread principal Kivy, créé côté
Java et porteur du bon classloader, avant tout appel JNI.

---

## Chaîne de compilation : deux blocages supplémentaires

Ces deux-là ne sont pas des défauts du projet, mais des limites de
python-for-android qu'il fallait franchir.

**`markupsafe` n'a aucun wheel Android.** C'est le seul paquet compilé de la chaîne
Flask (extension C `_speedups`). p4a essaie de le récupérer sous forme de wheel
précompilé pour Android — qui n'existe pas sur PyPI, et aucune version n'en propose de
version universelle. La recette locale `p4a-recipes/markupsafe/` le fait construire
depuis les sources avec le NDK. Il compile même son extension C native.

**La recette Flask entrait en conflit.** Elle déclare `markupsafe` dans
`python_depends`, ce qui le range côté pip. Lui donner une recette le rangeait aussi
côté compilation, et p4a exige que ces deux ensembles soient disjoints :

```python
assert set(build_order).intersection(set(python_modules)) == set()   # AssertionError
```

La surcharge locale `p4a-recipes/flask/` déplace `markupsafe` de `python_depends` vers
`depends`. Il reste construit avant Flask, mais du bon côté.

---

## Ce qui a changé dans le fonctionnement

### HTTPS local abandonné au profit de HTTP

L'ancienne version servait Flask en HTTPS avec un certificat auto-signé. Android
refuse ces certificats dans une WebView, et le seul moyen de passer outre aurait été
le `WebViewClient` sur-mesure — impossible (§2). Le serveur écoute donc en clair, sur
`127.0.0.1`, et le trafic est autorisé par le `network_security_config` désormais
réellement appliqué.

Ce n'est pas un recul de sécurité : le certificat était auto-signé, donc non vérifié,
et le trafic ne quitte pas l'appareil.

Le dossier `cybercafe_manager/certs/` n'est plus utilisé. **Tu peux le supprimer** —
il contient une clé privée devenue inutile. Elle est déjà exclue de l'APK.

### Le serveur écoute sur tout le réseau local

`0.0.0.0:5000` au lieu de `127.0.0.1:5000`. La WebView du téléphone continue de passer
par `127.0.0.1`, mais les postes clients du cybercafé peuvent maintenant atteindre le
serveur via `http://<IP-du-téléphone>:5000`. C'était nécessaire pour que
`dek_client_agent.py` serve à quelque chose.

Effet de bord utile : chaque poste arrivant avec sa propre adresse IP, le système de
rôles par IP fonctionne comme prévu.

### L'interface fonctionne sans Internet

Les sept templates chargeaient Tailwind, Font Awesome et trois images depuis des CDN.
Sans connexion, la console s'affichait sans aucun style — problématique pour un
cybercafé. Tout est désormais embarqué dans `static/vendor/` et `static/images/bg/`.

Une trace subsiste dans la console du navigateur : *« cdn.tailwindcss.com should not be
used in production »*. C'est un avertissement du moteur Tailwind, sans effet sur le
fonctionnement. Pour le supprimer il faudrait générer un CSS statique avec la CLI
Tailwind — améliorable plus tard, non bloquant.

### Serveur de développement : `debug=True` retiré

`app.py` lançait `app.run(host='0.0.0.0', debug=True)`. Le mode debug de Flask expose
une **console d'exécution de code Python** à quiconque est sur le réseau. Passé à
`False`.

---

## Inventaire des fichiers

### Ajoutés

| Fichier | Rôle |
|---|---|
| `manifest_application_args.xml` | attributs réseau injectés dans le manifeste |
| `android_assets/icon.png` · `presplash.png` | icône 512×512 et écran de démarrage optimisés |
| `p4a-recipes/markupsafe/__init__.py` | recette de compilation markupsafe |
| `p4a-recipes/flask/__init__.py` | surcharge Flask résolvant le conflit |
| `cybercafe_manager/static/vendor/` | Tailwind 3.4.16 + Font Awesome 6.4.0 en local |
| `cybercafe_manager/static/images/bg/` | 3 images de fond, anciennement sur Unsplash |
| `LISEZMOI-APK.md` | notice d'installation |

### Modifiés

| Fichier | Nature |
|---|---|
| `main.py` | réécrit — WebView, HTTP, gestion d'erreurs |
| `cybercafe_manager/app.py` | appel `init_db()`, création du dossier de base, `debug=False`, bannière compatible Windows, images locales |
| `buildozer.spec` | réécrit — clés valides, dépendances, architectures |
| `network_security_config.xml` | complété |
| `cybercafe_manager/templates/*.html` (×7) | CDN → ressources locales |
| `test_server_run.py` | réécrit — fonctionnait uniquement sous Linux |
| `cybercafe_manager/buildozer.spec.template` | resynchronisé (il contenait encore les clés cassées) |

### À supprimer quand tu veux

- `cybercafe_manager/certs/` — clé privée SSL inutilisée
- `cybercafe_manager/network_security_config.xml` — copie obsolète, seule celle de la racine est lue
- `uploads/dek_drivsim_logo.jpg` — doublon exact de `static/images/logo.jpg`

---

## Recompiler

Buildozer ne tourne pas nativement sous Windows. La compilation est passée par Docker,
ce qui évite d'installer le SDK, le NDK et Java à la main :

```bash
docker run --rm -v "$(pwd):/home/user/hostcwd" -v dekdrivsim_buildozer:/home/user/.buildozer kivy/buildozer:latest -v android debug
```

Le premier build télécharge le SDK/NDK et compile CPython, Kivy et OpenSSL depuis les
sources : **1 à 2 heures**. Les suivants réutilisent le cache : **2 à 5 minutes**.

**Si un build échoue en plein milieu**, le venv interne de p4a peut rester dans un état
incohérent (deux versions de pip superposées). Le symptôme est un
`ImportError` sur `pip._internal`. Supprimer uniquement ce dossier suffit, les
compilations coûteuses sont ailleurs :

```
.buildozer/android/platform/build-*/build/venv
```

---

## Vérifications effectuées

Sur PC :

- suite unitaire : **5/5**
- routes du serveur : **10/10**
- démarrage à froid sur base vide : `/` répond, redirection vers l'activation
- rendu hors connexion : styles Tailwind appliqués, glyphes Font Awesome rendus

Sur Android (émulateur, Android 15) :

- installation et lancement : processus vivant, aucune exception
- `[FLASK] Serveur prêt` — base initialisée sans erreur SQL
- `[WEBVIEW] Chargé : http://127.0.0.1:5000/`
- écran d'activation affiché avec logo, styles et icônes
- code admin saisi → console propriétaire affichée, APIs en réponse
  (`POST /api/tick 200`, `GET /api/dashboard/stats 200`)

Sur l'APK lui-même : manifeste, architectures, présence des sept dépendances Python,
des templates et des polices — tout contrôlé.

**Non testé :** un téléphone physique. L'appareil disponible pendant les travaux était
en `armeabi-v7a` (32 bits) ; l'APK embarque cette architecture, mais elle n'a pas été
exécutée sur du matériel réel. À vérifier au premier essai.

---

## Ce qui reste à traiter

Deux points de sécurité volontairement laissés en l'état : les corriger impliquait de
modifier le comportement de l'application, ce qui dépassait la remise en marche.

**Mots de passe stockés en clair.** Les codes admin et caissier sont enregistrés tels
quels dans la table `settings`, et affichés dans la console. Les hacher casserait cet
écran de paramètres. Chantier à part.

**Contrôle d'accès par adresse IP.** Le rôle d'un appareil est mémorisé à partir de
`request.remote_addr`. Sur un Wi-Fi maîtrisé c'est acceptable ; si le réseau est
ouvert aux clients, n'importe qui peut tenter le code d'activation, et une adresse
attribuée en DHCP peut changer de machine.

**Dans l'immédiat :** changer les deux codes par défaut (`admin123`, `caissier123`)
dès la première ouverture de la console. Ils figurent dans le code source, donc
publics.

---

## Points à retenir pour la suite

Trois pièges rencontrés ici se reproduiront ailleurs :

1. **Buildozer ignore en silence toute clé inconnue.** Une option inventée ou mal
   orthographiée ne produit aucune erreur — elle ne fait simplement rien. En cas de
   doute, vérifier dans le `default.spec` officiel avant d'y croire.

2. **pyjnius ne peut pas sous-classer une classe Java**, seulement implémenter des
   interfaces. Toute tentative de surcharger `WebViewClient`, `Activity` ou autre
   échouera à l'exécution.

3. **Les appels JNI doivent partir du thread principal Kivy.** Depuis un thread Python
   créé à la main, le classloader ne connaît pas le code de l'application.

Et une méthode : sur ce type de projet, une compilation réussie ne prouve rien.
Trois des cinq défauts ne se seraient manifestés qu'au lancement sur l'appareil.
Installer et lancer réellement l'APK reste la seule vérification qui compte.
