# KIOSK_DEKDRIVSIM — Base APK Serveur (Jellow) + PC Client

Cybercafé **DEK-DRIVSIM** — **modèle de base restauré** : **l'APK Android est le serveur Flask** (`0.0.0.0:5000` + WebView `127.0.0.1:5000` via `main.py`), les **PC sont de simples clients kiosk** (`dek_client_agent.py` + `dek-drivsim-pc/`).

```
APK Serveur (Kivy + Flask :5000)  <--- Wi-Fi --->  PC Client (kiosk)
 | main.py + WebView 127.0.0.1 + 0.0.0.0 LAN |  | dek_client_agent.py --server 192.168.x.x --pc PC-01 |
 | cybercafe_manager/app.py + templates Jinja |  | ou dek-drivsim-pc (Electron) en mode client |
```

## Structure

```
.
├── main.py                           # Entree Kivy APK — Flask + WebView (APK serveur)
├── buildozer.spec                    # Build APK Buildozer (arm64-v8a, api 34)
├── cybercafe_manager/app.py          # Backend Flask + SQLite + Jinja (APK serveur)
│   ├── templates/ (admin/cashier/client) + static/vendor/ (hors-ligne)
│   └── static/images/ (logo, presplash, bg)
├── dek_client_agent.py               # Agent PC kiosk Windows (3 verrous) — config + auto-scan LAN
├── dek-drivsim-pc/                   # Alternative PC kiosk Electron (peut pointer vers APK serveur via DEK_API_BASE)
├── p4a-recipes/                      # Recettes markupsafe/flask pour Buildozer
├── .github/workflows/
│   ├── buildozer-apk.yml             # Build APK serveur (manual, Buildozer)
│   ├── build-pc.yml                  # Build PC Electron (windows)
│   └── build-capacitor-apk.yml       # Build APK Capacitor (alternative, manual)
├── docs/GITHUB_SECRETS.md
└── scripts/encode-keystore.*
```

Base Jellow (Buildozer) restaurée sur `main` — branche `archive/pc-serveur-04ac527` conserve l'ancien modèle PC-serveur.

## Builds GitHub (CI)

| Workflow | Runner | Artefact | Release |
|---|---|---|---|
| `build-pc.yml` | `windows-latest` | `dekdrivsim.exe` | `Releases/latest` + sur tag `v*` |
| `build-capacitor-apk.yml` | `ubuntu-latest` (Java 21) | `dekdrivsim.apk` | `Releases/latest` + sur tag `v*` |

Déclenchement : `push` sur `main` touchant `dek-drivsim-pc/**` ou `cybercafe_manager/**`, ou `workflow_dispatch`.

## Secrets GitHub

Settings → Secrets and variables → Actions :

| Secret | Valeur |
|---|---|
| `KEYSTORE_BASE64` | `base64 -w0 dekdrivsim-release.keystore` (une ligne) |
| `KEYSTORE_PASSWORD` | storepass |
| `KEY_PASSWORD` | keypass |

Fichier `dekdrivsim-release.keystore` (alias `dekdrivsim`) — **ne jamais committer** (`.gitignore`).

Voir `docs/GITHUB_SECRETS.md`.

## Génération keystore (une fois)

```bash
keytool -genkeypair -alias dekdrivsim -keyalg RSA -keysize 2048 -validity 10000 \
  -keystore dekdrivsim-release.keystore -storepass "****" -keypass "****" \
  -dname "CN=DEK-DRIVSIM, OU=CyberCafe, O=DEK-DRIVSIM, L=Dakar, ST=Dakar, C=SN"
```

## Com' APK (serveur) ↔ PC (client) — FIX 127.0.0.1

**APK serveur** : `main.py:39` `FLASK_BIND_HOST=0.0.0.0:5000` (LAN) + `FLASK_HOST=127.0.0.1:5000` (WebView). `cybercafe_manager/app.py:1649` `app.run(host='0.0.0.0')`.

**PC client** : `dek_client_agent.py:32` **ne hardcode plus `127.0.0.1`** :
```bash
# config manuelle
python dek_client_agent.py --server 192.168.1.100 --pc PC-03
# ou fichier dek_config.json {"server_ip":"192.168.1.100","pc_name":"PC-03"}
# ou auto-scan 192.168.x.0/24 sur /api/health si aucune IP fournie
python dek_client_agent.py  # scan automatique
```
`dek-drivsim-pc/` en mode client : `VITE_API_BASE=http://192.168.1.100:5000` ou `localStorage DEK_API_BASE` (LoginPage).

## Développement local

### APK serveur (Buildozer)
```bash
# Docker (recommande, évite SDK/NDK)
docker run --rm -v "$(pwd):/home/user/hostcwd" -v dekdrivsim_buildozer:/home/user/.buildozer kivy/buildozer:latest -v android debug
# ou release signe (secrets)
docker run ... buildozer android release
# ou manuel
buildozer android debug deploy run
# → bin/*.apk
```

### PC kiosk (dek_client_agent)
```bash
python dek_client_agent.py --server 192.168.1.100 --pc PC-01   # kiosk inviolable + heartbeat
pyinstaller --onefile --noconsole dek_client_agent.py         # → dist/dek_client_agent.exe
# Alternative Electron
cd dek-drivsim-pc
VITE_API_BASE=http://192.168.1.100:5000 npm run dev:electron
```

**Codes :**
- Propriétaire device : **16c aléatoire** généré au 1er lancement, dans `admin_password.txt` (jamais `admin123`)
- Caissier device : `caissier123`
- Mastercode Kiosk : `DEK-EXIT-2026` (`Ctrl+Alt+Q` / `F12`)

## API santé

```
GET /api/health  → {status:"ok", db:"ok", version:"2.0"}
GET /api/settings → {hourly_rate, cyber_name, ...} (whitelist côté serveur)
```

## Releases

- `latest` à chaque push main, `v*.*.*` via `git tag v2.0.0 && git push origin v2.0.0`
