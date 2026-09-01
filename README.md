# KIOSK_DEKDRIVSIM — PC Kiosk + Android Capacitor

Cybercafé **DEK-DRIVSIM** : application Kiosk Windows (`.exe` Electron) + application Android Capacitor pour **Propriétaire** et **Caissier**. Le PC fait office de **serveur Flask** (`:5000`) et de **client Kiosk** ; l'APK se connecte au PC via le réseau local.

```
PC Kiosk (Electron + React + Flask :5000)  <--- Wi-Fi --->  APK Android (Capacitor)
         |  dekdrivsim.exe (NSIS x64)                 |  dekdrivsim.apk (signed dekdrivsim)
         +---> API Flask + SQLite (cybercafe.db) <----+
```

## Structure

```
.
├── cybercafe_manager/app.py          # Backend Flask + SQLite (API /api/*) — API-only, pas de Jinja
├── dek-drivsim-pc/                   # Frontend React + Electron + Capacitor
│   ├── src/                          # 3 rôles: Admin / Cashier / Player
│   ├── electron-main.cjs / preload.cjs
│   ├── capacitor.config.json
│   └── android/                      # Projet Android (généré, build via Gradle)
├── .github/workflows/
│   ├── build-pc.yml                  # Build Windows dekdrivsim.exe
│   └── build-capacitor-apk.yml       # Build Android dekdrivsim.apk (signé dekdrivsim)
├── docs/GITHUB_SECRETS.md            # Guide keystore + secrets
└── scripts/encode-keystore.*         # Helper base64 keystore
```

Seuls ces fichiers sont nécessaires aux deux builds. Legacy Buildozer/Kivy supprimé (voir branche `archive/legacy-jellow` si besoin).

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

## Développement local

### PC Kiosk (Electron)
```bash
cd dek-drivsim-pc
npm ci
npm run build
npm run build:electron:win  # -> dist-electron/dekdrivsim.exe
npm run dev:electron        # dev hot-reload
```

`electron-main.cjs` lance Flask (`cybercafe_manager/app.py` via `extraResources`) et attend `http://127.0.0.1:5000/api/health`.

### APK Capacitor
```bash
cd dek-drivsim-pc
npm ci
npm run build
npx cap sync android
cd android && ./gradlew assembleRelease
```

## Rôles & Com' PC ↔ APK

| Rôle | Route React | API |
|---|---|---|
| **Admin** | `/admin` | `/api/dashboard/stats`, `/api/terminals`, etc. |
| **Caissier** | `/cashier` | vente tickets, recharges |
| **Joueur** | `/player` | catalogue jeux |

**PC cherche 127.0.0.1:5000 corrigé :** l'APK ne hardcode plus `127.0.0.1`. `src/api.ts` lit `localStorage DEK_API_BASE` (IP saisie sur l'écran Login si `Capacitor.isNative`). Le PC Electron expose `/api/health` et `getLocalIP` via `preload.cjs`.

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
