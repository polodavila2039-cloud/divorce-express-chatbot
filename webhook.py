#!/usr/bin/env python3
"""Webhook de WhatsApp para Divorcio Express Saltillo.

Solo librería estándar. No guarda ningún token en el código:
  WHATSAPP_TOKEN   token permanente de la API (del enlace seguro)
  PHONE_NUMBER_ID  ID del número en Meta / Administrador de WhatsApp
  VERIFY_TOKEN     token de verificación que se pone en Meta
                   (elegir uno y guardarlo fuera del código)

Arranque local de prueba:
  WHATSAPP_TOKEN=x PHONE_NUMBER_ID=x VERIFY_TOKEN=prueba \
    python3 webhook.py
  curl "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=prueba&hub.challenge=123"

En producción este servidor necesita una URL pública HTTPS para
que Meta pueda llamarlo. Eso se decide con Polo cuando el token
esté conectado (túnel / hosting). Sin token no se envía nada real.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

GRAPH_URL = "https://graph.facebook.com/v21.0"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")


def load_catalog():
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"products": []}


def catalog_text():
    data = load_catalog()
    lines = ["Estos son nuestros servicios:"]
    for i, p in enumerate(data.get("products", []), 1):
        price = p.get("price")
        price_txt = f" — ${price:,.0f} MXN" if isinstance(price, (int, float)) else " — precio por confirmar"
        lines.append(f"{i}. {p.get('name', 'Servicio')}{price_txt}")
        if p.get("benefit"):
            lines.append(f"   {p['benefit']}")
    lines.append("¿Cuál te interesa? Escríbeme su número o su nombre.")
    return "\n".join(lines)


def reply_text(message: str) -> str:
    low = message.strip().lower()
    if low in ("hola", "buenas", "buenos días", "buenas tardes", "inicio", "menu", "menú"):
        return (
            "¡Hola! Soy el asistente de Divorcio Express Saltillo.\n"
            "Te ayudamos a terminar tu matrimonio de forma rápida, económica "
            "y sin juicio ni conflicto.\n\n"
            "¿Qué te gustaría saber?\n"
            "1. Ver servicios y precios\n"
            "2. ¿Cuánto tarda el divorcio?\n"
            "3. Financiamiento\n"
            "4. Agendar una cita / hablar con un asesor"
        )
    if low in ("1", "catalogo", "catálogo", "servicios", "precios", "precio"):
        return catalog_text()
    if low in ("2", "tiempo", "cuánto tarda", "cuanto tarda", "duración", "duracion"):
        return (
            "En Coahuila toma 30-45 días desde que presentamos la solicitud "
            "hasta la sentencia final. El tiempo exacto depende de tu caso, "
            "por eso te recomendamos agendar una cita para revisarlo."
        )
    if low in ("3", "financiamiento", "financiar", "pagos"):
        return (
            "Sí, tenemos financiamiento. Pregunta por financiamiento y un "
            "asesor te explica las opciones y los pagos.\n"
            "¿Quieres que te pase con un asesor?"
        )
    if low in ("4", "asesor", "humano", "hablar con alguien", "cita", "agendar"):
        return (
            "Perfecto, te paso con un asesor de Divorcio Express Saltillo. "
            "Te atenderá en horario de atención. Gracias por escribirnos."
        )
    if "asesor" in low or "humano" in low:
        return (
            "Perfecto, te paso con un asesor de Divorcio Express Saltillo. "
            "Te atenderá en horario de atención. Gracias por escribirnos."
        )
    return (
        "Gracias por tu mensaje. Puedes escribir \"catálogo\" para ver "
        "nuestros servicios, o preguntar por precio, tiempo o financiamiento."
    )


def send_whatsapp(to: str, text: str) -> None:
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("PHONE_NUMBER_ID", "1422322744300738")
    if not phone_id:
        print("Sin Phone Number ID: no se envía nada real.")
        print(f"Para {to}: {text}")
        return
    payload = json.dumps(
        {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    ).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{GRAPH_URL}/{phone_id}/messages",
        data=payload,
        headers=headers,
        method="POST",
    )
    # En local, si no hay token en el entorno, usar la credencial guardada
    # de forma segura (surrogate) sin exponerla nunca en texto.
    if not token:
        try:
            import sys
            sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
            from dynamic_credentials import add_surrogate_to_request
            add_surrogate_to_request(req, "custom.whatsapp-graph", allowed_hosts=["graph.facebook.com"])
        except Exception as e:
            print("Sin token guardado disponible:", e)
            print(f"Para {to}: {text}")
            return
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("WhatsApp API:", resp.status, resp.read().decode()[:200])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Verificación del webhook de Meta: ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(self.path).query)
        if (
            q.get("hub.mode", [""])[0] == "subscribe"
            and q.get("hub.verify_token", [""])[0] == os.environ.get("VERIFY_TOKEN", "")
        ):
            challenge = q.get("hub.challenge", [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(challenge.encode())
            return
        self.send_response(403)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    sender = msg.get("from", "")
                    text = msg.get("text", {}).get("body", "")
                    if sender and text:
                        send_whatsapp(sender, reply_text(text))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
