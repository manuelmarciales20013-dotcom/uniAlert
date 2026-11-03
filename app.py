"""Punto de entrada: python3 app.py."""

import os
import webbrowser
from threading import Timer

from riskmap import create_app

app = create_app()


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "5001"))
    # El recargador ejecuta este archivo dos veces; abrir solo en el proceso inicial.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        navegador = Timer(1.5, webbrowser.open, args=[f"http://127.0.0.1:{puerto}/login"])
        navegador.daemon = True
        navegador.start()
    app.run(host="127.0.0.1", debug=True, port=puerto)
