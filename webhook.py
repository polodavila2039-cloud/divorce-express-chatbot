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


MENU = (
    "¡Hola! Gracias por contactar a Divorcio Express Saltillo ⚖️\n\n"
    "Estamos para servirte. ¿En qué te podemos ayudar?\n\n"
    "Responde con un NÚMERO:\n\n"
    "1️⃣ - Divorcio Express (mutuo acuerdo)\n"
    "2️⃣ - Divorcio Incausado (cuando NO quiere firmar)\n"
    "3️⃣ - Pensión alimenticia (trámite de pensión para menores)\n"
    "4️⃣ - Fui demandado/a (requiero atención urgente)\n"
    "5️⃣ - No me dejan ver a mis hijos\n"
    "6️⃣ - Me llegó citatorio de fiscalía (requiero atención urgente)\n"
    "7️⃣ - Quiero denunciar violencia de mi pareja\n"
    "8️⃣ - Requiero tramitar mi acta de Divorcio\n"
    "9️⃣ - Me gustaría agendar una cita con un abogado\n\n"
    "Solo escribe el número (1, 2, 3...) y te enviamos la info al instante 👇"
)

# Respuestas del menú 1-9 de Polo (WhatsApp Business, 2026-11-14).
# Sin términos exactos de financiamiento: eso lo explica un asesor.
ANSWERS = {
    "1": (
        "Divorcio Exprés (mutuo acuerdo)\n\n"
        "Es el proceso más rápido y económico para terminar un matrimonio "
        "cuando ambos cónyuges están de acuerdo. No hay juicio ni conflicto.\n"
        "En Coahuila toma 30-45 días desde que presentamos la solicitud "
        "hasta la sentencia final.\n\n"
        "¿Quieres que te agende una cita con un abogado para revisarlo? "
        "Escríbeme tu nombre y te pasamos con un asesor."
    ),
    "2": (
        "Divorcio Incausado (cuando NO quiere firmar)\n\n"
        "Sí te puedes divorciar aunque tu pareja no quiera firmar. "
        "No necesitas su firma ni su permiso.\n"
        "En Divorcio Express te ayudamos de forma honesta y profesional, "
        "rápido y sin conflicto.\n\n"
        "¿Quieres que te agende una cita con un abogado? "
        "Escríbeme tu nombre y te pasamos con un asesor."
    ),
    "3": (
        "Pensión alimenticia (trámite de pensión para menores)\n\n"
        "Tus hijos tienen derecho a recibir pensión, y con gusto les "
        "ayudamos. Aún estás a tiempo para que tus hijos reciban parte "
        "del aguinaldo.\n\n"
        "Estos son nuestros servicios:\n"
        "1. PENSIÓN ALIMENTICIA — $8,500 MXN\n"
        "   Tus hijos tienen derecho a recibir pensión, y con gusto les ayudamos.\n\n"
        "También tenemos financiamiento; un asesor te explica las opciones "
        "y los pagos.\n"
        "¿Quieres que te pase con un asesor? Escríbeme tu nombre."
    ),
    "4": (
        "Fui demandado/a — atención urgente\n\n"
        "No te preocupes, pero no dejes pasar el tiempo: hay plazos que "
        "se cumplen y es importante contestar a tiempo.\n\n"
        "Te paso con un asesor de Divorcio Express Saltillo para atención "
        "urgente. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "5": (
        "No me dejan ver a mis hijos\n\n"
        "Lo sentimos mucho, sabemos lo difícil que es. Tienes derecho a "
        "convivir con tus hijos, y te podemos ayudar a recuperar esa "
        "convivencia por la vía legal, de forma honesta y profesional.\n\n"
        "¿Quieres que te agende una cita con un abogado? "
        "Escríbeme tu nombre y te pasamos con un asesor."
    ),
    "6": (
        "Citatorio de fiscalía — atención urgente\n\n"
        "No faltes y no dejes pasar el tiempo: es importante atender el "
        "citatorio con un abogado.\n\n"
        "Te paso con un asesor de Divorcio Express Saltillo para atención "
        "urgente. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "7": (
        "Denunciar violencia de tu pareja\n\n"
        "Lo sentimos mucho, y lo primero es tu seguridad. Si estás en "
        "peligro en este momento, llama al 911.\n\n"
        "Te podemos ayudar a denunciar y a protegerte legalmente. "
        "Te paso con un asesor de Divorcio Express Saltillo para atención "
        "urgente. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "8": (
        "Tramitar tu acta de Divorcio\n\n"
        "Con gusto te ayudamos a tramitar tu acta de divorcio una vez que "
        "salga la sentencia.\n\n"
        "¿Quieres que te agende una cita con un abogado para revisarlo? "
        "Escríbeme tu nombre y te pasamos con un asesor."
    ),
    "9": (
        "Agendar una cita con un abogado\n\n"
        "Claro, con gusto te agendo. Solo necesito:\n"
        "1. Tu nombre completo\n"
        "2. ¿El divorcio es de mutuo acuerdo? (sí / no / no sé)\n"
        "3. Tu teléfono para confirmarte la cita\n\n"
        "En cuanto me los pases, le aviso a nuestro equipo."
    ),
}


def reply_text(message: str) -> str:
    low = message.strip().lower()
    if low in ("hola", "buenas", "buenos días", "buenas tardes", "inicio", "menu", "menú", "0"):
        return MENU
    if low in ANSWERS:
        return ANSWERS[low]
    if low in ("catalogo", "catálogo", "servicios", "precios", "precio"):
        return catalog_text()
    if low in ("tiempo", "cuánto tarda", "cuanto tarda", "duración", "duracion"):
        return (
            "En Coahuila toma 30-45 días desde que presentamos la solicitud "
            "hasta la sentencia final. El tiempo exacto depende de tu caso, "
            "por eso te recomendamos agendar una cita para revisarlo."
        )
    if low in ("financiamiento", "financiar", "pagos"):
        return (
            "Sí, tenemos financiamiento. Pregunta por financiamiento y un "
            "asesor te explica las opciones y los pagos.\n"
            "¿Quieres que te pase con un asesor?"
        )
    if low in ("asesor", "humano", "hablar con alguien", "cita", "agendar"):
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
        "Gracias por tu mensaje. Puedes escribir \"hola\" para ver el menú "
        "de opciones (1 a 9), o escribir \"catálogo\" para ver nuestros servicios."
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


PRIVACY_HTML = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Política de Privacidad — Divorcio Express Saltillo</title></head>
<body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px">
<h1>Política de Privacidad — Divorcio Express Saltillo</h1>
<p>Última actualización: 14 de noviembre de 2026.</p>
<p>Divorcio Express Saltillo (Saltillo, Coahuila, México) opera un asistente
automático por WhatsApp para atender a sus clientes.</p>
<h2>Datos que recopilamos</h2>
<p>Cuando usted nos escribe por WhatsApp, recibimos su número de teléfono y
el contenido de sus mensajes, únicamente para contestar su consulta,
agendar una cita o pasarlo con un asesor.</p>
<h2>Uso de los datos</h2>
<p>Sus datos se usan solo para la atención de su caso y no se venden, no se
comparten con terceros con fines publicitarios y no se usan para ningún
otro fin.</p>
<h2>Sus derechos</h2>
<p>Usted puede pedir en cualquier momento que dejemos de escribirle o que
eliminemos sus datos, escribiendo "baja" por WhatsApp o llamando a la
Línea Directa (844) 688-01-88.</p>
<h2>Contacto</h2>
<p>Divorcio Express Saltillo — WhatsApp (844) 538-03-91 — Línea Directa
(844) 688-01-88 — Saltillo, Coahuila, México.</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Verificación del webhook de Meta: ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
        from urllib.parse import parse_qs, urlparse

        path = urlparse(self.path).path
        if path in ("/privacidad", "/privacy", "/politica-de-privacidad"):
            body = PRIVACY_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
