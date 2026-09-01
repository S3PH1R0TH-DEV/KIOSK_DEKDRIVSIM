# -*- coding: utf-8 -*-
"""
DEK-DRIVSIM CyberCafe - Serveur Central Unifié de Niveau Entreprise
Ce fichier regroupe l'intégralité du code de l'application (Moteur Web + Modèle de données SQLite).
Il gère de manière autonome l'initialisation de la base de données, la sécurité, l'audit et l'administration.
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import sqlite3
import random
import secrets
import string
from datetime import datetime, timedelta
import os
import sys
import csv
import io

def _generate_strong_admin_password() -> str:
    # 16 chars, au moins 1 maj, 1 min, 1 chiffre, 1 symbole - jamais devinable par caissier
    alphabet = string.ascii_letters + string.digits + "!@#$%*"
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(16))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd) and any(c in "!@#$%*" for c in pwd):
            return pwd
    # Fallback format lisible: DEK-ADM-XXXX-XXXX-XXXX
    # return 'DEK-ADM-' + '-'.join(''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) for _ in range(3))

app = Flask(__name__)
app.secret_key = os.environ.get('DEK_SECRET_KEY', 'senet_cybercafe_secret_key')
# CORS : autorise uniquement le réseau local ; en Electron/Capacitor le origin est file:// ou capacitor://
# On n'active pas supports_credentials avec wildcard (invalide côté navigateur)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)
# Limite taille payload + JSON strict
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# --- COUCHE DE BASE DE DONNÉES (DATABASE LAYER CONSOLIDATED) ---

def _get_db_path():
    # Android : stockage privé
    if 'ANDROID_ARGUMENT' in os.environ or os.environ.get('ANDROID_PRIVATE'):
        p = os.path.join(os.environ.get('ANDROID_PRIVATE', '/data/data/org.dekdrivsim/files'), 'cybercafe.db')
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        return p
    # Windows Program Files est en lecture seule -> utiliser %APPDATA%\DEK-DRIVSIM
    base_dir = os.path.dirname(__file__)
    default = os.path.join(base_dir, 'cybercafe.db')
    # Heuristique : si on est dans Program Files ou dossier non inscriptible
    try:
        # Test ecriture
        if 'Program Files' in os.path.abspath(base_dir) or not os.access(base_dir, os.W_OK):
            raise OSError('read-only')
        # Essai ecriture fichier test
        test = os.path.join(base_dir, '.writetest')
        with open(test, 'w') as f: f.write('x')
        os.remove(test)
        os.makedirs(os.path.dirname(os.path.abspath(default)), exist_ok=True)
        return default
    except Exception:
        appdata = os.getenv('APPDATA') or os.path.expanduser('~')
        dek_dir = os.path.join(appdata, 'DEK-DRIVSIM')
        os.makedirs(dek_dir, exist_ok=True)
        new_path = os.path.join(dek_dir, 'cybercafe.db')
        # Migration : copie l'ancienne DB si elle existe et la nouvelle n'existe pas
        if os.path.exists(default) and not os.path.exists(new_path):
            try:
                import shutil
                shutil.copy2(default, new_path)
                print(f"[DB] Migration Program Files -> {new_path}")
            except Exception as e:
                print(f"[DB] Migration echouee: {e}")
        os.makedirs(os.path.dirname(os.path.abspath(new_path)), exist_ok=True)
        return new_path

DB_PATH = _get_db_path()
# Compat : admin_password.txt doit suivre la DB (même dossier inscriptible)
def _get_admin_pwd_path():
    try:
        d = os.path.dirname(DB_PATH)
        test = os.path.join(d, '.writetest2')
        with open(test, 'w') as f: f.write('x')
        os.remove(test)
        return os.path.join(d, 'admin_password.txt')
    except Exception:
        return os.path.join(os.path.dirname(DB_PATH), 'admin_password.txt')

ADMIN_PWD_PATH = _get_admin_pwd_path()

def get_db():
    # Timeout de 30 secondes et pragma busy_timeout pour éviter les blocages de concurrence.
    # On évite le mode WAL qui plante sur les cartes SD / mémoires partagées d'Android (/sdcard/).
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Active les clés étrangères
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Table des terminaux/simulateurs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS terminals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        type TEXT NOT NULL, -- 'PC' or 'Console'
        status TEXT NOT NULL DEFAULT 'free', -- 'free', 'occupied', 'paused', 'maintenance'
        current_session_id INTEGER,
        ip_address TEXT,
        last_ping TEXT
    )
    ''')
    
    # Table des tickets d'accès prépayés
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        duration_mins INTEGER NOT NULL,
        price INTEGER NOT NULL, -- FCFA
        status TEXT NOT NULL DEFAULT 'active', -- 'active', 'sold', 'used', 'expired'
        created_at TEXT NOT NULL,
        used_at TEXT
    )
    ''')
    
    # Table des comptes Auto-Écoles
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS driving_schools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        school_name TEXT UNIQUE NOT NULL,
        instructor_name TEXT NOT NULL,
        special_hourly_rate INTEGER NOT NULL DEFAULT 300, -- FCFA/hour
        balance INTEGER NOT NULL DEFAULT 0, -- FCFA
        created_at TEXT NOT NULL
    )
    ''')
    
    # Table des joueurs membres avec système de parrainage et lien Auto-École
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        balance INTEGER NOT NULL DEFAULT 0, -- FCFA
        status TEXT NOT NULL DEFAULT 'active', -- 'active', 'suspended'
        referral_code TEXT UNIQUE NOT NULL,
        referred_by_code TEXT, -- Code parrain saisi à l'inscription
        driving_school_id INTEGER, -- NULL si joueur normal
        created_at TEXT NOT NULL,
        FOREIGN KEY (driving_school_id) REFERENCES driving_schools(id) ON DELETE SET NULL
    )
    ''')
    
    # Table de suivi des parrainages (Membres, tickets et caissiers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_type TEXT NOT NULL, -- 'player', 'cashier', 'ticket'
        referrer_code TEXT NOT NULL,
        referred_username TEXT NOT NULL,
        bonus_type TEXT NOT NULL, -- 'free_session', '50_percent_discount', 'cashier_bonus'
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'claimed'
        created_at TEXT NOT NULL
    )
    ''')
    
    # Table d'évaluation journalière du caissier gérant (14 jours d'essai)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cashier_evaluations (
        day_number INTEGER PRIMARY KEY, -- Jour 1 à 14
        rating INTEGER NOT NULL DEFAULT 0, -- Note sur 5 étoiles
        punctuality TEXT, -- 'good', 'late', 'absent'
        cash_accuracy TEXT, -- 'exact', 'short', 'over'
        recruits_count INTEGER DEFAULT 0,
        notes TEXT,
        evaluated_at TEXT
    )
    ''')

    # Table d'auto-configuration permanente des appareils (Rôle mémorisé)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS device_roles (
        ip_address TEXT PRIMARY KEY,
        role TEXT NOT NULL -- 'admin' or 'cashier'
    )
    ''')
    
    # Table d'audit des connexions (Journal de Connexion)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS connection_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        terminal_name TEXT NOT NULL,
        session_type TEXT NOT NULL, -- 'admin', 'cashier', 'player', 'ticket', 'postpaid'
        login_time TEXT NOT NULL,
        logout_time TEXT,
        duration_mins INTEGER DEFAULT 0
    )
    ''')
    
    # Table des sessions de jeux actives
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        terminal_id INTEGER NOT NULL,
        session_type TEXT NOT NULL, -- 'ticket', 'player', 'postpaid', 'driving_school', 'admin', 'cashier'
        reference_id INTEGER, -- ID lié
        start_time TEXT NOT NULL,
        end_time TEXT,
        duration_mins INTEGER,
        time_spent_seconds INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'running', -- 'running', 'paused', 'completed'
        amount_paid INTEGER DEFAULT 0,
        FOREIGN KEY (terminal_id) REFERENCES terminals(id)
    )
    ''')
    
    # Table d'historique comptable global
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, -- 'ticket_sale', 'player_recharge', 'session_payment', 'school_recharge'
        amount INTEGER NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')
    
    # Table de configuration globale (Settings)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')

    # Table de la bibliothèque des jeux du simulateur
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        image_url TEXT,
        launch_path TEXT
    )
    ''')
    
    conn.commit()
    
    # Insertion des paramètres par défaut
    cursor.execute("SELECT COUNT(*) FROM settings")
    if cursor.fetchone()[0] == 0:
        # Propriétaire : mot de passe fort aléatoire (jamais admin123) - le caissier garde caissier123
        strong_admin = os.environ.get('DEK_ADMIN_PASSWORD') or _generate_strong_admin_password()
        print(f"\n[SECURITE] Mot de passe Proprietaire genere: {strong_admin}  (a conserver, caissier ne le connait pas)\n")
        default_settings = [
            ('cyber_name', 'DEK-DRIVSIM CyberCafe'),
            ('currency', 'FCFA'),
            ('hourly_rate', '500'),
            ('wifi_ssid', 'DEK-DRIVSIM_WiFi'),
            ('wifi_password', 'DEKDRIV2026'),
            ('admin_password', strong_admin),
            ('cashier_password', 'caissier123'),
            ('cashier_referral_bonus', '200')
        ]
        cursor.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", default_settings)
        conn.commit()
        # Sauvegarde locale pour le propriétaire (hors git) - dans dossier inscriptible (APPDATA si Program Files)
        try:
            with open(ADMIN_PWD_PATH, 'w', encoding='utf-8') as f:
                f.write(f"DEK-DRIVSIM - Acces Proprietaire\nDate: {datetime.now().isoformat()}\nCode Proprietaire (admin): {strong_admin}\nCode Caissier: caissier123\nMastercode Kiosk: {os.environ.get('DEK_MASTERCODE', 'DEK-EXIT-2026')}\nDB: {DB_PATH}\n")
        except Exception as e:
            print(f"[WARN] Impossible d'ecrire {ADMIN_PWD_PATH}: {e}")
    else:
        cursor.execute("UPDATE settings SET value = 'DEK-DRIVSIM CyberCafe' WHERE key = 'cyber_name'")
        cursor.execute("UPDATE settings SET value = 'DEK-DRIVSIM_WiFi' WHERE key = 'wifi_ssid'")
        cursor.execute("UPDATE settings SET value = 'DEKDRIV2026' WHERE key = 'wifi_password'")
        # Migration securite : si ancien admin123 encore present -> remplace par fort aleatoire
        cursor.execute("SELECT value FROM settings WHERE key='admin_password'")
        row = cursor.fetchone()
        if row and row[0] == 'admin123':
            new_pwd = os.environ.get('DEK_ADMIN_PASSWORD') or _generate_strong_admin_password()
            cursor.execute("UPDATE settings SET value=? WHERE key='admin_password'", (new_pwd,))
            print(f"\n[MIGRATION SECURITE] admin123 detecte -> remplace par mot de passe fort: {new_pwd}\n")
            try:
                with open(ADMIN_PWD_PATH, 'w', encoding='utf-8') as f:
                    f.write(f"DEK-DRIVSIM - MIGRATION\nDate: {datetime.now().isoformat()}\nNouveau Code Proprietaire: {new_pwd}\nAncien: admin123 (revoque)\nDB: {DB_PATH}\n")
            except Exception as e:
                print(f"[WARN] Impossible d'ecrire {ADMIN_PWD_PATH}: {e}")
        else:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password', ?)", (_generate_strong_admin_password(),))
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cashier_password', 'caissier123')")
        conn.commit()
        # Recree admin_password.txt si supprime mais DB a encore le mot de passe (cas reinstall partielle)
        try:
            pwd_path = ADMIN_PWD_PATH
            if not os.path.exists(pwd_path):
                cursor.execute("SELECT value FROM settings WHERE key='admin_password'")
                r = cursor.fetchone()
                if r and r[0] and r[0] != 'admin123':
                    with open(pwd_path, 'w', encoding='utf-8') as f:
                        f.write(f"DEK-DRIVSIM - RECUPERATION\nDate: {datetime.now().isoformat()}\nCode Proprietaire (admin): {r[0]}\nCode Caissier: caissier123\nMastercode Kiosk: {os.environ.get('DEK_MASTERCODE', 'DEK-EXIT-2026')}\n")
                    print(f"[SECURITE] admin_password.txt regenere depuis la DB\n")
        except Exception:
            pass

    # Création des comptes d'accès spéciaux
    cursor.execute("SELECT COUNT(*) FROM players WHERE username = 'admin_dek'")
    if cursor.fetchone()[0] == 0:
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO players (username, password, balance, status, referral_code, created_at)
            VALUES ('admin_dek', 'admin123', 999999, 'active', 'REF-ADMIN-DEK', ?)
        ''', (now,))
        
    cursor.execute("SELECT COUNT(*) FROM players WHERE username = 'caissier_dek'")
    if cursor.fetchone()[0] == 0:
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO players (username, password, balance, status, referral_code, created_at)
            VALUES ('caissier_dek', 'caissier123', 60, 'active', 'REF-CAISSIER-DEK', ?)
        ''', (now,))
    conn.commit()

    # Initialisation de la grille d'évaluation caissier (14 jours)
    cursor.execute("SELECT COUNT(*) FROM cashier_evaluations")
    if cursor.fetchone()[0] == 0:
        evals = []
        for d in range(1, 15):
            evals.append((d, 0, 'good', 'exact', 0, '', ''))
        cursor.executemany("INSERT INTO cashier_evaluations (day_number, rating, punctuality, cash_accuracy, recruits_count, notes, evaluated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", evals)
        conn.commit()

    # Insertion de la bibliothèque de jeux par défaut
    cursor.execute("SELECT COUNT(*) FROM games")
    if cursor.fetchone()[0] == 0:
        default_games = [
            ('Assetto Corsa Competizione', 'Simulation Auto', '/static/images/logo.png', 'C:\\Games\\AssettoCorsa\\ACC.exe'),
            ('Forza Horizon 5', 'Simulation Auto', '/static/images/logo.png', 'C:\\Games\\Forza5\\ForzaHorizon5.exe'),
            ('Euro Truck Simulator 2', 'Simulation', '/static/images/logo.png', 'C:\\Games\\ETS2\\bin\\win_x64\\eurotruck2.exe'),
            ('Need for Speed Unbound', 'Course Arcade', '/static/images/logo.png', 'C:\\Games\\NFSUnbound\\NFSUnbound.exe'),
            ('Dirt Rally 2.0', 'Simulation Auto', '/static/images/logo.png', 'C:\\Games\\DirtRally2\\DirtRally2.exe'),
            ('Gran Turismo 7 (PS5)', 'Simulation Auto', '/static/images/logo.png', 'PS5_LAUNCHER_GT7'),
            ('Grand Theft Auto V', 'Action / Monde Ouvert', '/static/images/logo.png', 'C:\\Games\\GTAV\\PlayGTAV.exe'),
            ('FIFA 26', 'Sport', '/static/images/logo.png', 'C:\\Games\\FIFA26\\FIFA26.exe')
        ]
        cursor.executemany("INSERT INTO games (name, category, image_url, launch_path) VALUES (?, ?, ?, ?)", default_games)
        conn.commit()

    conn.close()

# Création/migration des tables dès l'import du module.
# Indispensable sur Android : la base vit dans ANDROID_PRIVATE et part toujours vide,
# le cybercafe.db livré dans les sources n'y est jamais recopié.
init_db()

# --- FONCTIONS HELPERS DB ---

def get_device_role(ip_address):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM device_roles WHERE ip_address = ?", (ip_address,))
    row = cursor.fetchone()
    conn.close()
    return row['role'] if row else None

def set_device_role(ip_address, role):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO device_roles (ip_address, role) VALUES (?, ?)", (ip_address, role))
    conn.commit()
    conn.close()
    return True

def get_all_terminals():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.session_type, s.start_time, s.end_time, s.duration_mins, s.time_spent_seconds, s.reference_id
        FROM terminals t
        LEFT JOIN sessions s ON t.current_session_id = s.id
    ''')
    terminals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return terminals

def get_terminal(terminal_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.session_type, s.start_time, s.end_time, s.duration_mins, s.time_spent_seconds, s.reference_id
        FROM terminals t
        LEFT JOIN sessions s ON t.current_session_id = s.id
        WHERE t.id = ?
    ''', (terminal_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_terminal_by_name(name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.session_type, s.start_time, s.end_time, s.duration_mins, s.time_spent_seconds, s.reference_id
        FROM terminals t
        LEFT JOIN sessions s ON t.current_session_id = s.id
        WHERE t.name = ?
    ''', (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_terminal_status(terminal_id, status):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE terminals SET status = ? WHERE id = ?", (status, terminal_id))
    conn.commit()
    conn.close()

def ping_terminal(name, ip_address):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("UPDATE terminals SET ip_address = ?, last_ping = ? WHERE name = ?", (ip_address, now, name))
    conn.commit()
    conn.close()

def generate_tickets(count, duration_mins, price):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    created_tickets = []
    
    for _ in range(count):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        while True:
            cursor.execute("SELECT id FROM tickets WHERE code = ?", (code,))
            if not cursor.fetchone():
                break
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
        cursor.execute("INSERT INTO tickets (code, duration_mins, price, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                       (code, duration_mins, price, now))
        created_tickets.append({
            'code': code,
            'duration_mins': duration_mins,
            'price': price,
            'status': 'active',
            'created_at': now
        })
        
    conn.commit()
    conn.close()
    return created_tickets

def get_tickets(status=None):
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id DESC", (status,))
    else:
        cursor.execute("SELECT * FROM tickets ORDER BY id DESC")
    tickets = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tickets

def get_ticket_by_code(code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE code = ?", (code,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_player(username, password, initial_balance=0, referred_by_code=None, driving_school_id=None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    ref_code = f"DEK-{username.upper()}"
    
    try:
        cursor.execute('''
            INSERT INTO players (username, password, balance, status, referral_code, referred_by_code, driving_school_id, created_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
        ''', (username, password, initial_balance, ref_code, referred_by_code, driving_school_id, now))
        
        if referred_by_code:
            cursor.execute("SELECT username FROM players WHERE referral_code = ?", (referred_by_code,))
            referrer = cursor.fetchone()
            if referrer:
                cursor.execute('''
                    INSERT INTO referrals (referrer_type, referrer_code, referred_username, bonus_type, status, created_at)
                    VALUES ('player', ?, ?, 'free_session', 'pending', ?)
                ''', (referred_by_code, username, now))
            elif referred_by_code == 'CASHIER-DEK':
                cursor.execute("SELECT day_number FROM cashier_evaluations WHERE evaluated_at = '' ORDER BY day_number ASC LIMIT 1")
                day_row = cursor.fetchone()
                if day_row:
                    cursor.execute("UPDATE cashier_evaluations SET recruits_count = recruits_count + 1 WHERE day_number = ?", (day_row['day_number'],))
                
                cursor.execute('''
                    INSERT INTO referrals (referrer_type, referrer_code, referred_username, bonus_type, status, created_at)
                    VALUES ('cashier', 'CASHIER-DEK', ?, 'cashier_bonus', 'claimed', ?)
                ''', (username, now))
            else:
                cursor.execute('''
                    INSERT INTO referrals (referrer_type, referrer_code, referred_username, bonus_type, status, created_at)
                    VALUES ('ticket', ?, ?, '50_percent_discount', 'pending', ?)
                ''', (referred_by_code, username, now))

        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def recharge_player(player_id, amount):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE players SET balance = balance + ? WHERE id = ?", (amount, player_id))
    
    cursor.execute("SELECT username FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    
    if player:
        now = datetime.now().isoformat()
        cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                       ('player_recharge', amount, f"Recharge compte de {player['username']}", now))
        conn.commit()
        success = True
    else:
        success = False
    conn.close()
    return success

def get_players():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, d.school_name 
        FROM players p
        LEFT JOIN driving_schools d ON p.driving_school_id = d.id
        ORDER BY p.username ASC
    ''')
    players = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return players

def get_player_by_username(username):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_driving_school(school_name, instructor_name, hourly_rate=300, initial_balance=0):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    try:
        cursor.execute('''
            INSERT INTO driving_schools (school_name, instructor_name, special_hourly_rate, balance, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (school_name, instructor_name, hourly_rate, initial_balance, now))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_driving_schools():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM driving_schools ORDER BY school_name ASC")
    schools = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return schools

def delete_driving_school(school_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM driving_schools WHERE id = ?", (school_id,))
    conn.commit()
    conn.close()
    return True

def recharge_driving_school(school_id, amount):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE driving_schools SET balance = balance + ? WHERE id = ?", (amount, school_id))
    
    cursor.execute("SELECT school_name FROM driving_schools WHERE id = ?", (school_id,))
    school = cursor.fetchone()
    if school:
        now = datetime.now().isoformat()
        cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                       ('school_recharge', amount, f"Rechargement Auto-École {school['school_name']}", now))
        conn.commit()
        success = True
    else:
        success = False
    conn.close()
    return success

def get_all_referrals():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM referrals ORDER BY id DESC")
    refs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return refs

def claim_referral_bonus(ref_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE referrals SET status = 'claimed' WHERE id = ?", (ref_id,))
    conn.commit()
    conn.close()
    return True

def get_cashier_evaluations():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cashier_evaluations ORDER BY day_number ASC")
    evals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return evals

def submit_cashier_evaluation(day_number, rating, punctuality, cash_accuracy, notes):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        UPDATE cashier_evaluations
        SET rating = ?, punctuality = ?, cash_accuracy = ?, notes = ?, evaluated_at = ?
        WHERE day_number = ?
    ''', (rating, punctuality, cash_accuracy, notes, now, day_number))
    conn.commit()
    conn.close()
    return True

def get_all_connection_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM connection_logs ORDER BY id DESC")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs

def log_session_login(username, terminal_name, session_type):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO connection_logs (username, terminal_name, session_type, login_time)
        VALUES (?, ?, ?, ?)
    ''', (username, terminal_name, session_type, now))
    conn.commit()
    conn.close()
    return True

def log_session_logout(terminal_name):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    now_str = now.isoformat()
    
    cursor.execute('''
        SELECT * FROM connection_logs 
        WHERE terminal_name = ? AND logout_time IS NULL 
        ORDER BY id DESC LIMIT 1
    ''', (terminal_name,))
    row = cursor.fetchone()
    
    if row:
        login_time = datetime.fromisoformat(row['login_time'])
        duration_mins = int((now - login_time).total_seconds() / 60)
        if duration_mins < 1:
            duration_mins = 1
            
        cursor.execute('''
            UPDATE connection_logs 
            SET logout_time = ?, duration_mins = ? 
            WHERE id = ?
        ''', (now_str, duration_mins, row['id']))
        conn.commit()
    conn.close()
    return True

def get_all_games():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM games ORDER BY category, name")
    games = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return games

def add_game(name, category, image_url, launch_path):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO games (name, category, image_url, launch_path) VALUES (?, ?, ?, ?)",
                   (name, category, image_url, launch_path))
    conn.commit()
    conn.close()
    return True

def delete_game(game_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()
    return True

def start_ticket_session(terminal_id, ticket_code):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tickets WHERE code = ? AND status = 'active'", (ticket_code,))
    ticket = cursor.fetchone()
    if not ticket:
        conn.close()
        return False, "Ticket invalide ou déjà vendu/utilisé"
        
    cursor.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,))
    terminal = cursor.fetchone()
    if not terminal:
        conn.close()
        return False, "Poste introuvable"
    if terminal['status'] != 'free':
        conn.close()
        return False, "Le poste est occupé"
        
    now = datetime.now()
    start_time_str = now.isoformat()
    end_time_str = (now + timedelta(minutes=ticket['duration_mins'])).isoformat()
    
    cursor.execute('''
        INSERT INTO sessions (terminal_id, session_type, reference_id, start_time, end_time, duration_mins, status)
        VALUES (?, 'ticket', ?, ?, ?, ?, 'running')
    ''', (terminal_id, ticket['id'], start_time_str, end_time_str, ticket['duration_mins']))
    
    session_id = cursor.lastrowid
    cursor.execute("UPDATE terminals SET status = 'occupied', current_session_id = ? WHERE id = ?", (session_id, terminal_id))
    
    used_at_str = start_time_str
    cursor.execute("UPDATE tickets SET status = 'used', used_at = ? WHERE id = ?", (used_at_str, ticket['id']))
    
    cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                   ('ticket_sale', ticket['price'], f"Vente ticket {ticket_code} ({ticket['duration_mins']} mins) pour {terminal['name']}", start_time_str))
                   
    conn.commit()
    conn.close()
    
    log_session_login(f"Ticket {ticket_code}", terminal['name'], 'ticket')
    return True, session_id

def get_cashier_played_minutes_today():
    conn = get_db()
    cursor = conn.cursor()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cursor.execute('''
        SELECT SUM(duration_mins) FROM connection_logs 
        WHERE username = 'caissier_dek' AND login_time >= ?
    ''', (today_start,))
    row = cursor.fetchone()
    conn.close()
    return row[0] or 0

def start_player_session(terminal_id, username, password):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM players WHERE username = ? AND password = ? AND status = 'active'", (username, password))
    player = cursor.fetchone()
    if not player:
        conn.close()
        return False, "Identifiants incorrects ou compte suspendu"
        
    cursor.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,))
    terminal = cursor.fetchone()
    if not terminal or terminal['status'] != 'free':
        conn.close()
        return False, "Poste occupé ou introuvable"
        
    session_type = 'player'
    ref_id = player['id']
    
    if username == 'admin_dek':
        duration_mins = 60000
        session_type = 'admin'
    elif username == 'caissier_dek':
        minutes_already_played = get_cashier_played_minutes_today()
        remaining_mins = max(0, 60 - minutes_already_played)
        if remaining_mins <= 0:
            conn.close()
            return False, "Limite de connexion de 1 heure par jour atteinte pour le caissier !"
        duration_mins = remaining_mins
        session_type = 'cashier'
    elif player['driving_school_id']:
        cursor.execute("SELECT special_hourly_rate FROM driving_schools WHERE id = ?", (player['driving_school_id'],))
        hourly_rate = cursor.fetchone()['special_hourly_rate']
        session_type = 'driving_school'
        ref_id = player['driving_school_id']
        duration_mins = int((player['balance'] / hourly_rate) * 60)
    else:
        cursor.execute("SELECT value FROM settings WHERE key = 'hourly_rate'")
        hourly_rate = int(cursor.fetchone()['value'])
        duration_mins = int((player['balance'] / hourly_rate) * 60)
        
    if duration_mins < 1:
        conn.close()
        return False, "Solde insuffisant"
        
    now = datetime.now()
    start_time_str = now.isoformat()
    end_time_str = (now + timedelta(minutes=duration_mins)).isoformat()
    
    cursor.execute('''
        INSERT INTO sessions (terminal_id, session_type, reference_id, start_time, end_time, duration_mins, status)
        VALUES (?, ?, ?, ?, ?, ?, 'running')
    ''', (terminal_id, session_type, ref_id, start_time_str, end_time_str, duration_mins))
    
    session_id = cursor.lastrowid
    cursor.execute("UPDATE terminals SET status = 'occupied', current_session_id = ? WHERE id = ?", (session_id, terminal_id))
    
    conn.commit()
    conn.close()
    
    log_session_login(username, terminal['name'], session_type)
    return True, session_id

def start_postpaid_session(terminal_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,))
    terminal = cursor.fetchone()
    if not terminal or terminal['status'] != 'free':
        conn.close()
        return False, "Poste occupé ou introuvable"
        
    now = datetime.now()
    start_time_str = now.isoformat()
    
    cursor.execute('''
        INSERT INTO sessions (terminal_id, session_type, reference_id, start_time, status)
        VALUES (?, 'postpaid', NULL, ?, 'running')
    ''', (terminal_id, start_time_str))
    
    session_id = cursor.lastrowid
    cursor.execute("UPDATE terminals SET status = 'occupied', current_session_id = ? WHERE id = ?", (session_id, terminal_id))
    conn.commit()
    conn.close()
    
    log_session_login("Session Libre-accès", terminal['name'], 'postpaid')
    return True, session_id

def pause_session(terminal_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT current_session_id FROM terminals WHERE id = ?", (terminal_id,))
    term = cursor.fetchone()
    if not term or not term['current_session_id']:
        conn.close()
        return False, "Aucune session active sur ce poste"
        
    session_id = term['current_session_id']
    cursor.execute("UPDATE sessions SET status = 'paused' WHERE id = ?", (session_id,))
    cursor.execute("UPDATE terminals SET status = 'paused' WHERE id = ?", (terminal_id,))
    conn.commit()
    conn.close()
    return True, "Session suspendue"

def resume_session(terminal_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT current_session_id FROM terminals WHERE id = ?", (terminal_id,))
    term = cursor.fetchone()
    if not term or not term['current_session_id']:
        conn.close()
        return False, "Aucune session active sur ce poste"
        
    session_id = term['current_session_id']
    
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    
    if session['session_type'] in ['ticket', 'player', 'driving_school', 'cashier']:
        remaining_seconds = (session['duration_mins'] * 60) - session['time_spent_seconds']
        if remaining_seconds <= 0:
            conn.close()
            return False, "Le temps de cette session est déjà écoulé"
            
        new_end_time = (datetime.now() + timedelta(seconds=remaining_seconds)).isoformat()
        cursor.execute("UPDATE sessions SET status = 'running', end_time = ? WHERE id = ?", (new_end_time, session_id))
    else:
        cursor.execute("UPDATE sessions SET status = 'running' WHERE id = ?", (session_id,))
        
    cursor.execute("UPDATE terminals SET status = 'occupied' WHERE id = ?", (terminal_id,))
    conn.commit()
    conn.close()
    return True, "Session reprise"

def stop_session(terminal_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT current_session_id, name FROM terminals WHERE id = ?", (terminal_id,))
    term = cursor.fetchone()
    if not term or not term['current_session_id']:
        conn.close()
        return False, "Aucune session active sur ce poste"
        
    session_id = term['current_session_id']
    terminal_name = term['name']
    
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session = cursor.fetchone()
    
    now = datetime.now()
    now_str = now.isoformat()
    
    if session['session_type'] == 'player':
        cursor.execute("SELECT value FROM settings WHERE key = 'hourly_rate'")
        hourly_rate = int(cursor.fetchone()['value'])
        played_mins = int(session['time_spent_seconds'] / 60)
        if played_mins < 1:
            played_mins = 1
        cost = int((played_mins / 60.0) * hourly_rate)
        
        player_id = session['reference_id']
        cursor.execute("UPDATE players SET balance = MAX(0, balance - ?) WHERE id = ?", (cost, player_id))
        
        cursor.execute("SELECT username FROM players WHERE id = ?", (player_id,))
        player_name = cursor.fetchone()['username']
        cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                       ('session_payment', cost, f"Consommation joueur {player_name} ({played_mins} mins) sur {terminal_name}", now_str))
        cursor.execute("UPDATE sessions SET status = 'completed', amount_paid = ? WHERE id = ?", (cost, session_id))
        
    elif session['session_type'] == 'driving_school':
        school_id = session['reference_id']
        cursor.execute("SELECT special_hourly_rate, school_name FROM driving_schools WHERE id = ?", (school_id,))
        school_row = cursor.fetchone()
        hourly_rate = school_row['special_hourly_rate']
        school_name = school_row['school_name']
        
        played_mins = int(session['time_spent_seconds'] / 60)
        if played_mins < 1:
            played_mins = 1
        cost = int((played_mins / 60.0) * hourly_rate)
        
        cursor.execute("UPDATE driving_schools SET balance = MAX(0, balance - ?) WHERE id = ?", (cost, school_id))
        cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                       ('session_payment', cost, f"Consommation Auto-École {school_name} ({played_mins} mins) sur {terminal_name}", now_str))
        cursor.execute("UPDATE sessions SET status = 'completed', amount_paid = ? WHERE id = ?", (cost, session_id))
        
    elif session['session_type'] == 'postpaid':
        cursor.execute("SELECT value FROM settings WHERE key = 'hourly_rate'")
        hourly_rate = int(cursor.fetchone()['value'])
        played_mins = int(session['time_spent_seconds'] / 60)
        if played_mins < 1:
            played_mins = 1
        cost = int((played_mins / 60.0) * hourly_rate)
        
        cursor.execute("INSERT INTO transactions (type, amount, description, created_at) VALUES (?, ?, ?, ?)",
                       ('session_payment', cost, f"Paiement session post-payée ({played_mins} mins) sur {terminal_name}", now_str))
        cursor.execute("UPDATE sessions SET status = 'completed', amount_paid = ?, end_time = ? WHERE id = ?", (cost, now_str, session_id))
        
    elif session['session_type'] in ['ticket', 'admin', 'cashier']:
        cursor.execute("UPDATE sessions SET status = 'completed' WHERE id = ?", (session_id,))
        
    cursor.execute("UPDATE terminals SET status = 'free', current_session_id = NULL WHERE id = ?", (terminal_id,))
    conn.commit()
    conn.close()
    
    log_session_logout(terminal_name)
    return True, "Session arrêtée avec succès"

def tick_all_sessions():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, t.name as terminal_name 
        FROM sessions s
        JOIN terminals t ON s.terminal_id = t.id
        WHERE s.status = 'running'
    ''')
    running_sessions = cursor.fetchall()
    
    now = datetime.now()
    sessions_to_stop = []
    
    for session in running_sessions:
        start_time = datetime.fromisoformat(session['start_time'])
        elapsed = int((now - start_time).total_seconds())
        
        if session['end_time']:
            end_time = datetime.fromisoformat(session['end_time'])
            if now >= end_time:
                sessions_to_stop.append(session['terminal_id'])
                cursor.execute("UPDATE sessions SET time_spent_seconds = duration_mins * 60 WHERE id = ?", (session['id'],))
            else:
                time_spent = int((now - start_time).total_seconds())
                cursor.execute("UPDATE sessions SET time_spent_seconds = ? WHERE id = ?", (min(time_spent, session['duration_mins'] * 60), session['id']))
        else:
            time_spent = int((now - start_time).total_seconds())
            cursor.execute("UPDATE sessions SET time_spent_seconds = ? WHERE id = ?", (time_spent, session['id']))
            
    conn.commit()
    conn.close()
    
    for term_id in sessions_to_stop:
        stop_session(term_id)

def get_financial_summary():
    conn = get_db()
    cursor = conn.cursor()
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE created_at >= ?", (today_start,))
    today_revenue = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE type = 'ticket_sale' AND created_at >= ?", (today_start,))
    tickets_sold_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM players WHERE status = 'active' AND username NOT IN ('admin_dek', 'caissier_dek')")
    active_players_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(amount) FROM transactions")
    all_time_revenue = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT 10")
    recent_transactions = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'today_revenue': today_revenue,
        'tickets_sold_today': tickets_sold_today,
        'active_players_count': active_players_count,
        'all_time_revenue': all_time_revenue,
        'recent_transactions': recent_transactions
    }

def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return settings

def update_settings(settings_dict):
    conn = get_db()
    cursor = conn.cursor()
    for key, val in settings_dict.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()

def get_report_data(period):
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    if period == 'daily':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        period_label = "Journalier (Aujourd'hui)"
    elif period == 'weekly':
        start_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        period_label = "Hebdomadaire (7 derniers jours)"
    elif period == 'monthly':
        start_date = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        period_label = "Mensuel (30 derniers jours)"
    elif period == 'yearly':
        start_date = datetime(now.year, 1, 1).isoformat()
        period_label = f"Annuel (Année {now.year})"
    else:
        start_date = (now - timedelta(days=1)).isoformat()
        period_label = "Custom"

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE created_at >= ?", (start_date,))
    total_revenue = cursor.fetchone()[0] or 0

    cursor.execute("SELECT type, SUM(amount), COUNT(*) FROM transactions WHERE created_at >= ? GROUP BY type", (start_date,))
    breakdown_rows = cursor.fetchall()
    breakdown = {
        'ticket_sale': {'amount': 0, 'count': 0},
        'player_recharge': {'amount': 0, 'count': 0},
        'session_payment': {'amount': 0, 'count': 0}
    }
    for row in breakdown_rows:
        t = row[0]
        if t in breakdown:
            breakdown[t]['amount'] = row[1] or 0
            breakdown[t]['count'] = row[2] or 0

    cursor.execute("SELECT COUNT(*) FROM sessions WHERE start_time >= ?", (start_date,))
    total_sessions = cursor.fetchone()[0]

    cursor.execute('''
        SELECT t.name, COUNT(s.id) as count, SUM(s.time_spent_seconds) as total_seconds
        FROM sessions s
        JOIN terminals t ON s.terminal_id = t.id
        WHERE s.start_time >= ?
        GROUP BY t.id
        ORDER BY count DESC
        LIMIT 5
    ''', (start_date,))
    popular_terminals = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM transactions WHERE created_at >= ? ORDER BY id DESC", (start_date,))
    transactions = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        'period': period,
        'period_label': period_label,
        'start_date': start_date,
        'end_date': now.isoformat(),
        'total_revenue': total_revenue,
        'breakdown': breakdown,
        'total_sessions': total_sessions,
        'popular_terminals': popular_terminals,
        'transactions': transactions
    }


# --- COUCHE DU SERVEUR WEB FLASK (API-ONLY : React/Electron/Capacitor) ---
# Les routes Jinja legacy (/, /admin, /client/<name>, /admin/*/print) ont ete
# supprimees : le frontend est React (dek-drivsim-pc). Le backend ne sert plus
# que du JSON (/api/*). Cela evite le 500 "template not found" apres le clean
# 9c0cc81 (templates/static supprimes). Voir audit Jellow.

@app.route('/')
def index():
    # API-only : redirige vers le frontend React (hash router) ou renvoie un JSON d'info
    # Pour Electron/Capacitor, le frontend est en file:// ou http://localhost:5173
    return jsonify({'name': 'DEK-DRIVSIM API', 'version': '2.1', 'docs': '/api/health', 'frontend': 'dek-drivsim-pc'})

@app.route('/role-setup')
def role_setup():
    return jsonify({'message': 'Utiliser POST /api/setup-role avec {ip, password}'}), 200

@app.route('/api/setup-role', methods=['POST'])
def api_setup_role():
    data = request.get_json(silent=True) or {}
    password = (data.get('password') or '').strip()
    # L'IP fournie par le client (utile pour Electron/Capacitor) sinon remote_addr
    client_ip = (data.get('ip') or request.remote_addr or '127.0.0.1').strip()

    # Si aucun password fourni mais qu'un rôle est déjà mémorisé -> auto-login
    existing = get_device_role(client_ip)
    if not password and existing in ('admin', 'cashier'):
        return jsonify({'success': True, 'role': existing, 'redirect': f'/{existing}'})

    settings = get_settings()
    admin_pwd = settings.get('admin_password')  # plus de fallback admin123
    cashier_pwd = settings.get('cashier_password', 'caissier123')  # caissier reste caissier123 volontairement

    if admin_pwd and password == admin_pwd:
        set_device_role(client_ip, 'admin')
        return jsonify({'success': True, 'role': 'admin', 'redirect': '/admin'})
    elif password == cashier_pwd:
        set_device_role(client_ip, 'cashier')
        return jsonify({'success': True, 'role': 'cashier', 'redirect': '/cashier'})

    # Pas de rôle mémorisé et password invalide -> message clair
    if not password:
        return jsonify({'success': False, 'message': 'Veuillez saisir votre code d\'activation'})
    return jsonify({'success': False, 'message': 'Code d\'activation incorrect'})

# --- EXPORT CONNECTION LOGS TO CSV ---
@app.route('/admin/connection-logs/csv')
def export_connection_logs_csv():
    client_ip = request.remote_addr
    role = get_device_role(client_ip)
    if role != 'admin':
        return jsonify({'success': False, 'message': 'Non autorise'}), 403
        
    logs = get_all_connection_logs()
    
    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID Log', 'Nom Utilisateur', 'Nom Terminal', 'Type de Session', 'Heure de Connexion', 'Heure de Déconnexion', 'Durée (Mins)'])
    
    for log in logs:
        writer.writerow([
            log['id'],
            log['username'],
            log['terminal_name'],
            log['session_type'].upper(),
            log['login_time'].replace('T', ' '),
            log['logout_time'].replace('T', ' ') if log['logout_time'] else 'EN COURS',
            log['duration_mins']
        ])
        
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=journal_connexions_dek_drivsim.csv"}
    )

# --- API ENDPOINTS ---

@app.route('/api/terminals', methods=['GET'])
def api_get_terminals():
    tick_all_sessions() # Update sessions with elapsed time
    terminals = get_all_terminals()
    return jsonify(terminals)

@app.route('/api/terminal/<int:terminal_id>', methods=['GET'])
def api_get_terminal(terminal_id):
    term = get_terminal(terminal_id)
    if term:
        return jsonify(term)
    return jsonify({'error': 'Poste introuvable'}), 404

@app.route('/api/terminal/<int:terminal_id>/start', methods=['POST'])
def api_start_session(terminal_id):
    data = request.json or {}
    session_type = data.get('session_type') # 'ticket', 'player', 'postpaid', 'driving_school'
    
    if session_type == 'ticket':
        code = data.get('code')
        if not code:
            return jsonify({'success': False, 'message': 'Code ticket requis'}), 400
        success, msg_or_id = start_ticket_session(terminal_id, code)
        return jsonify({'success': success, 'message': msg_or_id if not success else 'Session lancée avec succès'})
        
    elif session_type == 'player':
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'success': False, 'message': 'Nom d\'utilisateur et mot de passe requis'}), 400
        success, msg_or_id = start_player_session(terminal_id, username, password)
        return jsonify({'success': success, 'message': msg_or_id if not success else 'Session lancée avec succès'})
        
    elif session_type == 'postpaid':
        success, msg_or_id = start_postpaid_session(terminal_id)
        return jsonify({'success': success, 'message': msg_or_id if not success else 'Session post-payée démarrée'})
        
    return jsonify({'success': False, 'message': 'Type de session inconnu'}), 400

@app.route('/api/terminal/<int:terminal_id>/pause', methods=['POST'])
def api_pause_session(terminal_id):
    success, msg = pause_session(terminal_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/terminal/<int:terminal_id>/resume', methods=['POST'])
def api_resume_session(terminal_id):
    success, msg = resume_session(terminal_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/terminal/<int:terminal_id>/stop', methods=['POST'])
def api_stop_session(terminal_id):
    success, msg = stop_session(terminal_id)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/tick', methods=['POST', 'GET'])
def api_tick():
    tick_all_sessions()
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/client/status/<name>', methods=['GET'])
def api_client_status(name):
    tick_all_sessions()
    ip_addr = request.remote_addr
    
    term = get_terminal_by_name(name)
    if not term:
        conn = get_db()
        cursor = conn.cursor()
        term_type = 'Console' if any(x in name.upper() for x in ['CONSOLE', 'PS', 'XBOX', 'NINTENDO']) else 'PC'
        cursor.execute("INSERT OR IGNORE INTO terminals (name, type) VALUES (?, ?)", (name, term_type))
        conn.commit()
        conn.close()
        term = get_terminal_by_name(name)
        
    ping_terminal(name, ip_addr)
        
    response = {
        'id': term['id'],
        'name': term['name'],
        'status': term['status'],
        'session_type': term['session_type'],
        'duration_mins': term['duration_mins'],
        'time_spent_seconds': term['time_spent_seconds'],
        'start_time': term['start_time'],
        'end_time': term['end_time']
    }
    
    if term['status'] in ['occupied', 'paused'] and term['session_type'] in ['ticket', 'player', 'driving_school', 'admin', 'cashier']:
        total_seconds = term['duration_mins'] * 60
        remaining = total_seconds - term['time_spent_seconds']
        response['remaining_seconds'] = max(0, remaining)
    elif term['status'] in ['occupied', 'paused'] and term['session_type'] == 'postpaid':
        response['remaining_seconds'] = -1
        
    if term['session_type'] in ['player', 'driving_school', 'admin', 'cashier'] and term['reference_id']:
        if term['session_type'] in ['player', 'admin', 'cashier']:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM players WHERE id = ?", (term['reference_id'],))
            row = cursor.fetchone()
            response['username'] = row['username'] if row else "Joueur"
            conn.close()
        else:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT school_name FROM driving_schools WHERE id = ?", (term['reference_id'],))
            row = cursor.fetchone()
            response['username'] = f"Auto-École {row['school_name']}" if row else "Auto-École"
            conn.close()
    elif term['session_type'] == 'ticket' and term['reference_id']:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM tickets WHERE id = ?", (term['reference_id'],))
        row = cursor.fetchone()
        if row:
            response['username'] = f"Ticket {row['code']}"
        conn.close()
    else:
        response['username'] = "Session Directe"
        
    return jsonify(response)

@app.route('/api/client/unlock/<name>', methods=['POST'])
def api_client_unlock(name):
    data = request.json or {}
    unlock_type = data.get('unlock_type') # 'ticket' or 'player'
    
    term = get_terminal_by_name(name)
    if not term:
        return jsonify({'success': False, 'message': 'Poste non configuré'}), 404
        
    if term['status'] != 'free':
        return jsonify({'success': False, 'message': 'Ce poste est déjà occupé'}), 400
        
    if unlock_type == 'ticket':
        code = data.get('code')
        if not code:
            return jsonify({'success': False, 'message': 'Veuillez saisir un code ticket'}), 400
        success, msg_or_id = start_ticket_session(term['id'], code.upper().strip())
        return jsonify({'success': success, 'message': msg_or_id if not success else 'Session activée'})
        
    elif unlock_type == 'player':
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'success': False, 'message': 'Veuillez saisir votre identifiant et mot de passe'}), 400
        success, msg_or_id = start_player_session(term['id'], username.strip(), password)
        return jsonify({'success': success, 'message': msg_or_id if not success else 'Session activée'})
        
    return jsonify({'success': False, 'message': 'Méthode d\'authentification inconnue'}), 400

@app.route('/api/client/admin-login', methods=['POST'])
def api_client_admin_login():
    data = request.get_json(silent=True) or {}
    password = data.get('password')
    settings = get_settings()
    admin_pwd = settings.get('admin_password')
    if admin_pwd and password == admin_pwd:
        return jsonify({'success': True, 'message': 'Authentification réussie'})
    return jsonify({'success': False, 'message': 'Mot de passe administrateur incorrect'})

@app.route('/api/tickets', methods=['GET'])
def api_get_tickets():
    status = request.args.get('status')
    tickets = get_tickets(status)
    return jsonify(tickets)

@app.route('/api/tickets/generate', methods=['POST'])
def api_generate_tickets():
    data = request.get_json(silent=True) or {}
    try:
        count = max(1, min(50, int(data.get('count', 10))))
        duration = int(data.get('duration', data.get('duration_mins', 60)))
        price = int(data.get('price', 500))
        if duration <= 0 or price < 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Paramètres invalides'}), 400
    tickets = generate_tickets(count, duration, price)
    return jsonify({'success': True, 'tickets_count': len(tickets), 'tickets': tickets})

# Alias compat React (anciens noms)
@app.route('/api/schools', methods=['GET'])
def api_get_schools_alias():
    return jsonify(get_driving_schools())

@app.route('/api/referrals', methods=['GET'])
def api_get_referrals_alias():
    return jsonify(get_all_referrals())

@app.route('/api/cashier-evaluations', methods=['GET'])
def api_get_evals_alias():
    return jsonify(get_cashier_evaluations())

@app.route('/api/connection-logs', methods=['GET'])
def api_get_logs_alias():
    return jsonify(get_all_connection_logs())

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    return jsonify(get_settings())

@app.route('/api/players', methods=['GET'])
def api_get_players():
    players = get_players()
    return jsonify(players)

@app.route('/api/players/create', methods=['POST'])
def api_create_player():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    balance = int(data.get('balance', 0))
    referred_by_code = data.get('referred_by_code', '').strip() or None
    driving_school_id = data.get('driving_school_id') or None
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Nom d\'utilisateur et mot de passe requis'}), 400
        
    success = create_player(username, password, balance, referred_by_code, driving_school_id)
    if success:
        return jsonify({'success': True, 'message': f'Joueur {username} créé avec succès'})
    return jsonify({'success': False, 'message': 'Ce nom d\'utilisateur existe déjà'})

@app.route('/api/players/<int:player_id>/recharge', methods=['POST'])
def api_recharge_player(player_id):
    data = request.json or {}
    amount = int(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Le montant de recharge doit être supérieur à 0'}), 400
        
    success = recharge_player(player_id, amount)
    if success:
        return jsonify({'success': True, 'message': 'Compte rechargé avec succès'})
    return jsonify({'success': False, 'message': 'Joueur non trouvé'}), 404

@app.route('/api/schools/create', methods=['POST'])
def api_create_school():
    data = request.json or {}
    name = data.get('school_name', '').strip()
    instructor = data.get('instructor_name', '').strip()
    rate = int(data.get('special_hourly_rate', 300))
    balance = int(data.get('balance', 0))
    
    if not name or not instructor:
        return jsonify({'success': False, 'message': 'Champs obligatoires manquants'}), 400
        
    success = create_driving_school(name, instructor, rate, balance)
    if success:
        return jsonify({'success': True, 'message': f'Auto-École {name} créée'})
    return jsonify({'success': False, 'message': 'Ce nom d\'Auto-École existe déjà'})

@app.route('/api/schools/<int:school_id>/recharge', methods=['POST'])
def api_recharge_school(school_id):
    data = request.json or {}
    amount = int(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Montant invalide'}), 400
        
    success = recharge_driving_school(school_id, amount)
    if success:
        return jsonify({'success': True, 'message': 'Compte crédité'})
    return jsonify({'success': False, 'message': 'Auto-École introuvable'}), 404

@app.route('/api/schools/<int:school_id>', methods=['DELETE'])
def api_delete_school(school_id):
    delete_driving_school(school_id)
    return jsonify({'success': True, 'message': 'Compte supprimé'})

@app.route('/api/referrals/<int:ref_id>/claim', methods=['POST'])
def api_claim_referral(ref_id):
    claim_referral_bonus(ref_id)
    return jsonify({'success': True})

@app.route('/api/cashier/evaluate', methods=['POST'])
def api_evaluate_cashier():
    data = request.json or {}
    day = int(data.get('day_number'))
    rating = int(data.get('rating', 5))
    punctuality = data.get('punctuality', 'good')
    cash = data.get('cash_accuracy', 'exact')
    notes = data.get('notes', '').strip()
    
    submit_cashier_evaluation(day, rating, punctuality, cash, notes)
    return jsonify({'success': True, 'message': f'Évaluation du Jour {day} enregistrée'})

@app.route('/api/games', methods=['GET'])
def api_get_games():
    games = get_all_games()
    return jsonify(games)

@app.route('/api/games/add', methods=['POST'])
def api_add_game():
    data = request.json or {}
    name = data.get('name', '').strip()
    category = data.get('category', '').strip()
    image_url = data.get('image_url', '').strip()
    launch_path = data.get('launch_path', '').strip()
    
    if not name or not category:
        return jsonify({'success': False, 'message': 'Le nom et la catégorie sont obligatoires'}), 400
        
    if not image_url:
        image_url = '/static/images/bg/game-1.jpg'
        
    add_game(name, category, image_url, launch_path)
    return jsonify({'success': True, 'message': 'Jeu ajouté avec succès'})

@app.route('/api/games/<int:game_id>', methods=['DELETE'])
def api_delete_game(game_id):
    delete_game(game_id)
    return jsonify({'success': True, 'message': 'Jeu supprimé du catalogue'})

@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    data = request.get_json(silent=True) or {}
    # Whitelist des clés modifiables
    allowed = {'cyber_name','currency','hourly_rate','wifi_ssid','wifi_password','admin_password','cashier_password','cashier_referral_bonus'}
    filtered = {k: str(v).strip() for k, v in data.items() if k in allowed and str(v).strip()}
    if not filtered:
        return jsonify({'success': False, 'message': 'Aucun paramètre valide'}), 400
    update_settings(filtered)
    return jsonify({'success': True, 'message': 'Paramètres enregistrés'})

@app.route('/api/health', methods=['GET'])
def api_health():
    # Utilise par electron-main.cjs waitForFlask() et par l'APK pour tester la com PC<->APK
    # Ne pas exiger de templates, ne touche pas la DB lourdement
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({'status': 'ok' if db_ok else 'db_error', 'db': 'ok' if db_ok else 'error', 'version': '2.1', 'port': 5000})

@app.route('/api/dashboard/stats', methods=['GET'])
def api_dashboard_stats():
    summary = get_financial_summary()
    terminals = get_all_terminals()
    
    online_count = sum(1 for t in terminals if t['status'] != 'maintenance')
    occupied_count = sum(1 for t in terminals if t['status'] == 'occupied')
    free_count = sum(1 for t in terminals if t['status'] == 'free')
    paused_count = sum(1 for t in terminals if t['status'] == 'paused')
    
    return jsonify({
        'today_revenue': summary['today_revenue'],
        'tickets_sold_today': summary['tickets_sold_today'],
        'active_players_count': summary['active_players_count'],
        'all_time_revenue': summary['all_time_revenue'],
        'recent_transactions': summary['recent_transactions'],
        'online_count': online_count,
        'occupied_count': occupied_count,
        'free_count': free_count,
        'paused_count': paused_count
    })

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    # Lecture publique des settings non sensibles pour l'APK/PC
    # On filtre admin_password/cashier_password (jamais renvoye en clair)
    s = get_settings()
    safe = {k: v for k, v in s.items() if k not in ('admin_password', 'cashier_password')}
    return jsonify(safe)

if __name__ == '__main__':
    # La console Windows utilise cp1252 par défaut : sans ce basculement en UTF-8,
    # le simple affichage de la bannière lève UnicodeEncodeError et tue le serveur.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

    print("\n" + "="*60)
    print("      DEK-DRIVSIM CYBERCAFE - SERVEUR UNIFIE MOBILE  ")
    print("="*60)
    print("-> LE SERVEUR UNIFIE TOURNE SUR LE PORT 5000.")
    print("\n-> AU PREMIER LANCEMENT SUR UN NOUVEL APPAREIL :")
    print("   Ouvrez le navigateur internet de l'appareil (Chrome, etc.)")
    print("   et tapez : http://127.0.0.1:5000")
    print("   Saisissez votre code d'activation pour memoriser le role de l'appareil.")
    print("="*60 + "\n")
    
    # debug=False : le mode debug expose une console d'exécution de code à tout le réseau.
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
