# DEK-DRIVSIM — Installation de l'APK

**Fichier :** `bin/DEK-DRIVSIM-2.5.apk` (46,8 Mo)
**Compatibilité :** Android 5.0 (API 21) et supérieur, processeurs ARM 32 et 64 bits.

## Installation

1. Transférer l'APK sur le téléphone (WhatsApp, câble USB, Bluetooth...).
2. L'ouvrir depuis le gestionnaire de fichiers.
3. Android affichera un avertissement « source inconnue » : autoriser l'installation
   pour l'application depuis laquelle le fichier est ouvert. C'est normal, l'APK
   n'est pas distribué par le Play Store.

> Il s'agit d'une **build de debug**, signée avec la clé de développement d'Android.
> Elle s'installe et fonctionne normalement, mais ne peut pas être publiée sur le
> Play Store en l'état. Pour cela il faudrait une build `release` signée avec une
> clé de production.

## Premier lancement

L'application démarre un serveur local sur le téléphone puis affiche son interface.
Le tout premier écran demande un **code d'activation** qui détermine le rôle de
l'appareil :

| Code par défaut | Rôle obtenu |
|---|---|
| `admin123` | Console propriétaire (accès complet) |
| `caissier123` | Console caissier |

**À faire immédiatement :** changer ces deux codes depuis l'onglet Paramètres de la
console propriétaire. Ils sont publics puisqu'ils figurent dans le code source.

Le rôle est mémorisé par adresse IP. Sur le téléphone lui-même l'adresse est
toujours `127.0.0.1`, donc le rôle choisi au premier lancement y reste actif.

## Postes clients du cybercafé

Le serveur écoute sur tout le réseau local (port 5000). Depuis un PC connecté au
même Wi-Fi, ouvrir dans un navigateur :

```
http://<IP-du-telephone>:5000
```

L'adresse IP du téléphone est visible dans Paramètres Android → À propos → État.
Chaque poste obtient son propre rôle puisqu'il arrive avec une adresse IP distincte.

## Fonctionnement hors connexion

L'application n'a besoin d'aucun accès Internet : l'interface, les polices et les
images sont embarquées dans l'APK. Un cybercafé sans connexion reste pleinement
opérationnel.

## Recompiler

```bash
docker run --rm -v "$(pwd):/home/user/hostcwd" -v dekdrivsim_buildozer:/home/user/.buildozer kivy/buildozer:latest -v android debug
```

Le premier build télécharge le SDK et le NDK Android puis compile CPython, Kivy et
OpenSSL depuis les sources : compter 1 à 2 heures. Les suivants réutilisent le cache
et prennent 2 à 5 minutes.
