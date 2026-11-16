#!/usr/bin/env python3
"""Webhook de WhatsApp para Divorcio Express Saltillo — v7.

Flujo completo de Divorcio Incausado (texto de Polo, 2026-11-15) con
botones interactivos, formulario paso a paso y máquina de estados por
cliente. Menú 1-9 y resto de respuestas intactos (formato v6).

Solo librería estándar. No guarda ningún token en el código:
  WHATSAPP_TOKEN   token permanente de la API (del enlace seguro)
  PHONE_NUMBER_ID  ID del número en Meta / Administrador de WhatsApp
  VERIFY_TOKEN     token de verificación que se pone en Meta
Los datos bancarios NO van en el bot: el cliente los obtiene por
teléfono o de un asesor humano (decisión de Polo, 2026-11-15).

Notas:
- Las sesiones viven en memoria. En el plan gratis de Render el
  servicio se duerme y al despertar la conversación en curso se
  reinicia: el cliente solo tiene que escribir "hola" y retomar.
- Los botones de WhatsApp permiten máximo 3 por mensaje y títulos
  de máximo 20 caracteres.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

GRAPH_URL = "https://graph.facebook.com/v21.0"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")

LINEA_DIRECTA = "(844) 688-01-88"
WHATSAPP_NUM = "(844) 538-03-91"
OFICINAS = (
    "Blvd. Jesús Valdés Sánchez esquina con Abasolo, Oficina #15, "
    "planta alta, en Plaza Santa Lucía, Saltillo, Coahuila, C.P. 25284."
)


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
    "¡Hola! Gracias por contactar a *Divorcio Express Saltillo* ⚖️\n"
    "¿En qué te podemos ayudar? Responde con un NÚMERO:\n"
    "1️⃣ Divorcio Express (mutuo acuerdo)\n"
    "2️⃣ Divorcio Incausado (cuando NO quiere firmar)\n"
    "3️⃣ Pensión alimenticia (trámite de pensión para menores)\n"
    "4️⃣ Fui demandado/a (requiero atención urgente)\n"
    "5️⃣ No me dejan ver a mis hijos\n"
    "6️⃣ Me llegó citatorio de fiscalía (requiero atención urgente)\n"
    "7️⃣ Quiero denunciar violencia de mi pareja\n"
    "8️⃣ Requiero tramitar mi acta de Divorcio\n"
    "9️⃣ Me gustaría agendar una cita con un abogado\n"
    "Solo escribe el número (1, 2, 3...) y te enviamos la info al instante 👇"
)

# Respuestas del menú 1-9 de Polo (WhatsApp Business, 2026-11-14).
# Sin términos exactos de financiamiento: eso lo explica un asesor.
# La opción 2 ya no usa este texto corto: inicia el flujo Incausado.
ANSWERS = {
    "1": (
        "*Divorcio Exprés* (mutuo acuerdo) ⚖️\n"
        "El proceso más rápido y económico para terminar un matrimonio cuando ambos están de acuerdo. No hay juicio ni conflicto.\n"
        "En Coahuila toma *30-45 días* desde que presentamos la solicitud hasta la sentencia final.\n"
        "¿Quieres agendar una cita? Escríbeme tu nombre."
    ),
    "3": (
        "*Pensión alimenticia* 👶\n"
        "Tus hijos tienen derecho a recibir pensión, y con gusto les ayudamos. "
        "Aún estás a tiempo para que tus hijos reciban parte del aguinaldo.\n\n"
        "*Precio:* $8,500 MXN de contado.\n"
        "También tenemos financiamiento; un asesor te explica las opciones y los pagos.\n\n"
        "¿Quieres que te pase con un asesor? Escríbeme tu nombre."
    ),
    "4": (
        "*Fui demandado/a* 🚨\n"
        "Atención urgente: hay plazos que se cumplen y es importante contestar a tiempo.\n"
        "Te paso con un asesor de Divorcio Express Saltillo. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "5": (
        "*No me dejan ver a mis hijos* 👨‍👧\n"
        "Lo sentimos mucho, sabemos lo difícil que es. Tienes derecho a convivir con tus hijos, y te podemos ayudar a recuperar esa convivencia por la vía legal, de forma honesta y profesional.\n"
        "¿Quieres agendar una cita? Escríbeme tu nombre."
    ),
    "6": (
        "*Citatorio de fiscalía* 🚨\n"
        "Atención urgente: no faltes y no dejes pasar el tiempo, es importante atender el citatorio con un abogado.\n"
        "Te paso con un asesor de Divorcio Express Saltillo. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "7": (
        "*Denunciar violencia de tu pareja* 🛡️\n"
        "Lo primero es tu seguridad. Si estás en peligro en este momento, llama al *911*.\n"
        "Te podemos ayudar a denunciar y a protegerte legalmente.\n"
        "Te paso con un asesor para atención urgente. Escríbeme tu nombre y tu teléfono, por favor."
    ),
    "8": (
        "*Tramitar tu acta de Divorcio* 📄\n"
        "Con gusto te ayudamos a tramitar tu acta de divorcio una vez que salga la sentencia.\n"
        "¿Quieres agendar una cita para revisarlo? Escríbeme tu nombre."
    ),
    "9": (
        "*Agendar una cita con un abogado* 📅\n"
        "Claro, con gusto te agendo. Solo necesito:\n"
        "1. Tu nombre completo\n"
        "2. ¿El divorcio es de mutuo acuerdo? (sí / no / no sé)\n"
        "3. Tu teléfono para confirmarte la cita\n"
        "En cuanto me los pases, le aviso a nuestro equipo."
    ),
}

REQUISITOS = (
    "📋 *Requisitos para tu trámite:*\n"
    "• Acta de matrimonio.\n"
    "• Actas de nacimiento de ambos cónyuges.\n"
    "• Actas de nacimiento de los hijos, aunque sean mayores de edad.\n"
    "• Comprobante de domicilio.\n"
    "• Copia de INE de cualquiera de los cónyuges.\n"
    "No es necesario llevar todos los documentos al momento de realizar el pago. "
    "Solo los que tengas a la mano. Si no los tienes, con posterioridad tu abogado te los pedirá."
)

# El bot NUNCA muestra datos bancarios: un asesor humano los comparte
# con el cliente en el mismo chat, en cuanto el equipo ve la solicitud
# en la app de WhatsApp Business (decisión de Polo, 2026-11-15).
BANK_TEXT = (
    "🏦 Para tu pago por transferencia, un asesor te compartirá los datos "
    "bancarios por aquí mismo en unos momentos.\n"
    "Si prefieres, también puedes llamarnos a la línea directa:\n"
    f"📞 {LINEA_DIRECTA}\n"
    "Cuando hagas la transferencia, incluye tu nombre completo en el concepto "
    "y envíanos la captura para confirmarla sin retrasos."
)

ASESOR_TEXT = (
    "¡Con mucho gusto podemos ayudarte! Si tienes alguna duda adicional o prefieres "
    "recibir atención personalizada de una persona de nuestro equipo, puedes "
    "comunicarte a nuestra línea directa:\n"
    f"📞 {LINEA_DIRECTA}\n"
    "Nuestro equipo te atenderá con gusto y resolverá todas tus dudas."
)

# ---------------------------------------------------------------------------
# Máquina de estados del flujo Incausado (texto de Polo, 2026-11-15)
# SESSIONS[teléfono] = {"stage": str, "data": {...}}
# ---------------------------------------------------------------------------
SESSIONS = {}

FORM_FIELDS = [
    ("f_nombre", "📝 Para empezar el formulario, ¿cuál es tu *nombre completo*?"),
    ("f_expareja", "¿Cuál es el *nombre completo de tu expareja*?"),
    ("f_domicilio", "¿En qué *domicilio o domicilios* puede ser notificada tu expareja?"),
    ("f_hijos", "¿Cómo se llaman tus *hijos y cuántos años tienen*?"),
    ("f_tel", "¿Cuál es *tu número de teléfono*?"),
    ("f_tel_ex", "¿Cuál es el *teléfono de tu expareja*? (Si no lo tienes, escribe *saltar*)"),
    ("f_trabajo", "¿Cuál es el *lugar de trabajo de tu expareja*? (Si no lo sabes, escribe *saltar*)"),
]


def _yes(text):
    t = text.strip().lower()
    if t.startswith("no"):
        return False
    if t in ("sí", "si", "sí.", "si.", "claro", "claro que sí", "de acuerdo", "ok", "sí quiero"):
        return True
    if t.startswith("sí") or t.startswith("si ") or t.startswith("sí,") or t.startswith("si,"):
        return True
    if "estamos de acuerdo" in t or "sí estamos" in t or "si estamos" in t or "creo que sí" in t:
        return True
    return False


def _no(text):
    t = text.strip().lower()
    if t.startswith("no"):
        return True
    return t in ("nel", "para nada", "no quiero", "no creo", "no lo sé", "no se")


def _unknown(text):
    t = text.strip().lower()
    return t in ("no sé", "no se", "no lo sé", "no lo se", "no tengo idea", "desconozco", "no", "no.")


def _skip(text):
    return text.strip().lower() in ("saltar", "no lo tengo", "no lo sé", "no se", "no sé", "ninguno", "-")


def form_summary(data):
    def v(k, default="—"):
        val = data.get(k)
        return val if val else default
    return (
        "📋 *Tu información:*\n"
        f"• Nombre: {v('f_nombre')}\n"
        f"• Expareja: {v('f_expareja')}\n"
        f"• Domicilio para notificar: {v('f_domicilio')}\n"
        f"• Hijos: {v('f_hijos')}\n"
        f"• Tu teléfono: {v('f_tel')}\n"
        f"• Teléfono expareja: {v('f_tel_ex')}\n"
        f"• Trabajo expareja: {v('f_trabajo')}\n"
        "Si algo está mal, escríbeme la corrección. Si todo está bien, continuamos."
    )


def _msg(text, buttons=None):
    """Un mensaje saliente. buttons: lista de (id, título ≤20 caracteres)."""
    m = {"text": text}
    if buttons:
        m["buttons"] = buttons
    return m


def _start_incausado(session):
    session["stage"] = "inc_a"
    session["data"] = {}
    return [
        _msg(
            "⚖️ *Divorcio Incausado* (cuando NO quiere firmar)\n"
            "Sí te puedes divorciar aunque tu pareja no quiera firmar. No necesitas su firma ni su permiso.\n\n"
            "¿Ambas partes están de acuerdo en presentar el divorcio, o solo una persona quiere iniciarlo?",
            buttons=[("inc_acuerdo_si", "Estamos de acuerdo"), ("inc_acuerdo_no", "Solo yo quiero")],
        )
    ]


def handle_message(sender, text):
    """Devuelve la lista de mensajes a enviar a `sender` por `text` recibido."""
    session = SESSIONS.setdefault(sender, {"stage": "menu", "data": {}})
    low = text.strip().lower()

    # --- Atajos globales (valen en cualquier momento del flujo) ---
    if low in ("hola", "buenas", "buenos días", "buenas tardes", "inicio", "menu", "menú", "0"):
        session["stage"] = "menu"
        session["data"] = {}
        return [_msg(MENU)]
    if low in ("privacidad", "aviso de privacidad", "política de privacidad", "politica de privacidad"):
        return [_msg("Claro, aquí puedes ver nuestro aviso de privacidad:\nhttps://divorce-express-chatbot.onrender.com/privacidad")]
    if low in ("ubicación", "ubicacion", "dirección", "direccion", "dónde están", "donde están", "oficinas", "dónde se encuentran"):
        return [_msg("📍 *Nuestras oficinas:*\n" + OFICINAS + "\n\nEn cuanto esté disponible, te compartimos también el enlace de Google Maps.")]
    if low in ("requisitos", "documentos", "qué necesito", "que necesito", "qué documentos"):
        return [_msg(REQUISITOS)]
    if low in ("asesor", "humano", "hablar con alguien", "persona", "hablar con una persona", "quiero hablar con alguien"):
        return [_msg(ASESOR_TEXT)]
    if "asesor" in low or "humano" in low:
        return [_msg(ASESOR_TEXT)]
    if low in ("catalogo", "catálogo", "servicios", "precios", "precio"):
        return [_msg(catalog_text())]
    if low in ("tiempo", "cuánto tarda", "cuanto tarda", "duración", "duracion"):
        return [_msg(
            "En Coahuila toma 30-45 días desde que presentamos la solicitud "
            "hasta la sentencia final. El tiempo exacto depende de tu caso, "
            "por eso te recomendamos agendar una cita para revisarlo."
        )]

    stage = session["stage"]
    data = session["data"]

    # --- Menú principal ---
    if stage == "menu":
        if low == "2" or low == "inc_acuerdo_no":
            return _start_incausado(session)
        if low in ANSWERS:
            return [_msg(ANSWERS[low])]
        if low in ("financiamiento", "financiar", "pagos"):
            return [_msg(
                "Sí, tenemos financiamiento. Pregunta por financiamiento y un "
                "asesor te explica las opciones y los pagos.\n"
                "¿Quieres que te pase con un asesor?"
            )]
        if low in ("cita", "agendar"):
            return [_msg(ANSWERS["9"])]
        return [_msg(
            "Gracias por tu mensaje. Puedes escribir \"hola\" para ver el menú "
            "de opciones (1 a 9), o escribir \"catálogo\" para ver nuestros servicios."
        )]

    # --- A. Identificar la situación ---
    if stage == "inc_a":
        if low == "inc_acuerdo_si" or _yes(text):
            session["stage"] = "menu"
            return [_msg(
                "¡Qué bueno! Si ambos están de acuerdo, el divorcio de mutuo acuerdo es "
                "el proceso más rápido y económico. No hay juicio ni conflicto.\n\n"
                + ANSWERS["1"]
            )]
        # Solo una persona quiere iniciarlo (o no hay acuerdo / no se hablan /
        # no está en la ciudad / se desconoce su paradero / se niega a firmar).
        session["stage"] = "inc_a2"
        return [_msg(
            "¡Entendemos! Cuéntanos un poquito más sobre tu situación. ¿Consideras que, "
            "si lograras comunicarte con tu pareja y le propusieras el divorcio, estaría "
            "dispuesto(a) a llegar a un acuerdo para llevar a cabo el trámite?",
            buttons=[("inc_podria_si", "Sí, creo que sí"), ("inc_podria_no", "No, no creo")],
        )]

    if stage == "inc_a2":
        if low == "inc_podria_si" or _yes(text):
            session["stage"] = "menu"
            return [_msg(
                "¡Qué bueno! Si crees que puede haber acuerdo, el divorcio de mutuo acuerdo "
                "es el camino más rápido y económico.\n\n" + ANSWERS["1"] +
                "\n\nSi de todos modos quieres seguir con el trámite incausado, escríbeme *2*."
            )]
        session["stage"] = "inc_b1"
        return [_msg(
            "Perfecto, no hay ningún problema, podemos continuar con el trámite. "
            "Solo te haré algunas preguntas para definir la estrategia.\n\n"
            "¿Sabes dónde vive tu expareja? Si lo sabes, ¿podrías darnos la dirección?"
        )]

    # --- B. Preguntas para definir la estrategia ---
    if stage == "inc_b1":
        data["domicilio_ex"] = text.strip()
        session["stage"] = "inc_b2"
        return [_msg(
            "¿Tiene familiares, amigos o conocidos en Saltillo, o conoces algún domicilio "
            "o lugar donde pudiera ser localizado(a)?"
        )]

    if stage == "inc_b2":
        if _unknown(text) or "nadie" in low or "ninguno" in low or "ningún" in low:
            data["localizacion"] = "Sin ubicación conocida"
            out = ["No te preocupes, continuamos con el trámite."]
        else:
            data["localizacion"] = text.strip()
            out = [
                "Gracias. Nuestro equipo jurídico valorará si esa ubicación procede para "
                "una notificación legal. No te aseguramos que se pueda emplazar ahí sin "
                "una revisión jurídica."
            ]
        session["stage"] = "inc_b3"
        out.append("¿Sabes si tu expareja tiene un trabajo fijo actualmente y, de ser así, en dónde es?")
        return [_msg("\n\n".join(out))]

    if stage == "inc_b3":
        data["trabajo_ex"] = text.strip()
        session["stage"] = "inc_b4"
        return [_msg(
            "¿Tu expareja actualmente paga pensión alimenticia a tus hijos?",
            buttons=[("inc_pension_si", "Sí"), ("inc_pension_no", "No")],
        )]

    if stage == "inc_b4":
        data["pension"] = "Sí" if (low == "inc_pension_si" or _yes(text)) else "No"
        session["stage"] = "inc_b5"
        return [_msg(
            "¿En algún momento, dentro o fuera de la relación, existió violencia por parte de tu expareja?",
            buttons=[("inc_violencia_si", "Sí"), ("inc_violencia_no", "No")],
        )]

    if stage == "inc_b5":
        if low == "inc_violencia_si" or _yes(text):
            data["violencia"] = "Sí"
            session["stage"] = "inc_b5b"
            return [_msg(
                "Lamentamos mucho lo que viviste. Lo primero es tu seguridad: si estás en "
                "peligro en este momento, llama al *911*.\n\n"
                "¿Cuentas con documentos de la denuncia?",
                buttons=[("inc_denuncia_si", "Sí, los tengo"), ("inc_denuncia_no", "No")],
            )]
        data["violencia"] = "No"
        session["stage"] = "inc_form_0"
        return [_msg(
            "¡Perfecto! Con la información que nos has proporcionado, podemos continuar con "
            "tu trámite de Divorcio Exprés Incausado, incluso si tu expareja no está de "
            "acuerdo o se niega a firmar.\n\n"
            "Para avanzar, necesitamos que nos ayudes completando el siguiente formulario "
            "con algunos datos importantes. Por favor, llena la información solicitada para "
            "que nuestro equipo jurídico pueda revisar tu caso y comenzar con la integración "
            "de tu expediente.\n\n¡Estamos listos para ayudarte!"
        ), _msg(FORM_FIELDS[0][1])]

    if stage == "inc_b5b":
        data["denuncia_docs"] = "Sí" if (low == "inc_denuncia_si" or _yes(text)) else "No"
        session["stage"] = "inc_form_0"
        return [_msg(
            "¡Perfecto! Con la información que nos has proporcionado, podemos continuar con "
            "tu trámite de Divorcio Exprés Incausado, incluso si tu expareja no está de "
            "acuerdo o se niega a firmar.\n\n"
            "Para avanzar, necesitamos que nos ayudes completando el siguiente formulario "
            "con algunos datos importantes. Por favor, llena la información solicitada para "
            "que nuestro equipo jurídico pueda revisar tu caso y comenzar con la integración "
            "de tu expediente.\n\n¡Estamos listos para ayudarte!"
        ), _msg(FORM_FIELDS[0][1])]

    # --- D. Formulario (campo por campo) ---
    if stage.startswith("inc_form_"):
        idx = int(stage.split("_")[-1])
        key, _q = FORM_FIELDS[idx]
        if _skip(text) and key in ("f_tel_ex", "f_trabajo"):
            data[key] = "No proporcionado"
        else:
            data[key] = text.strip()
        idx += 1
        if idx < len(FORM_FIELDS):
            session["stage"] = f"inc_form_{idx}"
            return [_msg(FORM_FIELDS[idx][1])]
        session["stage"] = "inc_pago"
        return [_msg(
            "¡Muchas gracias por proporcionarnos esta información! Ya contamos con los datos "
            "necesarios para continuar con el análisis de tu situación y definir la estrategia "
            "jurídica más conveniente para tu trámite.\n\n" + form_summary(data)
        ), _msg(
            "¿Te gustaría realizar tu pago de contado o prefieres aprovechar nuestros planes de financiamiento?",
            buttons=[("inc_pago_contado", "De contado"), ("inc_pago_fin", "Financiamiento")],
        )]

    # --- E. Modalidad de pago ---
    if stage == "inc_pago":
        if low == "inc_pago_contado" or "contado" in low:
            data["modalidad"] = "contado"
            session["stage"] = "inc_metodo"
            return [_msg(
                "¡Excelente! Nuestro trámite de Divorcio Exprés Incausado es igual de efectivo "
                "que el de mutuo consentimiento. En Divorcio Exprés trabajamos para obtener los "
                "mejores resultados posibles y brindarte una solución jurídica profesional.\n\n"
                "*El costo de tu trámite con pago de contado es de $8,500 pesos.*\n\n"
                "¡Nuestro equipo está listo para ayudarte a recuperar tu tranquilidad y comenzar "
                "una nueva etapa!\n\n"
                "¿Te gustaría realizar tu pago en nuestras oficinas o prefieres hacerlo mediante transferencia bancaria?",
                buttons=[("inc_met_oficinas", "En oficinas"), ("inc_met_transf", "Transferencia")],
            )]
        if low == "inc_pago_fin" or "financiamiento" in low or "financiar" in low:
            data["modalidad"] = "financiamiento"
            session["stage"] = "inc_metodo"
            return [_msg(
                "¡Ok, perfecto! Contamos con excelentes planes de financiamiento para que puedas "
                "comenzar tu trámite sin tener que cubrir el costo total de contado.\n\n"
                "Para iniciar tu trámite de Divorcio Exprés Incausado, únicamente necesitas "
                "realizar un *pago inicial de $3,500 pesos* y con eso comenzamos tu trámite de "
                "forma inmediata.\n\n"
                "¡En Divorcio Exprés te damos facilidades para que puedas comenzar cuanto antes!\n\n"
                "¿Te gustaría realizar tu pago inicial en nuestras oficinas o prefieres hacerlo por transferencia bancaria?",
                buttons=[("inc_met_oficinas", "En oficinas"), ("inc_met_transf", "Transferencia")],
            )]
        return [_msg(
            "¿Te gustaría realizar tu pago de contado o prefieres aprovechar nuestros planes de financiamiento?",
            buttons=[("inc_pago_contado", "De contado"), ("inc_pago_fin", "Financiamiento")],
        )]

    # --- Método de pago ---
    if stage == "inc_metodo":
        if low == "inc_met_oficinas" or "oficina" in low:
            data["metodo"] = "oficinas"
            session["stage"] = "inc_cita"
            return [_msg("¡Perfecto! Mañana te podemos atender con mucho gusto. ¿A qué hora podrías acudir a nuestras oficinas para agendar tu cita?")]
        if low == "inc_met_transf" or "transferencia" in low:
            data["metodo"] = "transferencia"
            session["stage"] = "inc_comprobante"
            return [_msg("¡Perfecto! Puedes realizar tu pago mediante transferencia bancaria.\n\n" + BANK_TEXT)]
        return [_msg(
            "¿Te gustaría realizar tu pago en nuestras oficinas o prefieres hacerlo mediante transferencia bancaria?",
            buttons=[("inc_met_oficinas", "En oficinas"), ("inc_met_transf", "Transferencia")],
        )]

    # --- Comprobante de transferencia ---
    if stage == "inc_comprobante":
        session["stage"] = "inc_cita"
        return [_msg(
            "¡Gracias! En cuanto nos envíes la captura, nuestro equipo verificará el depósito. "
            "No podemos confirmarlo hasta que el despacho lo revise.\n\n"
            "¿Nos podrías indicar qué día y en qué horario tendrías disponibilidad para acudir a nuestras oficinas?"
        )]

    # --- Cita ---
    if stage == "inc_cita":
        if "cuesta" in low or "cuánto" in low or "cuanto" in low or "pagos" in low or "mensual" in low:
            return [_msg(
                "El día que acudas a nuestras oficinas a realizar tu pago inicial, nuestro equipo "
                "te explicará las modalidades y formas de pago disponibles para tu financiamiento. "
                "También te entregaremos el formulario con los requisitos legales necesarios para "
                "definir la mejor estrategia para tu caso.\n\n"
                "¿Qué día y en qué horario podrías acudir?"
            )]
        data["cita"] = text.strip()
        session["stage"] = "inc_llamada"
        modalidad = data.get("modalidad", "contado")
        if modalidad == "financiamiento":
            confirm = (
                "¡Excelente! Tu cita queda agendada. Te esperamos en nuestras oficinas de "
                "Divorcio Exprés Saltillo.\n\n"
                "No es necesario que lleves documentación a tu cita. Nuestro equipo te recibirá "
                "y te entregará una lista con todos los requisitos y documentos necesarios para "
                "integrar tu expediente."
            )
        else:
            confirm = (
                "¡Excelente! Tu cita queda agendada. Te esperamos en nuestras oficinas de "
                "Divorcio Exprés Saltillo.\n\n"
                f"Perfecto, confirmamos que tu trámite de divorcio exprés será de contado y te "
                f"esperamos el día {text.strip()}."
            )
        return [_msg(confirm), _msg(
            "Por último, ¿te gustaría que nuestra asistente te realice una llamada de confirmación unas horas antes de tu cita?",
            buttons=[("inc_llamada_si", "Sí, por favor"), ("inc_llamada_no", "No, gracias")],
        )]

    # --- Llamada de confirmación y despedida ---
    if stage == "inc_llamada":
        session["stage"] = "menu"
        session["data"] = {}
        return [_msg(
            "¡Muchas gracias por confiar en Divorcio Exprés Saltillo! Te esperamos en tu cita. "
            "¡Que tengas un excelente día! ⚖️"
        )]

    # Si algo no encajó, volver al menú.
    session["stage"] = "menu"
    session["data"] = {}
    return [_msg(MENU)]


def _post_graph(phone_id, payload, token):
    headers = {"Content-Type": "application/json"}
    req = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{GRAPH_URL}/{phone_id}/messages",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    if not token:
        try:
            import sys
            sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
            from dynamic_credentials import add_surrogate_to_request
            add_surrogate_to_request(req, "custom.whatsapp-graph", allowed_hosts=["graph.facebook.com"])
        except Exception as e:
            print("Sin token guardado disponible:", e)
            return
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("WhatsApp API:", resp.status, resp.read().decode()[:200])


def send_whatsapp(to, text):
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("PHONE_NUMBER_ID", "1422322744300738")
    if not phone_id:
        print("Sin Phone Number ID: no se envía nada real.")
        print(f"Para {to}: {text}")
        return
    _post_graph(phone_id, {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}, token)


def send_interactive(to, text, buttons):
    """Botones de respuesta rápida (máx. 3, título ≤20 caracteres)."""
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("PHONE_NUMBER_ID", "1422322744300738")
    if not phone_id:
        print("Sin Phone Number ID: no se envía nada real.")
        print(f"Para {to}: {text} | botones: {buttons}")
        return
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "reply",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": bid, "title": title}}
                    for bid, title in buttons[:3]
                ]
            },
        },
    }
    _post_graph(phone_id, payload, token)


def send_messages(to, messages):
    for m in messages:
        if m.get("buttons"):
            send_interactive(to, m["text"], m["buttons"])
        else:
            send_whatsapp(to, m["text"])


# Compatibilidad: el nombre anterior sigue funcionando para pruebas.
def reply_text(message: str) -> str:
    out = handle_message("test", message)
    SESSIONS.pop("test", None)
    return "\n\n".join(m["text"] for m in out)


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
                    if not sender:
                        continue
                    # Texto normal
                    text = msg.get("text", {}).get("body", "")
                    # Respuesta a un botón interactivo
                    if not text and msg.get("type") == "interactive":
                        btn = msg.get("interactive", {}).get("button_reply", {})
                        text = btn.get("id", "") or btn.get("title", "")
                    # Foto (p. ej. captura de transferencia): se trata como
                    # comprobante si el cliente está en esa etapa.
                    if not text and msg.get("type") == "image":
                        text = "[foto recibida]"
                    if text:
                        send_messages(sender, handle_message(sender, text))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
