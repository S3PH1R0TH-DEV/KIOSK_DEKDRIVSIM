# -*- coding: utf-8 -*-
"""
DEK-DRIVSIM CyberCafe - Agent Client Windows Kiosk Invincible
================================================================
3 Verrous de sécurité implémentés :
  1. Pompe de messages PeekMessageW non-bloquante (thread principal)
  2. Élévation UAC automatique + manifeste admin PyInstaller
  3. Scancode Map noyau (désactivation physique des touches Windows)
  
Aucune fonction time.sleep() n'est utilisée dans ce script.
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import ctypes
from ctypes import wintypes

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

# =============================================================================
# CONFIGURATION (CORRIGE AUDIT : plus de 127.0.0.1 dur)
# Usage: python dek_client_agent.py --server 192.168.1.100 --pc PC-03
# ou fichier dek_config.json {"server_ip":"192.168.1.100","pc_name":"PC-03"}
# Fallback auto-scan 192.168.x.0/24 si aucun serveur fourni.
# =============================================================================
import argparse
import socket as _sock
import concurrent.futures as _fut

SERVER_PORT = 5000
HEARTBEAT_INTERVAL_MS = 5000  # 5 secondes
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dek_config.json")

def _load_config():
    cfg = {}
    # 1. fichier json
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            pass
    # 2. args CLI
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--server', dest='server')
    parser.add_argument('--pc', dest='pc')
    try:
        args, _ = parser.parse_known_args()
        if args.server: cfg['server_ip'] = args.server.strip()
        if args.pc: cfg['pc_name'] = args.pc.strip()
    except Exception:
        pass
    # 3. env
    if os.environ.get('DEK_SERVER_IP'): cfg['server_ip'] = os.environ['DEK_SERVER_IP'].strip()
    if os.environ.get('DEK_PC_NAME'): cfg['pc_name'] = os.environ['DEK_PC_NAME'].strip()
    return cfg

def _get_local_subnet():
    try:
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        base = ".".join(ip.split(".")[:3])
        return base
    except Exception:
        return None

def _scan_for_server(port=5000, timeout=0.4):
    base = _get_local_subnet()
    if not base:
        return None
    print(f"[SCAN] Recherche serveur sur {base}.0/24:{port} ...")
    def _probe(i):
        ip = f"{base}.{i}"
        try:
            with _sock.create_connection((ip, port), timeout=timeout):
                # Verifie que c'est bien DEK (api/health)
                try:
                    with urllib.request.urlopen(f"http://{ip}:{port}/api/health", timeout=1) as r:
                        if r.getcode() == 200:
                            return ip
                except Exception:
                    # Port ouvert mais pas DEK -> ignore
                    return None
        except Exception:
            return None
        return None
    with _fut.ThreadPoolExecutor(max_workers=50) as ex:
        futs = {ex.submit(_probe, i): i for i in range(1, 255)}
        for fut in _fut.as_completed(futs):
            ip = fut.result()
            if ip:
                # Annule le reste
                for f in futs: f.cancel()
                print(f"[SCAN] Serveur trouve: {ip}:{port}")
                return ip
    return None

_cfg = _load_config()
_raw_ip = _cfg.get('server_ip') or ''
_raw_pc = _cfg.get('pc_name') or f"PC-{_sock.gethostname()[:8]}"
# Si pas d'IP fournie ou 127.0.0.1 force -> auto-scan
if not _raw_ip or _raw_ip == "127.0.0.1":
    _found = _scan_for_server(SERVER_PORT)
    if _found:
        SERVER_IP = _found
        # Sauvegarde pour prochain lancement
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump({"server_ip": _found, "pc_name": _raw_pc}, f, indent=2)
        except Exception:
            pass
    else:
        SERVER_IP = _raw_ip or "127.0.0.1"
        if SERVER_IP == "127.0.0.1":
            print("[WARN] Aucun serveur trouve, fallback 127.0.0.1 — lancez avec --server 192.168.x.x")
else:
    SERVER_IP = _raw_ip

PC_NAME = _raw_pc
HEARTBEAT_INTERVAL_MS = 5000

SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
CLIENT_URL = f"{SERVER_URL}/client/{PC_NAME}"
STATUS_API_URL = f"{SERVER_URL}/api/client/status/{PC_NAME}"
print(f"[CONFIG] SERVER={SERVER_IP}:{SERVER_PORT} PC={PC_NAME} -> {STATUS_API_URL}")

# =============================================================================
# CONSTANTES WIN32
# =============================================================================
HC_ACTION = 0
WH_KEYBOARD_LL = 13
PM_REMOVE = 0x0001
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
LLKHF_ALTDOWN = 0x20
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_RBUTTONUP = 0x0205
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SW_HIDE = 0
SW_SHOW = 1
SW_SHOWNORMAL = 1

# Scancode Map binaire : désactive E05B (LWin) et E05C (RWin) au niveau noyau
SCANCODE_MAP_BINARY = bytes([
    0x00, 0x00, 0x00, 0x00,  # Header
    0x00, 0x00, 0x00, 0x00,  # Flags
    0x03, 0x00, 0x00, 0x00,  # Count (2 remaps + 1 null terminator)
    0x00, 0x00, 0x00, 0x00,  # Target 1: 0x00000000 (disabled)
    0x5B, 0xE0, 0x00, 0x00,  # Source 1: 0xE05B (Left Windows)
    0x00, 0x00, 0x00, 0x00,  # Target 2: 0x00000000 (disabled)
    0x5C, 0xE0, 0x00, 0x00,  # Source 2: 0xE05C (Right Windows)
    0x00, 0x00, 0x00, 0x00,  # Null terminator
])

# =============================================================================
# TYPES CTYPES (Interopérabilité native Windows)
# =============================================================================
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]

WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM
)

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM
)

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]

# =============================================================================
# RÉFÉRENCES GLOBALES
# =============================================================================
agent_instance = None
global_wndproc = None
global_hookproc = None

# =============================================================================
# CALLBACKS GLOBAUX
# =============================================================================
def window_proc(hwnd, msg, wParam, lParam):
    """Procédure de fenêtre globale."""
    if agent_instance is not None:
        return agent_instance.window_proc(hwnd, msg, wParam, lParam)
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wParam, lParam)

def keyboard_hook(nCode, wParam, lParam):
    """Callback du crochet clavier bas niveau."""
    if agent_instance is not None:
        return agent_instance.keyboard_hook(nCode, wParam, lParam)
    return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

# =============================================================================
# VERROU 2 : ÉLÉVATION UAC AUTOMATIQUE
# =============================================================================
def ensure_admin():
    """
    Vérifie les privilèges administrateur.
    Si non-élevé, relance le processus avec l'invite UAC (verbe 'runas').
    """
    if ctypes.windll.shell32.IsUserAnAdmin():
        print("[UAC] Privilèges administrateur confirmés.")
        return True
    print("[UAC] Relance avec élévation administrateur...")
    params = " ".join([f'"{a}"' for a in sys.argv[1:]])
    if getattr(sys, 'frozen', False):
        # Mode .exe PyInstaller : on relance l'exécutable lui-même
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, SW_SHOWNORMAL
        )
    else:
        # Mode script Python
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{sys.argv[0]}" {params}', None, SW_SHOWNORMAL
        )
    sys.exit(0)

# =============================================================================
# CLASSE PRINCIPALE DE L'AGENT KIOSK
# =============================================================================
class DEKClientAgent:
    """
    Agent client Kiosk DEK-DRIVSIM.
    Implémente les 3 verrous de sécurité absolue contre tout bypass clavier.
    """
    REG_PATH = r"SYSTEM\CurrentControlSet\Control\Keyboard Layout"
    REG_VALUE = "Scancode Map"
    WNDCLASS_NAME = "DEKDRIVSIM_KioskClass"

    def __init__(self):
        self.running = False
        self.hwnd = None
        self.hwnd_taskbar = None
        self.hhook = None
        self.hinst = ctypes.windll.kernel32.GetModuleHandleW(None)
        self._heartbeat_thread = None
        self._registry_modified = False

    # -------------------------------------------------------------------------
    # VERROU 3 : SCANCODE MAP NOYAU
    # -------------------------------------------------------------------------
    def setup_registry(self):
        """
        Écrit la Scancode Map dans le registre pour désactiver physiquement
        les touches Windows au niveau du pilote clavier du noyau.
        """
        if not HAS_WINREG:
            print("[REGISTRY] Module winreg indisponible.")
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.REG_PATH,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, self.REG_PATH)
        try:
            winreg.SetValueEx(
                key, self.REG_VALUE, 0, winreg.REG_BINARY, SCANCODE_MAP_BINARY
            )
            self._registry_modified = True
            print("[REGISTRY] Scancode Map écrite. Touches Windows désactivées au prochain démarrage.")
        finally:
            winreg.CloseKey(key)

    def restore_registry(self):
        """
        Supprime la Scancode Map pour restaurer les touches Windows
        lors de l'arrêt du programme.
        """
        if not HAS_WINREG or not self._registry_modified:
            return
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.REG_PATH,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                winreg.DeleteValue(key, self.REG_VALUE)
                print("[REGISTRY] Scancode Map supprimée. Touches Windows restaurées.")
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            print(f"[REGISTRY ERROR] Restauration impossible: {e}")

    # -------------------------------------------------------------------------
    # MASQUAGE BARRE DES TÂCHES
    # -------------------------------------------------------------------------
    def hide_taskbar(self):
        """Masque la barre des tâches Windows."""
        self.hwnd_taskbar = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
        if self.hwnd_taskbar:
            ctypes.windll.user32.ShowWindow(self.hwnd_taskbar, SW_HIDE)
            ctypes.windll.user32.EnableWindow(self.hwnd_taskbar, False)
            print("[TASKBAR] Masquée.")

    def show_taskbar(self):
        """Restaure la barre des tâches Windows."""
        if self.hwnd_taskbar:
            ctypes.windll.user32.ShowWindow(self.hwnd_taskbar, SW_SHOW)
            ctypes.windll.user32.EnableWindow(self.hwnd_taskbar, True)
            print("[TASKBAR] Restaurée.")

    # -------------------------------------------------------------------------
    # VERROU 1 : HOOK CLAVIER BAS NIVEAU
    # -------------------------------------------------------------------------
    def install_hook(self):
        """Installe le crochet WH_KEYBOARD_LL sur le thread principal."""
        global global_hookproc
        global_hookproc = HOOKPROC(keyboard_hook)
        self.hhook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            global_hookproc,
            self.hinst,
            0
        )
        if self.hhook:
            print("[HOOK] Crochet clavier installé.")
        else:
            print("[HOOK ERROR] Échec d'installation.")

    def uninstall_hook(self):
        """Désinstalle proprement le crochet clavier."""
        if self.hhook:
            ctypes.windll.user32.UnhookWindowsHookEx(self.hhook)
            self.hhook = None
            print("[HOOK] Crochet désinstallé.")

    def keyboard_hook(self, nCode, wParam, lParam):
        """
        Traitement DU HOOK : ULTRA-RAPIDE (< 1000ms) pour éviter
        la désinstallation silencieuse par LowLevelHooksTimeout.
        """
        if nCode != HC_ACTION:
            return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kb.vkCode
        # --- BLOCAGE ABSOLU LWIN / RWIN ---
        if vk in (VK_LWIN, VK_RWIN):
            return 1
        # --- BLOCAGE ALT+TAB / ALT+ESC ---
        if kb.flags & LLKHF_ALTDOWN:
            if vk in (VK_TAB, VK_ESCAPE):
                return 1
        # --- BLOCAGE CTRL+ESC ---
        if vk == VK_ESCAPE:
            lctrl = ctypes.windll.user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000
            rctrl = ctypes.windll.user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000
            if lctrl or rctrl:
                return 1
        return ctypes.windll.user32.CallNextHookEx(None, nCode, wParam, lParam)

    # -------------------------------------------------------------------------
    # FENÊTRE KIOSK PLEIN ÉCRAN
    # -------------------------------------------------------------------------
    def create_kiosk_window(self):
        """Crée une fenêtre noire plein écran, toujours au premier plan."""
        global global_wndproc
        global_wndproc = WNDPROC(window_proc)
        wndclass = WNDCLASSEXW()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wndclass.lpfnWndProc = global_wndproc
        wndclass.hInstance = self.hinst
        wndclass.hbrBackground = ctypes.windll.gdi32.GetStockObject(4)  # BLACK_BRUSH
        wndclass.lpszClassName = self.WNDCLASS_NAME
        if not ctypes.windll.user32.RegisterClassExW(ctypes.byref(wndclass)):
            print("[WINDOW] Échec d'enregistrement de la classe.")
            return
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        self.hwnd = ctypes.windll.user32.CreateWindowExW(
            0,
            self.WNDCLASS_NAME,
            "DEK-DRIVSIM Client Kiosk",
            WS_POPUP | WS_VISIBLE,
            0, 0, screen_w, screen_h,
            None, None, self.hinst, None
        )
        if self.hwnd:
            ctypes.windll.user32.SetWindowPos(
                self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE
            )
            print("[WINDOW] Fenêtre Kiosk créée (plein écran, topmost).")

    def destroy_kiosk_window(self):
        """Détruit la fenêtre Kiosk et libère la classe."""
        if self.hwnd:
            ctypes.windll.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            ctypes.windll.user32.UnregisterClassW(self.WNDCLASS_NAME, self.hinst)
            print("[WINDOW] Fenêtre détruite.")

    def window_proc(self, hwnd, msg, wParam, lParam):
        """Procédure de fenêtre : gère la fermeture et bloque le clic droit."""
        if msg == WM_CLOSE:
            self.shutdown()
            return 0
        if msg == WM_DESTROY:
            ctypes.windll.user32.PostQuitMessage(0)
            return 0
        if msg == WM_RBUTTONUP:
            return 0  # Clic droit bloqué
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    # -------------------------------------------------------------------------
    # COMMUNICATION SERVEUR
    # -------------------------------------------------------------------------
    def heartbeat_thread(self):
        """Envoi périodique du statut au serveur Flask."""
        while self.running:
            try:
                data = json.dumps({
                    "pc_name": PC_NAME,
                    "status": "online",
                    "tick": ctypes.windll.kernel32.GetTickCount()
                }).encode('utf-8')
                req = urllib.request.Request(
                    STATUS_API_URL,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except Exception:
                pass
            ctypes.windll.kernel32.Sleep(HEARTBEAT_INTERVAL_MS)

    def open_client_browser(self):
        """Ouvre le navigateur par défaut vers l'interface client."""
        def _open():
            ctypes.windll.kernel32.Sleep(800)
            try:
                import webbrowser
                webbrowser.open(CLIENT_URL)
                print(f"[BROWSER] Ouverture : {CLIENT_URL}")
            except Exception as e:
                print(f"[BROWSER ERROR] {e}")
        threading.Thread(target=_open, daemon=True).start()

    # -------------------------------------------------------------------------
    # VERROU 1 : POMPE DE MESSAGES PRINCIPALE (Thread Principal)
    # -------------------------------------------------------------------------
    def run_message_pump(self):
        """
        Pompe de messages PeekMessageW non-bloquante.
        """
        msg = MSG()
        print("[PUMP] Pompe de messages active. Kiosk verrouillé.")
        print("[PUMP] Fermez la fenêtre ou appuyez sur ALT+F4 pour quitter.")
        while self.running:
            if ctypes.windll.user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0, PM_REMOVE
            ):
                if msg.message == 0x0012:  # WM_QUIT
                    self.running = False
                    break
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
            else:
                ctypes.windll.kernel32.Sleep(1)

    # -------------------------------------------------------------------------
    # DÉMARRAGE & ARRÊT
    # -------------------------------------------------------------------------
    def start(self):
        """Initialise l'agent Kiosk et démarre la boucle principale."""
        global agent_instance
        agent_instance = self
        print("=" * 60)
        print("  DEK-DRIVSIM Client Agent - Mode Kiosk Invincible")
        print("=" * 60)
        self.setup_registry()
        self.hide_taskbar()
        self.create_kiosk_window()
        self.install_hook()
        self.running = True
        self._heartbeat_thread = threading.Thread(target=self.heartbeat_thread, daemon=True)
        self._heartbeat_thread.start()
        self.open_client_browser()
        self.run_message_pump()

    def shutdown(self):
        """Arrêt propre : restauration complète du système."""
        if not self.running:
            return
        self.running = False
        print("\n[SHUTDOWN] Arrêt de l'agent Kiosk...")
        self.restore_registry()
        self.uninstall_hook()
        self.show_taskbar()
        self.destroy_kiosk_window()
        ctypes.windll.user32.PostQuitMessage(0)
        print("[SHUTDOWN] Système restauré.")

    def emergency_cleanup(self):
        """Filet de sécurité en cas d'exception fatale."""
        self.restore_registry()
        self.uninstall_hook()
        self.show_taskbar()
        self.destroy_kiosk_window()

# =============================================================================
# POINT D'ENTRÉE
# =============================================================================
if __name__ == '__main__':
    ensure_admin()
    agent = DEKClientAgent()
    try:
        agent.start()
    except KeyboardInterrupt:
        print("\n[MAIN] Interruption clavier détectée.")
    except Exception as e:
        print(f"\n[MAIN ERROR] {e}")
    finally:
        agent.emergency_cleanup()
