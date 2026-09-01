# -*- coding: utf-8 -*-
"""
DEK-DRIVSIM CyberCafe - Point d'entrée Android (main.py)

Démarre le serveur Flask dans un thread d'arrière-plan, attend qu'il réponde
réellement, puis bascule l'affichage vers une WebView native Android.

Choix d'architecture volontaires :
  - HTTP en local (pas de HTTPS auto-signé) : Android bloque les certificats
    auto-signés dans la WebView, et le seul moyen de passer outre serait de
    sous-classer WebViewClient, ce que pyjnius ne permet pas (proxy Java =
    interfaces uniquement). Le trafic clair vers 127.0.0.1 est autorisé via
    le network_security_config déclaré dans buildozer.spec.
  - Le serveur écoute sur 0.0.0.0 pour que les postes clients du cybercafé
    puissent l'atteindre sur le Wi-Fi, la WebView passant elle par 127.0.0.1.
  - La WebView n'est créée qu'une fois le serveur confirmé actif : en cas
    d'échec, l'écran Kivy reste affiché avec la cause exacte au lieu d'un
    écran noir.
"""

import os
import socket
import sys
import threading
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
MANAGER_DIR = os.path.join(APP_DIR, 'cybercafe_manager')
sys.path.insert(0, MANAGER_DIR)

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.utils import platform

# --- CONSTANTES ---
FLASK_BIND_HOST = '0.0.0.0'      # accessible depuis les postes clients du réseau
FLASK_HOST = '127.0.0.1'         # adresse utilisée par la WebView embarquée
FLASK_PORT = 5000
FLASK_URL = f"http://{FLASK_HOST}:{FLASK_PORT}/"
STARTUP_TIMEOUT = 40.0
RETRY_DELAY = 0.3

# Trace complète de l'erreur si le serveur meurt au démarrage (import, DB, port occupé...)
SERVER_ERROR = None


def start_flask_server():
    """Démarre Flask. Toute exception est conservée pour être affichée à l'écran."""
    global SERVER_ERROR
    try:
        import app as flask_backend
        print(f"[FLASK] Démarrage sur {FLASK_BIND_HOST}:{FLASK_PORT}")
        flask_backend.app.run(
            host=FLASK_BIND_HOST,
            port=FLASK_PORT,
            debug=False,
            threaded=True,
            use_reloader=False,
        )
    except Exception:
        SERVER_ERROR = traceback.format_exc()
        print(f"[FLASK ERROR]\n{SERVER_ERROR}")


def wait_for_server(timeout=STARTUP_TIMEOUT):
    """Attend que le port réponde. Sort immédiatement si le serveur a planté."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if SERVER_ERROR:
            return False
        try:
            with socket.create_connection((FLASK_HOST, FLASK_PORT), timeout=1.0):
                print("[FLASK] Serveur prêt")
                return True
        except OSError:
            time.sleep(RETRY_DELAY)
    return False


class DEKDRIVSIMApp(App):

    def build(self):
        # Références Java retenues côté Python : pyjnius exige de garder l'objet
        # vivant tant que Java l'utilise, sinon le GC le collecte et l'app plante.
        self._webview = None
        self._webview_client = None

        self.layout = BoxLayout(orientation='vertical', padding=24)
        self.lbl_status = Label(
            text="INITIALISATION DE DEK-DRIVSIM...\n\nCalibrage des simulateurs en cours...",
            font_size='15sp',
            halign='center',
            valign='middle',
        )
        self.lbl_status.bind(size=lambda widget, *_: setattr(widget, 'text_size', widget.size))
        self.layout.add_widget(self.lbl_status)

        threading.Thread(target=start_flask_server, daemon=True).start()

        # Laisse la fenêtre Kivy s'afficher avant de lancer l'attente du serveur.
        Clock.schedule_once(
            lambda _dt: threading.Thread(target=self._boot, daemon=True).start(), 0.5
        )
        return self.layout

    @mainthread
    def _set_status(self, message, error=False):
        self.lbl_status.text = message
        self.lbl_status.color = [1, 0.25, 0.25, 1] if error else [1, 1, 1, 1]

    def _boot(self):
        """Exécuté hors du thread UI : attend le serveur puis bascule l'affichage."""
        if not wait_for_server():
            detail = SERVER_ERROR or (
                "Le serveur local n'a pas répondu dans le délai imparti "
                f"({STARTUP_TIMEOUT:.0f}s)."
            )
            self._set_status(
                "⚠️ ERREUR DE DEMARRAGE DU SERVEUR\n\n" + detail.strip()[-900:], error=True
            )
            return

        if platform == 'android':
            self._show_android_webview()
        else:
            self._open_desktop_browser()

    def _open_desktop_browser(self):
        import webbrowser
        self._set_status(f"Serveur DEK-DRIVSIM actif\n\n{FLASK_URL}\n\nOuverture du navigateur...")
        webbrowser.open(FLASK_URL)

    @mainthread
    def _show_android_webview(self):
        """
        @mainthread est obligatoire ici, ce n'est pas un détail de style.

        run_on_ui_thread construit un proxy Java (Runnable) via pyjnius. Appelé
        depuis un thread créé par threading.Thread, ce proxy échoue sur :

            ClassNotFoundException: org.jnius.NativeInvocationHandler
            DexPathList[[directory "."], nativeLibraryDirectories=[/system/lib64]]

        Un thread Python est attaché à la JVM avec le classloader système, qui
        n'a pas accès au dex de l'application. Le thread principal Kivy, lui,
        est créé côté Java et porte le bon classloader : on y revient d'abord,
        et run_on_ui_thread peut alors instancier ses proxys.
        """
        self._create_android_webview()

    def _create_android_webview(self):
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def create_webview():
            try:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                activity = PythonActivity.mActivity
                WebView = autoclass('android.webkit.WebView')
                WebViewClient = autoclass('android.webkit.WebViewClient')

                webview = WebView(activity)
                settings = webview.getSettings()
                settings.setJavaScriptEnabled(True)
                settings.setDomStorageEnabled(True)
                settings.setDatabaseEnabled(True)
                settings.setAllowFileAccess(True)
                settings.setAllowContentAccess(True)
                settings.setMediaPlaybackRequiresUserGesture(False)
                settings.setUseWideViewPort(True)
                settings.setLoadWithOverviewMode(True)
                settings.setSupportZoom(True)
                settings.setBuiltInZoomControls(True)
                settings.setDisplayZoomControls(False)

                # WebViewClient standard, instancié directement : garde la navigation
                # à l'intérieur de la WebView au lieu de l'ouvrir dans Chrome.
                self._webview_client = WebViewClient()
                webview.setWebViewClient(self._webview_client)
                self._webview = webview

                activity.setContentView(webview)
                webview.loadUrl(FLASK_URL)
                print(f"[WEBVIEW] Chargé : {FLASK_URL}")
            except Exception:
                self._set_status(
                    "⚠️ ERREUR WEBVIEW\n\n" + traceback.format_exc()[-900:], error=True
                )

        create_webview()

    def on_pause(self):
        # Garde l'application (et donc le serveur) en vie quand l'écran s'éteint.
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    DEKDRIVSIMApp().run()
