# -*- coding: utf-8 -*-
"""
Test d'intégration : démarre réellement le serveur Flask puis interroge ses routes.

Fonctionne sous Windows comme sous Linux : la version précédente utilisait
preexec_fn=os.setsid et os.killpg, qui n'existent que sur Unix et faisaient
échouer le test avec AttributeError sur la machine de développement.
"""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOST = "127.0.0.1"
PORT = 5000
BASE = f"http://{HOST}:{PORT}"
BOOT_TIMEOUT = 30.0

ROUTES = [
    ("Accueil", "/"),
    ("Console Administration", "/admin"),
    ("Locker PC Client", "/client/PC-01"),
    ("Impression Tickets", "/admin/tickets/print"),
    ("Impression Rapport Journalier", "/admin/reports/print?period=daily"),
    ("Impression Rapport Hebdomadaire", "/admin/reports/print?period=weekly"),
    ("Impression Rapport Mensuel", "/admin/reports/print?period=monthly"),
    ("Impression Rapport Annuel", "/admin/reports/print?period=yearly"),
    ("API Terminals", "/api/terminals"),
    ("API Client Status", "/api/client/status/PC-01"),
]


def wait_for_port(timeout=BOOT_TIMEOUT):
    """Attend l'ouverture du port plutôt qu'un sleep fixe."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def claim_admin_role():
    """Enregistre 127.0.0.1 comme poste admin, sinon /admin renvoie vers l'activation."""
    payload = json.dumps({"password": "admin123"}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/setup-role", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()).get("success", False)
    except Exception as exc:
        print(f"  (role admin non enregistre : {exc})")
        return False


def test_live_server():
    print("Demarrage du test d'integration du serveur Flask...")

    server_py = Path(__file__).parent / "cybercafe_manager" / "app.py"
    # stdout/stderr vers DEVNULL : avec subprocess.PIPE non lu, le tampon se
    # remplit et le serveur finit par se bloquer en pleine campagne de tests.
    process = subprocess.Popen(
        [sys.executable, str(server_py)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    all_passed = True
    try:
        if not wait_for_port():
            print(f"Le serveur n'a pas ouvert le port {PORT} en {BOOT_TIMEOUT:.0f}s.")
            return 1

        claim_admin_role()

        for name, path in ROUTES:
            url = BASE + path
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    status = response.getcode()
                if status == 200:
                    print(f"[OK]   {name} ({path}) -> HTTP 200")
                else:
                    print(f"[FAIL] {name} ({path}) -> HTTP {status}")
                    all_passed = False
            except Exception as exc:
                print(f"[FAIL] {name} ({path}) -> {exc}")
                all_passed = False
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        print("Serveur de test arrete.")

    if all_passed:
        print("\nTOUTES LES ROUTES DU SERVEUR SONT OPERATIONNELLES.")
        return 0
    print("\nCertains tests d'integration ont echoue.")
    return 1


if __name__ == "__main__":
    sys.exit(test_live_server())
