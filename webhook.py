#!/usr/bin/env python3
"""Webhook de WhatsApp para Divorcio Express Saltillo — v8.

Chatbot de ventas guiado (máquina de estados, sin IA que improvise):
  - Pide el nombre, muestra el menú 1-9 como lista y lleva cada servicio
    con preguntas de botones. Agradece cada dato y sigue preguntando.
  - Cierre por forma de pago (contado / financiamiento), manejo de
    objeciones, oferta especial de $900 con vigencia de 24 horas.
  - Planes de pago calculados desde la tabla PLANES (no se improvisan).
  - Pasa a una persona del equipo SOLO cuando el cliente acepta pagar,
    pide una cita, o es un caso urgente. Después de pasar, el bot guarda
    silencio con ese cliente durante HANDOFF_HOURS.

Solo librería estándar. Variables de entorno (en Render, nunca en el código):
  WHATSAPP_TOKEN   token permanente de la API
  PHONE_NUMBER_ID  ID del número
  VERIFY_TOKEN     token de verificación del webhook
  APP_SECRET       (opcional) valida la firma de Meta en cada aviso
  HANDOFF_HOURS    (opcional) horas de silencio tras pasar a humano; 24
  PUBLIC_URL       (opcional) dirección pública del servicio
"""
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

GRAPH_URL = "https://graph.facebook.com/v21.0"
PUBLIC_URL = os.environ.get("PUBLIC_URL", "https://divorce-express-chatbot.onrender.com").rstrip("/")
HANDOFF_HOURS = float(os.environ.get("HANDOFF_HOURS", "24"))
SESSIONS_PATH = os.environ.get("SESSIONS_PATH", "/tmp/sesiones_chatbot.json")

LINEA = "844 688 0188"
OFICINAS = ("Blvd. Jesús Valdés Sánchez esquina con Abasolo, Plaza Santa Lucía, "
            "segunda planta, oficina 15, Saltillo, Coahuila.")
HORARIO = "lunes a viernes de 9:30 a.m. a 7:00 p.m. y sábados de 9:30 a.m. a 2:00 p.m."
CONFIANZA = "Tenemos 15 años de experiencia y hemos atendido más de 900 casos."

# ---------------------------------------------------------------------------
# Precios y planes. TODO lo que el bot cotiza sale de aquí.
# ---------------------------------------------------------------------------
SERVICIOS = {
    "express": {"nombre": "Divorcio Express", "base": 5900, "inicial": 1500,
                "oferta": 900, "pago_ratificacion": False},
    "pension": {"nombre": "Pensión Alimenticia", "base": 5900, "inicial": 1500,
                "oferta": 900, "pago_ratificacion": False},
    "incausado": {"nombre": "Divorcio Incausado", "base": 12500, "inicial": 3500,
                  "oferta": None, "pago_ratificacion": True},
}
# semanas -> % de aumento por financiamiento. Tope: 14 semanas.
PLANES = {3: 35, 4: 38, 6: 45, 8: 58, 12: 70, 14: 78}
# Plan a la medida (rescate): se alarga el plazo SIN subir el margen más allá del máximo de PLANES.
PLAZOS_EXTRA = (16, 18, 20, 24)
AVISO_INACTIVIDAD_MIN = 10      # minutos de silencio antes del primer recordatorio
OFERTA_HORAS = 24
RECORDATORIO_HORAS = 20
CITA_PRESENCIAL = 500
CITA_LLAMADA = 350


def pesos(n):
    return "${:,.0f}".format(n)


def plan_semanal(servicio, semanas, inicial):
    """Devuelve {semanas, semanal, ratificacion, total} para un plan."""
    s = SERVICIOS[servicio]
    total = s["base"] * (100 + PLANES.get(semanas, max(PLANES.values()))) // 100
    resto = total - inicial
    if s["pago_ratificacion"] and semanas >= 6:
        semanal = math.ceil(resto / (semanas + 3))
        ratificacion = semanal * 3
    else:
        semanal = math.ceil(resto / semanas)
        ratificacion = 0
    return {"semanas": semanas, "semanal": semanal, "ratificacion": ratificacion,
            "total": inicial + semanal * semanas + ratificacion}


def plan_etapas(servicio, inicial):
    resto = SERVICIOS[servicio]["base"] - inicial
    a = math.ceil(resto / 2)
    return a, resto - a


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------
def norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9$ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


SI = {"si", "sii", "claro", "ok", "okay", "va", "de acuerdo", "por supuesto", "simon",
      "si claro", "claro que si", "esta bien", "sale", "si por favor", "adelante", "correcto"}
RELLENO = {"si", "no", "ok", "okay", "gracias", "hola", "buenas", "quiero", "es", "manana", "info",
           "informacion", "precio", "requisitos", "no se", "no lo se", "nada", "menu", "claro",
           "buenos dias", "buenas tardes", "buenas noches", "es muy caro", "caro"}


def parece_nombre(t, minimo=2):
    """Texto con forma de nombre de persona: solo letras, sin palabras de relleno."""
    t = t.strip()
    palabras = t.split()
    if len(palabras) < minimo or len(palabras) > 7 or len(t) < 3:
        return False
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ.' -]+", t):
        return False
    return norm(t) not in RELLENO and norm(palabras[0]) not in RELLENO


NO = {"no", "nel", "no gracias", "para nada", "nop", "no por ahora", "ahorita no", "ahora no"}


def M(text, buttons=None, rows=None, list_button="Ver opciones"):
    m = {"text": text}
    if buttons:
        m["buttons"] = buttons
    if rows:
        m["rows"] = rows
        m["list_button"] = list_button
    return m


def nm(s, coma=True):
    n = s["data"].get("nombre")
    if not n:
        return ""
    return (", " if coma else "") + n


def gracias(s):
    n = s["data"].get("nombre")
    return "Gracias, {}. ".format(n) if n else "Gracias. "


def svc(s):
    return SERVICIOS[s.get("servicio") or "express"]


def inicial(s):
    return s.get("inicial") or svc(s)["inicial"]


# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------
SESSIONS = {}
LOCK = threading.RLock()
SENT_IDS = []
SEEN_IDS = []


def nueva_sesion():
    return {"stage": "nuevo", "data": {}, "servicio": None, "neg": 0, "misses": 0,
            "opts": [], "paused_until": 0, "opted_out": False, "last_in": 0,
            "offer_ts": 0, "offer_used": False, "reminded": False, "inicial": None,
            "plan": None, "modalidad": None}


def cargar_sesiones():
    try:
        with open(SESSIONS_PATH, encoding="utf-8") as f:
            SESSIONS.update(json.load(f))
    except Exception:
        pass


def guardar_sesiones():
    try:
        tmp = SESSIONS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(SESSIONS, f, ensure_ascii=False)
        os.replace(tmp, SESSIONS_PATH)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Textos fijos
# ---------------------------------------------------------------------------
MENU_BOTONES = [("m1", "Divorcio Express"), ("m2", "Divorcio Incausado"), ("m3", "Pensión alimenticia")]
OTROS_ROWS = [
    ("m4", "Fui demandado/a", "Requiero atención urgente"),
    ("m5", "No veo a mis hijos", "No me dejan convivir con ellos"),
    ("m6", "Citatorio de fiscalía", "Requiero atención urgente"),
    ("m7", "Denunciar violencia", "Violencia por parte de mi pareja"),
    ("m8", "Acta de divorcio", "Tramitar mi acta de divorcio"),
    ("m9", "Agendar una cita", "Asesoría con un abogado"),
]

TXT_MENU = ("¿En qué te podemos ayudar? 👇\n\n"
            "• *Divorcio Express:* ambos están de acuerdo en firmar.\n"
            "• *Divorcio Incausado:* tu pareja no quiere firmar.\n"
            "• *Pensión alimenticia:* para tus hijos.\n\n"
            "Si necesitas otro servicio, escribe *otro*.")

REQUISITOS = (
    "📋 *Requisitos para tu trámite:*\n"
    "• Acta de matrimonio.\n"
    "• Actas de nacimiento de ambos cónyuges.\n"
    "• Actas de nacimiento de los hijos, aunque sean mayores de edad.\n"
    "• Comprobante de domicilio.\n"
    "• Copia de INE.\n"
    "No necesitas tener todo para iniciar: los requisitos completos te los "
    "entregamos en nuestras oficinas al contratar."
)

TOTAL_TXT = ("El desglose completo de tu plan te lo entrega nuestro equipo al "
             "formalizar tu contratación.")

FORM_INCAUSADO = [
    ("f_nombre", "📝 ¿Cuál es tu *nombre completo*?"),
    ("f_expareja", "¿Cuál es el *nombre completo de tu expareja*?"),
    ("f_hijos", "¿Cómo se llaman tus *hijos y cuántos años tienen*? (Si no tienen hijos, escribe *no*)"),
    ("f_tel_ex", "¿Cuál es el *teléfono de tu expareja*? (Si no lo tienes, escribe *saltar*)"),
]

ETIQUETAS = [
    ("servicio_nombre", "Servicio"), ("nombre_completo", "Nombre completo"),
    ("f_nombre", "Nombre completo"), ("nombre", "Nombre"), ("pareja", "Pareja"),
    ("f_expareja", "Expareja"), ("acuerdo", "Acuerdo para firmar"),
    ("hijos", "Hijos menores"), ("f_hijos", "Hijos"), ("bienes", "Bienes en común"),
    ("ciudad", "Ciudad"), ("prisa", "Cuándo quiere iniciar"),
    ("pe_hijos", "Hijos para pensión"), ("pe_trabajo", "Trabajo del obligado"),
    ("pe_aporta", "Aporta actualmente"), ("domicilio_ex", "Domicilio de la expareja"),
    ("localizacion", "Dónde localizarla"), ("trabajo_ex", "Trabajo de la expareja"),
    ("f_tel_ex", "Teléfono de la expareja"), ("pension", "Paga pensión"),
    ("violencia", "Hubo violencia"), ("denuncia_docs", "Documentos de denuncia"),
    ("modalidad", "Forma de pago"), ("plan_txt", "Plan elegido"),
    ("metodo", "Medio de pago"), ("cita_tipo", "Tipo de asesoría"),
    ("cita_cuando", "Día y horario"), ("motivo", "Motivo"), ("dudas", "Dudas pendientes"),
    ("horario_contacto", "Horario para contactar"), ("documentos", "Documentos"),
    ("objecion", "Qué lo detiene"), ("situacion", "Situación que describió"),
    ("interes_adicional", "Otros servicios de interés"),
]


def anotar(s, clave, texto):
    """Agrega texto a un campo del expediente sin repetirlo."""
    prev = s["data"].get(clave) or ""
    texto = texto.strip()[:200]
    if texto and texto not in prev:
        s["data"][clave] = (prev + " | " + texto)[:600] if prev else texto


OTROS_TEMAS = [
    (("testamento", "herencia", "sucesion", "intestad", "heredar"), "testamentos y sucesiones"),
    (("despido", "me despidieron", "me corrieron", "liquidacion", "finiquito", "laboral"), "asuntos laborales"),
    (("acta de divorcio",), "el trámite de tu acta de divorcio"),
    (("no me deja ver", "no me dejan ver", "convivencia"), "la convivencia con tus hijos"),
    (("registrar una marca", "mi marca", "mi empresa", "constituir", "un contrato"), "contratos, marcas y empresas"),
]


def venta_adicional(s, low):
    """Si el cliente menciona un asunto de otro servicio, se anota y se le ofrece."""
    for claves, nombre in OTROS_TEMAS:
        if any(c in low for c in claves):
            anotar(s, "interes_adicional", nombre)
            return ("También podemos ayudarte con *{}*. Lo anotamos en tu expediente para que nuestro "
                    "equipo te dé los detalles.".format(nombre))
    return None


def resumen(s):
    lines = ["📋 *Resumen de tu información:*"]
    vistos = set()
    completo = s["data"].get("nombre_completo") or s["data"].get("f_nombre")
    for k, label in ETIQUETAS:
        if k == "nombre" and completo:
            continue
        v = s["data"].get(k)
        if v and label not in vistos:
            vistos.add(label)
            lines.append("• {}: {}".format(label, v))
    return "\n".join(lines)[:1000]


# ---------------------------------------------------------------------------
# Pase a humano
# ---------------------------------------------------------------------------
def pasar_a_humano(s, texto, venta=False):
    s["stage"] = "post"
    s["opts"] = []
    s["notas_post"] = 0
    print("LEAD " + json.dumps({"tel": s.get("tel"), **s["data"]}, ensure_ascii=False), flush=True)
    if venta:
        final = ("🤝 Estás en buenas manos{}. Tomaste la mejor decisión y agradecemos mucho tu "
                 "preferencia. Nuestro equipo se pondrá en contacto contigo en breve.\n\n"
                 "Mientras tanto seguimos aquí: si tienes cualquier duda, escríbela y con gusto "
                 "te la resolvemos.").format(nm(s))
    else:
        final = ("🤝 Estás en buenas manos{}. Agradecemos mucho tu confianza. Nuestro equipo se pondrá "
                 "en contacto contigo en breve.\n\nMientras tanto, si tienes cualquier duda, "
                 "escríbela por aquí.").format(nm(s))
    return [M(texto + "\n\n🕘 Nuestro horario de atención es de " + HORARIO),
            M(resumen(s)), M(final)]


def txt_pago(s, monto):
    return ("¡Listo{}! ✅\n\n"
            "En este momento te referimos con una persona de nuestro equipo para acordar "
            "el día y la hora de tu pago de {} en nuestras oficinas, o bien por "
            "transferencia si lo prefieres. Ellos te proporcionarán los medios de pago."
            ).format(nm(s), pesos(monto))


def urgente(s, motivo, pedir_foto=False):
    s["data"]["motivo"] = motivo
    t = ("🚨 Tu asunto requiere atención inmediata. En este momento pasamos tu conversación "
         "con un abogado de nuestro equipo y se manejará de forma urgente.\n\n"
         "Por favor comunícate de inmediato a nuestra línea directa: 📞 *{}*").format(LINEA)
    if pedir_foto:
        t += "\n\nSi tienes el citatorio o la demanda, envíanos una fotografía por este medio."
    return pasar_a_humano(s, t)


# ---------------------------------------------------------------------------
# Etapas. Cada etapa tiene:
#   ask(s)              -> lista de mensajes con la pregunta
#   on(s, opcion, txt)  -> (mensajes_previos, siguiente_etapa) o None si no entendió
# ---------------------------------------------------------------------------
ASK = {}
ON = {}


def etapa(nombre):
    def deco(cls):
        ASK[nombre] = cls.ask
        ON[nombre] = cls.on
        return cls
    return deco


def detectar_servicio(low):
    if any(k in low for k in ("incausado", "no quiere firmar", "no quiere divorci", "no firma")):
        return "m2"
    if "pension" in low:
        return "m3"
    if any(k in low for k in ("me demandaron", "fui demandad", "me llego una demanda", "demandaron")):
        return "m4"
    if any(k in low for k in ("citatorio", "fiscalia", "me denunciaron", "centro de empoderamiento", "centro de justicia")):
        return "m6"
    if any(k in low for k in ("ver a mis hijos", "no me dejan ver", "convivencia")):
        return "m5"
    if "acta de divorcio" in low:
        return "m8"
    if any(k in low for k in ("agendar", "una cita", "asesoria")) or low == "cita":
        return "m9"
    if any(k in low for k in ("divorcio express", "divorcio expres", "mutuo", "de acuerdo en firmar")):
        return "m1"
    return None


@etapa("nombre")
class _Nombre:
    @staticmethod
    def ask(s):
        return [M("¡Hola! Gracias por escribir a *Divorcio Express Saltillo* ⚖️\n"
                  + CONFIANZA + "\n\n"
                  "Para atenderte mejor, ¿cuál es tu *nombre*?")]

    @staticmethod
    def on(s, op, txt):
        t = re.sub(r"(?i)^\s*(hola[,!. ]*)?(buen[oa]s? (dias|días|tardes|noches)[,!. ]*)?"
                   r"(me llamo|mi nombre es|soy|habla)\s+", "", txt.strip())
        palabras = t.split()
        if len(palabras) <= 4 and parece_nombre(t, minimo=1) and len(palabras[0]) >= 3:
            s["data"]["nombre"] = palabras[0].capitalize()[:20]
        destino = s.pop("intent", None)
        if destino:
            return ([], "menu>" + destino)
        return ([], "menu")


@etapa("menu")
class _Menu:
    @staticmethod
    def ask(s):
        saludo = "Gracias, {}. ".format(s["data"]["nombre"]) if s["data"].get("nombre") else ""
        return [M(saludo + TXT_MENU, buttons=MENU_BOTONES)]

    @staticmethod
    def on(s, op, txt):
        low = norm(txt)
        if op is None and (low in ("otro", "otros", "otra", "otro servicio", "otros servicios", "mas",
                                   "mas opciones", "otra cosa", "ninguno", "ninguna")
                           or low.startswith("otro")):
            return ([], "otros")
        op = op or detectar_servicio(low)
        if op is None:
            return None
        # nuevo asunto: se conserva solo el nombre
        s["data"] = {"nombre": s["data"]["nombre"]} if s["data"].get("nombre") else {}
        s["neg"] = 0
        s["inicial"] = None
        s["plan"] = None
        s["en_oferta"] = False
        if op == "m1":
            s["servicio"] = "express"
            s["data"]["servicio_nombre"] = "Divorcio Express"
            return ([], "ex_acuerdo")
        if op == "m2":
            s["servicio"] = "incausado"
            s["data"]["servicio_nombre"] = "Divorcio Incausado"
            return ([], "in_acuerdo")
        if op == "m3":
            s["servicio"] = "pension"
            s["data"]["servicio_nombre"] = "Pensión Alimenticia"
            return ([], "pe_hijos")
        if op == "m4":
            return (urgente(s, "Fue demandado/a", pedir_foto=True), "post")
        if op == "m6":
            return (urgente(s, "Citatorio de fiscalía", pedir_foto=True), "post")
        if op == "m7":
            s["data"]["motivo"] = "Denunciar violencia de su pareja"
            return (pasar_a_humano(
                s, "🛡️ Lo primero es tu seguridad. Si estás en peligro en este momento, llama al *911*.\n\n"
                   "Pasamos tu conversación con un abogado de nuestro equipo para atenderte de forma "
                   "urgente. También puedes comunicarte a nuestra línea directa: 📞 *{}*".format(LINEA)),
                "post")
        if op == "m5":
            s["data"]["motivo"] = "No le permiten ver a sus hijos"
            return ([M("👨‍👧 Sabemos lo difícil que es. Tienes derecho a convivir con tus hijos y "
                       "podemos ayudarte a recuperar esa convivencia por la vía legal. En la asesoría "
                       "el abogado define la mejor estrategia según tu caso.")], "ci_tipo")
        if op == "m8":
            s["data"]["motivo"] = "Tramitar acta de divorcio"
            return ([M("📄 Con gusto te ayudamos a tramitar tu acta de divorcio una vez que exista "
                       "sentencia. En la asesoría revisamos tu caso y te decimos qué se necesita.")], "ci_tipo")
        if op == "m9":
            s["data"]["motivo"] = "Asesoría con un abogado"
            return ([], "ci_tipo")
        return None


@etapa("otros")
class _Otros:
    @staticmethod
    def ask(s):
        return [M("Con gusto{}. Estos son nuestros otros servicios. Toca *Ver servicios* y elige 👇".format(nm(s)),
                  rows=OTROS_ROWS + [("m0", "Volver al inicio", "Divorcio Express, Incausado o Pensión")],
                  list_button="Ver servicios")]

    @staticmethod
    def on(s, op, txt):
        if op == "m0":
            return ([], "menu")
        return _Menu.on(s, op, txt)


# ----------------------------- CITAS ---------------------------------------
@etapa("ci_tipo")
class _CiTipo:
    @staticmethod
    def ask(s):
        return [M("📅 Para agendar tu asesoría, ¿cómo la prefieres?\n\n"
                  "• Presencial en nuestras oficinas: {}\n• Por llamada: {}".format(
                      pesos(CITA_PRESENCIAL), pesos(CITA_LLAMADA)),
                  buttons=[("ci_pres", "Presencial"), ("ci_llam", "Por llamada"), ("ci_menu", "Ver el menú")])]

    @staticmethod
    def on(s, op, txt):
        if op == "ci_pres":
            s["data"]["cita_tipo"] = "Presencial ({})".format(pesos(CITA_PRESENCIAL))
            return ([], "ci_cuando")
        if op == "ci_llam":
            s["data"]["cita_tipo"] = "Por llamada ({})".format(pesos(CITA_LLAMADA))
            return ([], "ci_cuando")
        if op == "ci_menu":
            return ([], "menu")
        return None


@etapa("ci_cuando")
class _CiCuando:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Qué *día y a qué hora* te gustaría tu asesoría?\n\n"
                  "Atendemos de " + HORARIO)]

    @staticmethod
    def on(s, op, txt):
        if len(txt.strip()) < 4 or norm(txt) in RELLENO:
            return None
        s["data"]["cita_cuando"] = txt.strip()[:120]
        return (pasar_a_humano(
            s, gracias(s) + "En este momento te referimos con una persona de nuestro equipo "
               "para confirmar el día y la hora de tu asesoría."), "post")


# ----------------------------- EXPRESS -------------------------------------
@etapa("ex_acuerdo")
class _ExAcuerdo:
    @staticmethod
    def ask(s):
        return [M("⚖️ *Divorcio Express*\nEs el camino más rápido y económico para divorciarse: "
                  "sin juicio ni conflicto, con un convenio que ambos firman.\n\n"
                  "Para orientarte bien{}: ¿tú y tu pareja *están de acuerdo en firmar* el divorcio?".format(nm(s)),
                  buttons=[("ex_ac_si", "Sí, de acuerdo"), ("ex_ac_no", "No quiere firmar"), ("ex_ac_ns", "No lo sé")])]

    @staticmethod
    def on(s, op, txt):
        if op == "ex_ac_si":
            s["data"]["acuerdo"] = "Sí"
            return ([], "ex_hijos")
        if op == "ex_ac_no":
            s["servicio"] = "incausado"
            s["data"]["servicio_nombre"] = "Divorcio Incausado"
            s["data"]["acuerdo"] = "No"
            return ([M(gracias(s) + "No te preocupes: *sí te puedes divorciar aunque tu pareja no quiera "
                       "firmar*. No necesitas su firma ni su permiso. Ese trámite es el Divorcio Incausado.")],
                    "in_dom")
        if op == "ex_ac_ns":
            return ([], "ex_quiza")
        return None


@etapa("ex_quiza")
class _ExQuiza:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "Si le propusieras el divorcio a tu pareja, ¿crees que estaría "
                  "dispuesto(a) a llegar a un acuerdo y firmar?",
                  buttons=[("exq_si", "Sí, creo que sí"), ("exq_no", "No, no creo")])]

    @staticmethod
    def on(s, op, txt):
        if op == "exq_si":
            s["data"]["acuerdo"] = "Probablemente sí"
            return ([], "ex_hijos")
        if op == "exq_no":
            s["servicio"] = "incausado"
            s["data"]["servicio_nombre"] = "Divorcio Incausado"
            s["data"]["acuerdo"] = "Probablemente no"
            return ([M("Entendido. Podemos continuar con el *Divorcio Incausado*: no necesitas la firma "
                       "ni el permiso de tu pareja.")], "in_dom")
        return None


@etapa("ex_hijos")
class _ExHijos:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "Cuando ambos están de acuerdo, el trámite se hace con una demanda y un "
                  "convenio que firman en nuestras oficinas.\n\n¿Tienen *hijos menores de edad*?",
                  buttons=[("exh_si", "Sí"), ("exh_no", "No")])]

    @staticmethod
    def on(s, op, txt):
        if op == "exh_si":
            s["data"]["hijos"] = "Sí"
            return ([M(gracias(s) + "En ese caso el convenio deja por escrito la pensión alimenticia, "
                       "la custodia y las convivencias, para que todo quede claro y protegido.")], "ex_bienes")
        if op == "exh_no":
            s["data"]["hijos"] = "No"
            return ([M(gracias(s) + "Sin hijos menores el trámite es todavía más sencillo.")], "ex_bienes")
        return None


@etapa("ex_bienes")
class _ExBienes:
    @staticmethod
    def ask(s):
        return [M("¿Tienen *bienes en común*, como casa, terreno o vehículo?",
                  buttons=[("exb_si", "Sí"), ("exb_no", "No")])]

    @staticmethod
    def on(s, op, txt):
        if op in ("exb_si", "exb_no"):
            s["data"]["bienes"] = "Sí" if op == "exb_si" else "No"
            pre = ("El convenio también puede dejar definida la división de esos bienes."
                   if op == "exb_si" else "Perfecto, eso simplifica el convenio.")
            return ([M(gracias(s) + pre)], "ex_ciudad")
        return None


class _Ciudad:
    siguiente = "ex_prisa"

    @classmethod
    def ask(cls, s):
        return [M("¿En qué *ciudad* viven actualmente?",
                  buttons=[("cd_sal", "Saltillo"), ("cd_ra", "Ramos o Arteaga"), ("cd_otra", "Otra ciudad")])]

    @classmethod
    def on(cls, s, op, txt):
        ciudades = {"cd_sal": "Saltillo", "cd_ra": "Ramos Arizpe o Arteaga", "cd_otra": "Otra ciudad"}
        if op in ciudades:
            s["data"]["ciudad"] = ciudades[op]
        elif parece_nombre(txt, minimo=1) and len(txt.split()) <= 5:
            s["data"]["ciudad"] = txt.strip()[:40]
        else:
            return None
        return ([], cls.siguiente)


@etapa("ex_ciudad")
class _ExCiudad(_Ciudad):
    siguiente = "ex_prisa"


@etapa("ex_prisa")
class _ExPrisa:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Qué tan pronto te gustaría *iniciar tu trámite*?",
                  buttons=[("exp_sem", "Esta semana"), ("exp_mes", "Este mes"), ("exp_info", "Solo me informo")])]

    @staticmethod
    def on(s, op, txt):
        m = {"exp_sem": "Esta semana", "exp_mes": "Este mes", "exp_info": "Solo se informa"}
        if op in m:
            s["data"]["prisa"] = m[op]
            return ([], "cierre")
        return None


# ----------------------------- PENSIÓN -------------------------------------
@etapa("pe_hijos")
class _PeHijos:
    @staticmethod
    def ask(s):
        return [M("👶 *Pensión alimenticia*\nTus hijos tienen derecho a recibir pensión y con gusto "
                  "te ayudamos a tramitarla.\n\nPara orientarte{}: ¿para *cuántos hijos* sería la pensión?".format(nm(s)),
                  buttons=[("peh_1", "1 hijo"), ("peh_2", "2 hijos"), ("peh_3", "3 o más")])]

    @staticmethod
    def on(s, op, txt):
        m = {"peh_1": "1", "peh_2": "2", "peh_3": "3 o más"}
        if op in m:
            s["data"]["pe_hijos"] = m[op]
            return ([], "pe_trabajo")
        return None


@etapa("pe_trabajo")
class _PeTrabajo:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿La persona que debe dar la pensión *tiene trabajo* actualmente?",
                  buttons=[("pet_fijo", "Sí, empleo fijo"), ("pet_cuenta", "Por su cuenta"), ("pet_ns", "No lo sé")])]

    @staticmethod
    def on(s, op, txt):
        m = {"pet_fijo": "Empleo fijo", "pet_cuenta": "Trabaja por su cuenta", "pet_ns": "No se sabe"}
        if op in m:
            s["data"]["pe_trabajo"] = m[op]
            return ([], "pe_aporta")
        return None


@etapa("pe_aporta")
class _PeAporta:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Actualmente *aporta algo* para los gastos de tus hijos?",
                  buttons=[("pea_si", "Sí, a veces"), ("pea_no", "No da nada")])]

    @staticmethod
    def on(s, op, txt):
        if op in ("pea_si", "pea_no"):
            s["data"]["pe_aporta"] = "A veces" if op == "pea_si" else "No aporta"
            return ([M(gracias(s) + "Con el trámite, la pensión queda fijada por un juez y deja de "
                       "depender de la voluntad de la otra persona.")], "pe_ciudad")
        return None


@etapa("pe_ciudad")
class _PeCiudad(_Ciudad):
    siguiente = "cierre"


# ----------------------------- INCAUSADO -----------------------------------
@etapa("in_acuerdo")
class _InAcuerdo:
    @staticmethod
    def ask(s):
        return [M("⚖️ *Divorcio Incausado*\nSí te puedes divorciar aunque tu pareja no quiera firmar. "
                  "No necesitas su firma ni su permiso.\n\n¿Ambos están de acuerdo en divorciarse, "
                  "o solo tú quieres iniciarlo?",
                  buttons=[("ina_si", "Estamos de acuerdo"), ("ina_no", "Solo yo quiero")])]

    @staticmethod
    def on(s, op, txt):
        if op == "ina_si":
            s["servicio"] = "express"
            s["data"]["servicio_nombre"] = "Divorcio Express"
            s["data"]["acuerdo"] = "Sí"
            return ([M("¡Qué bueno! Si ambos están de acuerdo, el *Divorcio Express* es el camino "
                       "más rápido y económico, sin juicio ni conflicto.")], "ex_hijos")
        if op == "ina_no":
            s["data"]["acuerdo"] = "No"
            return ([M(gracias(s) + "Podemos continuar con tu trámite. Te haremos unas preguntas "
                       "para definir la estrategia.")], "in_dom")
        return None


@etapa("in_dom")
class _InDom:
    @staticmethod
    def ask(s):
        return [M("¿Sabes *dónde vive* tu expareja? Si lo sabes, escríbenos la dirección. "
                  "(Si no lo sabes, escribe *no sé*)")]

    @staticmethod
    def on(s, op, txt):
        s["data"]["domicilio_ex"] = txt.strip()[:200]
        return ([], "in_loc")


@etapa("in_loc")
class _InLoc:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Tiene familiares, amigos o conocidos en Saltillo, o conoces algún "
                  "*lugar donde pueda ser localizado(a)*? (Si no, escribe *no*)")]

    @staticmethod
    def on(s, op, txt):
        s["data"]["localizacion"] = txt.strip()[:200]
        if norm(txt) in NO or norm(txt) in ("no se", "no lo se", "nadie", "ninguno"):
            return ([M("No te preocupes, el trámite puede continuar.")], "in_trab")
        return ([M("Gracias. Nuestro equipo jurídico valorará si esa ubicación procede para "
                   "la notificación legal.")], "in_trab")


@etapa("in_trab")
class _InTrab:
    @staticmethod
    def ask(s):
        return [M("¿Sabes si tu expareja tiene un *trabajo fijo* y en dónde? (Si no, escribe *no sé*)")]

    @staticmethod
    def on(s, op, txt):
        s["data"]["trabajo_ex"] = txt.strip()[:200]
        return ([], "in_pension")


@etapa("in_pension")
class _InPension:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Tu expareja actualmente *paga pensión alimenticia* a tus hijos?",
                  buttons=[("inp_si", "Sí"), ("inp_no", "No"), ("inp_na", "No tenemos hijos")])]

    @staticmethod
    def on(s, op, txt):
        m = {"inp_si": "Sí", "inp_no": "No", "inp_na": "No tienen hijos"}
        if op in m:
            s["data"]["pension"] = m[op]
            pre = []
            if op == "inp_no":
                pre = [M("Te va a interesar: al contratar el Divorcio Incausado, el trámite de "
                         "pensión alimenticia va incluido.")]
            return (pre, "in_violencia")
        return None


@etapa("in_violencia")
class _InViolencia:
    @staticmethod
    def ask(s):
        return [M("¿En algún momento existió *violencia* por parte de tu expareja?",
                  buttons=[("inv_si", "Sí"), ("inv_no", "No")])]

    @staticmethod
    def on(s, op, txt):
        if op == "inv_si":
            s["data"]["violencia"] = "Sí"
            return ([M("Lamentamos mucho lo que viviste. Si estás en peligro en este momento, "
                       "llama al *911*.")], "in_denuncia")
        if op == "inv_no":
            s["data"]["violencia"] = "No"
            return ([], "in_form0")
        return None


@etapa("in_denuncia")
class _InDenuncia:
    @staticmethod
    def ask(s):
        return [M("¿Cuentas con *documentos de la denuncia*?",
                  buttons=[("ind_si", "Sí, los tengo"), ("ind_no", "No")])]

    @staticmethod
    def on(s, op, txt):
        if op in ("ind_si", "ind_no"):
            s["data"]["denuncia_docs"] = "Sí" if op == "ind_si" else "No"
            return ([], "in_form0")
        return None


def _make_form(i):
    key, pregunta = FORM_INCAUSADO[i]

    class _F:
        @staticmethod
        def ask(s):
            intro = ""
            if i == 0:
                intro = ("¡Perfecto! Con lo que nos has contado podemos continuar con tu Divorcio "
                         "Incausado. Ahora necesitamos unos datos para integrar tu expediente.\n\n")
            else:
                intro = gracias(s)
            return [M(intro + pregunta)]

        @staticmethod
        def on(s, op, txt):
            v = txt.strip()[:200]
            if norm(v) in ("saltar", "no lo tengo", "no se", "no lo se"):
                v = "No proporcionado"
            s["data"][key] = v
            if i + 1 < len(FORM_INCAUSADO):
                return ([], "in_form{}".format(i + 1))
            return ([M("¡Muchas gracias! Ya tenemos lo necesario para analizar tu situación.")], "cierre")
    ASK["in_form{}".format(i)] = _F.ask
    ON["in_form{}".format(i)] = _F.on


for _i in range(len(FORM_INCAUSADO)):
    _make_form(_i)


# ----------------------------- CIERRE --------------------------------------
def info_servicio(s):
    k = s["servicio"]
    d = s["data"]
    if k == "express":
        t = ("📌 *Tu Divorcio Express{}*\n"
             "• Duración aproximada: 30 a 45 días hábiles.\n"
             "• Firman la demanda y el convenio en nuestras oficinas y nosotros la presentamos.\n"
             "• El juzgado da una cita 15 a 20 días después, a la que acuden ambos.").format(nm(s))
        if d.get("hijos") == "Sí":
            t += ("\n• Quien no tendrá la custodia lleva ese día un fiador alimentista "
                  "(cualquier persona con INE).")
        return t
    if k == "pension":
        return ("📌 *Tu trámite de Pensión Alimenticia{}*\n"
                "• Duración aproximada: 30 a 45 días hábiles.\n"
                "• Firmas la demanda en nuestras oficinas y nosotros la presentamos.\n"
                "• Al juzgado acudes solo tú, con tu INE.").format(nm(s))
    return ("📌 *Tu Divorcio Incausado{}*\n"
            "• No necesitas la firma de tu expareja.\n"
            "• Firmas la demanda en nuestras oficinas y la presentamos al día siguiente.\n"
            "• El juzgado te cita a ratificarla (aprox. 7 a 15 días hábiles) y te acompañamos.\n"
            "• Después viene la audiencia preliminar, en 30 a 60 días hábiles.\n"
            "• El trámite de pensión alimenticia va incluido.").format(nm(s))


@etapa("cierre")
class _Cierre:
    @staticmethod
    def ask(s):
        v = svc(s)
        return [M(info_servicio(s) + "\n\n" + CONFIANZA),
                M("💰 Tu trámite de contado es de *{}*. También puedes iniciar con solo *{}* "
                  "y pagar el resto a plazos.\n\n¿Qué opción te conviene más?".format(
                      pesos(v["base"]), pesos(inicial(s))),
                  buttons=[("c_contado", "Pago de contado"), ("c_fin", "Iniciar con " + pesos(inicial(s))),
                           ("c_no", "Ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "c_contado":
            return aceptar(s, "Contado", "Pago de contado: " + pesos(svc(s)["base"]), svc(s)["base"])
        if op == "c_fin":
            return ([], "fin_tipo")
        if op == "c_no":
            return negativa(s)
        return None


def negativa(s):
    s["neg"] += 1
    if s["neg"] == 1:
        return ([], "obj1")
    if not s.get("medida_vista"):
        return ([], "a_medida")
    if svc(s)["oferta"] and s["offer_ts"] and time.time() - s["offer_ts"] < OFERTA_HORAS * 3600:
        return ([], "oferta_vigencia")
    return ([M("Gracias por tu tiempo y tu confianza{}. Aquí seguimos para cuando decidas "
               "avanzar. 🤝".format(nm(s)))], "espera")


def aceptar(s, modalidad, plan_txt, monto):
    s["data"]["modalidad"] = modalidad
    s["data"]["plan_txt"] = plan_txt
    s["monto_inicio"] = monto
    return ([M("¡Excelente decisión{}! 🎉 Para dejar listo tu expediente solo necesitamos "
               "un par de datos.".format(nm(s)))], "acc_nombre")


@etapa("fin_tipo")
class _FinTipo:
    @staticmethod
    def ask(s):
        extra = ("comenzamos a preparar tu demanda y la estrategia de tu caso"
                 if s["servicio"] == "incausado"
                 else "te entregamos los requisitos de tu trámite en nuestras oficinas")
        return [M("Te explicamos cómo funciona{}: iniciar con {} es un *financiamiento a plazos*. "
                  "Con ese primer pago contratas el servicio y {}.\n\n"
                  "Puedes liquidar el resto en solo 2 pagos más, *sin incremento del costo original*, "
                  "o en pagos semanales si lo necesitas.".format(nm(s), pesos(inicial(s)), extra),
                  buttons=[("ft_etapas", "2 pagos sin aumento"), ("ft_semana", "Pagos por semana"),
                           ("ft_contado", "Mejor de contado")])]

    @staticmethod
    def on(s, op, txt):
        if op == "ft_etapas":
            return ([], "etapas")
        if op == "ft_semana":
            return ([], "semanal")
        if op == "ft_contado":
            return aceptar(s, "Contado", "Pago de contado: " + pesos(svc(s)["base"]), svc(s)["base"])
        return None


def texto_etapas(s):
    a, b = plan_etapas(s["servicio"], inicial(s))
    if s["servicio"] == "incausado":
        l2 = "{} el día que firmes tu demanda en nuestras oficinas.".format(pesos(a))
        l3 = ("{} un día antes de tu cita en el juzgado para ratificar la demanda "
              "(aprox. 7 a 15 días hábiles después de presentarla).").format(pesos(b))
        l1 = "{} al contratar.".format(pesos(inicial(s)))
    else:
        l1 = "{} al contratar. Te entregamos tus requisitos en nuestras oficinas.".format(pesos(inicial(s)))
        l2 = "{} el día que firmes tu demanda en nuestras oficinas.".format(pesos(a))
        l3 = ("{} el día que te citemos para entregarte el acuse de que tu demanda ya quedó "
              "presentada en el juzgado, aproximadamente una semana después de la firma.").format(pesos(b))
    return "1️⃣ {}\n2️⃣ {}\n3️⃣ {}".format(l1, l2, l3)


@etapa("etapas")
class _Etapas:
    @staticmethod
    def ask(s):
        return [M("Perfecto{}. Tu plan queda así, sin incremento del costo original:\n\n".format(nm(s))
                  + texto_etapas(s) + "\n\n¿Confirmamos tu plan?",
                  buttons=[("et_si", "Sí, confirmo"), ("et_semana", "Pagos por semana"), ("et_no", "Ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "et_si":
            a, b = plan_etapas(s["servicio"], inicial(s))
            return aceptar(s, "Financiamiento por etapas",
                           "{} inicial + {} + {} (sin aumento)".format(pesos(inicial(s)), pesos(a), pesos(b)),
                           inicial(s))
        if op == "et_semana":
            return ([], "semanal")
        if op == "et_no":
            return negativa(s)
        return None


@etapa("semanal")
class _Semanal:
    @staticmethod
    def ask(s):
        rows = []
        for sem in sorted(PLANES, reverse=True):
            p = plan_semanal(s["servicio"], sem, inicial(s))
            desc = "{} pagos semanales".format(sem)
            if p["ratificacion"]:
                desc += " + un pago antes de ratificar"
            rows.append(("sem_{}".format(sem), "{} por semana".format(pesos(p["semanal"])), desc))
        return [M("Con gusto{}. Te comentamos con transparencia: al pagar en más semanas, el costo "
                  "original aumenta por el financiamiento. Entre menos semanas, menor es el aumento.\n\n"
                  "Para armarte el plan que mejor se ajuste a ti, ¿*cuánto podrías pagar por semana*? "
                  "Toca *Ver pagos* y elige 👇".format(nm(s)),
                  rows=rows, list_button="Ver pagos")]

    @staticmethod
    def on(s, op, txt):
        if op and op.startswith("sem_"):
            s["plan"] = int(op[4:])
            return ([], "plan")
        m = re.search(r"\d[\d,\.]*", txt)
        if m:
            try:
                monto = float(m.group(0).replace(",", ""))
            except ValueError:
                return None
            # el plan más corto que el cliente puede cubrir con ese pago semanal
            for sem in sorted(PLANES):
                if plan_semanal(s["servicio"], sem, inicial(s))["semanal"] <= monto:
                    s["plan"] = sem
                    return ([], "plan")
            for sem in PLAZOS_EXTRA:
                if plan_semanal(s["servicio"], sem, inicial(s))["semanal"] <= monto:
                    s["plan"] = sem
                    return ([M("Con gusto{}, ajustamos el plazo para que tus pagos sean más cómodos.".format(nm(s)))], "plan")
            return ([], "a_medida")
        return None


def activar_oferta(s):
    """El plan a la medida inicia con el pago de oferta mientras esté vigente (24 h)."""
    v = svc(s)
    if not v["oferta"]:
        return
    if not s["offer_used"]:
        s["offer_used"] = True
        s["offer_ts"] = time.time()
        s["reminded"] = False
    if time.time() - s["offer_ts"] < OFERTA_HORAS * 3600:
        s["inicial"] = v["oferta"]
        s["en_oferta"] = True


def todas_las_semanas():
    return sorted(set(PLANES) | set(PLAZOS_EXTRA))


@etapa("a_medida")
class _AMedida:
    @staticmethod
    def ask(s):
        activar_oferta(s)
        s["medida_vista"] = True
        rows = []
        for sem in sorted(todas_las_semanas(), reverse=True):
            p = plan_semanal(s["servicio"], sem, inicial(s))
            desc = "{} pagos semanales".format(sem)
            if p["ratificacion"]:
                desc += " + un pago antes de ratificar"
            rows.append(("sem_{}".format(sem), "{} por semana".format(pesos(p["semanal"])), desc))
        return [M("Queremos que te quedes con nosotros{}. 🤝 Contarías con abogados expertos, 15 años de "
                  "experiencia y la mejor asesoría.\n\n"
                  "Por eso te armamos un *plan exclusivo a tu medida*: inicias con solo *{}* y ajustamos "
                  "el plazo para que tus pagos sean cómodos.\n\n"
                  "¿*Cuánto podrías pagar por semana*? Toca *Ver pagos* y elige, o escríbenos la cantidad 👇".format(
                      nm(s), pesos(inicial(s))),
                  rows=rows[:10], list_button="Ver pagos")]

    @staticmethod
    def on(s, op, txt):
        if op and op.startswith("sem_"):
            s["plan"] = int(op[4:])
            return ([], "plan")
        m = re.search(r"\d[\d,\.]*", txt)
        if m:
            try:
                monto = float(m.group(0).replace(",", ""))
            except ValueError:
                return None
            for sem in todas_las_semanas():
                if plan_semanal(s["servicio"], sem, inicial(s))["semanal"] <= monto:
                    s["plan"] = sem
                    return ([], "plan")
            s["plan"] = max(todas_las_semanas())
            minimo = plan_semanal(s["servicio"], s["plan"], inicial(s))["semanal"]
            return ([M("Gracias por tu confianza{}. El pago más cómodo que podemos ofrecerte es de {} por "
                       "semana.".format(nm(s), pesos(minimo)))], "plan")
        return None


@etapa("nudge")
class _Nudge:
    """Recordatorio por inactividad durante el cierre."""
    @staticmethod
    def ask(s):
        return [M("{}seguimos aquí para ayudarte. 🙂 ¿Qué te pareció tu plan? Si lo necesitas, te armamos "
                  "uno *exclusivo a tu medida* para que tus pagos sean más cómodos.".format(
                      (s["data"]["nombre"] + ", ") if s["data"].get("nombre") else "Hola, "),
                  buttons=[("nd_medida", "Plan a mi medida"), ("nd_duda", "Tengo una duda"), ("nd_no", "No, gracias")])]

    @staticmethod
    def on(s, op, txt):
        if op == "nd_medida":
            return ([], "a_medida")
        if op == "nd_duda":
            return ([], "duda")
        if op == "nd_no":
            return negativa(s)
        return None


@etapa("plan")
class _Plan:
    @staticmethod
    def ask(s):
        p = plan_semanal(s["servicio"], s["plan"], inicial(s))
        t = ("{}Con lo que nos indicas, este es tu plan:\n\n"
             "💳 Pago inicial: {}\n📅 {} pagos semanales de {}").format(
                 gracias(s), pesos(inicial(s)), p["semanas"], pesos(p["semanal"]))
        if p["ratificacion"]:
            t += ("\n⚖️ Un pago de {} un día antes de tu cita en el juzgado para ratificar la demanda"
                  ).format(pesos(p["ratificacion"]))
        return [M(t + "\n\n¿Te gustaría comenzar con este plan?",
                  buttons=[("pl_si", "Sí, quiero comenzar"), ("pl_otro", "Ver otro plazo"), ("pl_no", "Ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "pl_si":
            p = plan_semanal(s["servicio"], s["plan"], inicial(s))
            txtp = "{} inicial + {} pagos semanales de {}".format(pesos(inicial(s)), p["semanas"], pesos(p["semanal"]))
            if p["ratificacion"]:
                txtp += " + {} antes de ratificar".format(pesos(p["ratificacion"]))
            return aceptar(s, "Financiamiento semanal", txtp, inicial(s))
        if op == "pl_otro":
            return ([], "a_medida" if s.get("medida_vista") else "semanal")
        if op == "pl_no":
            return negativa(s)
        return None


# ----------------------------- OBJECIONES ----------------------------------
@etapa("obj1")
class _Obj1:
    @staticmethod
    def ask(s):
        return [M("Entendemos{}, y gracias por tu sinceridad. Seguimos aquí para ayudarte: con nosotros "
                  "tendrías abogados expertos y la mejor asesoría. 🙂\n\n"
                  "¿Qué fue lo que no te convenció y cómo podemos ayudarte?".format(nm(s)),
                  buttons=[("o_precio", "Los pagos"), ("o_pensar", "Necesito pensarlo"), ("o_dudas", "Tengo más dudas")])]

    @staticmethod
    def on(s, op, txt):
        if op == "o_precio":
            return ([], "a_medida")
        if op == "o_pensar":
            return ([], "obj_pensar")
        if op == "o_dudas":
            return ([], "duda")
        if len(norm(txt)) >= 3:
            s["data"]["objecion"] = txt.strip()[:200]
            return ([M("Gracias por decírnoslo{}. Lo tomamos en cuenta.".format(nm(s)))], "a_medida")
        return None


@etapa("obj_precio")
class _ObjPrecio:
    @staticmethod
    def ask(s):
        return [M("Te entendemos perfectamente{}. Es una decisión importante y queremos que el dinero "
                  "no sea lo que te impida resolver tu situación.\n\n"
                  "¿Cómo podemos ayudarte a contratar el servicio? Tenemos estas opciones:".format(nm(s)),
                  buttons=[("op_dos", "Dos exhibiciones"), ("op_semana", "Pagos por semana"), ("op_no", "Ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "op_dos":
            return ([], "dos_exh")
        if op == "op_semana":
            return ([], "semanal")
        if op == "op_no":
            return negativa(s)
        return None


@etapa("dos_exh")
class _DosExh:
    @staticmethod
    def ask(s):
        base = svc(s)["base"]
        a = math.ceil(base / 2)
        return [M("Con gusto{}. En dos exhibiciones, sin incremento del costo original:\n\n"
                  "1️⃣ {} al contratar.\n2️⃣ {} el día que firmes tu demanda en nuestras oficinas.\n\n"
                  "¿Confirmamos esta opción?".format(nm(s), pesos(a), pesos(base - a)),
                  buttons=[("de_si", "Sí, confirmo"), ("de_semana", "Pagos por semana"), ("de_no", "Ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "de_si":
            base = svc(s)["base"]
            a = math.ceil(base / 2)
            return aceptar(s, "Dos exhibiciones", "{} al contratar + {} al firmar la demanda".format(
                pesos(a), pesos(base - a)), a)
        if op == "de_semana":
            return ([], "semanal")
        if op == "de_no":
            return negativa(s)
        return None


@etapa("obj_pensar")
class _ObjPensar:
    @staticmethod
    def ask(s):
        return [M("Claro que sí{}, tómate tu tiempo. Mientras lo piensas, ¿hay algo que te gustaría "
                  "aclarar sobre el proceso o sobre las formas de pago?".format(nm(s)),
                  buttons=[("ot_duda", "Sí, tengo una duda"), ("ot_pagos", "Ver formas de pago"),
                           ("ot_luego", "Les escribo después")])]

    @staticmethod
    def on(s, op, txt):
        if op == "ot_duda":
            return ([], "duda")
        if op == "ot_pagos":
            return ([], "obj_precio")
        if op == "ot_luego":
            return negativa(s)
        return None


@etapa("duda")
class _Duda:
    @staticmethod
    def ask(s):
        return [M("Con gusto{}. Cuéntanos tu duda y te la resolvemos en este momento.".format(nm(s)))]

    @staticmethod
    def on(s, op, txt):
        r = faq(s, norm(txt))
        extra = venta_adicional(s, norm(txt))
        if r or extra:
            return ([M("\n\n".join(x for x in (r, extra) if x))], "duda_mas")
        prev = s["data"].get("dudas")
        s["data"]["dudas"] = ((prev + " | ") if prev else "") + txt.strip()[:200]
        return ([M(gracias(s) + "Dejamos anotada tu pregunta en tu expediente para que nuestro "
                   "equipo jurídico te la responda a detalle según tu caso.")], "duda_mas")


# ----------------------------- OFERTA $900 ---------------------------------
@etapa("oferta")
class _Oferta:
    @staticmethod
    def ask(s):
        s["en_oferta"] = True
        return [M("Te entendemos{}, y no queremos que el dinero te detenga. 🤝\n\n"
                  "Por eso tenemos para ti una *oferta especial y exclusiva*: comienza tu trámite "
                  "únicamente con *{}* y el resto a plazos.\n\n¿Te gustaría aprovecharla?".format(
                      nm(s), pesos(svc(s)["oferta"])),
                  buttons=[("of_si", "Iniciar con " + pesos(svc(s)["oferta"])), ("of_duda", "Tengo una duda"),
                           ("of_no", "Por ahora no")])]

    @staticmethod
    def on(s, op, txt):
        if op == "of_si":
            s["inicial"] = svc(s)["oferta"]
            return ([M("¡Excelente decisión{}! 🎉".format(nm(s)))], "fin_tipo")
        if op == "of_duda":
            return ([], "duda")
        if op == "of_no":
            return ([], "oferta_vigencia")
        return None


@etapa("oferta_vigencia")
class _OfertaVigencia:
    @staticmethod
    def ask(s):
        return [M("Con gusto{}, gracias por tu tiempo. 🤝\n\n"
                  "Solo te comentamos que nuestra oferta exclusiva tiene una *vigencia de 24 horas*: "
                  "comenzar tu trámite con {} y el resto a plazos.\n\n"
                  "Nuestro trámite es rápido, confiable y eficiente. {}\n\n"
                  "Cuando decidas avanzar, escríbenos aquí mismo y te atendemos de inmediato.".format(
                      nm(s), pesos(svc(s)["oferta"]), CONFIANZA))]

    @staticmethod
    def on(s, op, txt):
        # cualquier mensaje posterior del cliente
        if time.time() - s["offer_ts"] < OFERTA_HORAS * 3600:
            if op == "rec_no" or norm(txt) in NO:
                return ([M("Gracias por tu tiempo{}. Aquí seguimos para cuando decidas avanzar. 🤝".format(nm(s)))],
                        "espera")
            s["inicial"] = svc(s)["oferta"]
            return ([M("¡Qué gusto saludarte de nuevo{}! Tu oferta exclusiva sigue vigente.".format(nm(s)))],
                    "fin_tipo")
        s["inicial"] = None
        s["en_oferta"] = False
        s["neg"] = 0
        return ([M("¡Qué gusto saludarte de nuevo{}! 🙂 La oferta exclusiva de {} ya concluyó, pero con "
                   "gusto te ayudamos a iniciar tu trámite.".format(nm(s), pesos(svc(s)["oferta"])))], "cierre")


@etapa("espera")
class _Espera:
    @staticmethod
    def ask(s):
        return []

    @staticmethod
    def on(s, op, txt):
        s["neg"] = 0
        if s.get("servicio") and s["data"].get("servicio_nombre"):
            if s["offer_ts"] and time.time() - s["offer_ts"] >= OFERTA_HORAS * 3600:
                s["inicial"] = None
                s["en_oferta"] = False
            return ([M("¡Qué gusto saludarte de nuevo{}! 🙂 Retomamos tu trámite de {}.".format(
                nm(s), s["data"]["servicio_nombre"]))], "cierre")
        return ([], "menu")


# ----------------------------- ACEPTÓ PAGAR --------------------------------
@etapa("acc_nombre")
class _AccNombre:
    @staticmethod
    def ask(s):
        if s["data"].get("f_nombre"):
            return []
        return [M("¿Cuál es tu *nombre completo* (nombre y apellidos), tal como aparece en tu INE?")]

    @staticmethod
    def on(s, op, txt):
        if s["data"].get("f_nombre"):
            return ([], "acc_metodo")
        if not parece_nombre(txt):
            return None
        s["data"]["nombre_completo"] = txt.strip()[:80]
        return ([], "acc_pareja")


@etapa("acc_pareja")
class _AccPareja:
    @staticmethod
    def ask(s):
        if s["servicio"] == "pension":
            return [M(gracias(s) + "¿Cuál es el *nombre completo* (nombre y apellidos) de la persona que debe dar la pensión?")]
        return [M(gracias(s) + "¿Cuál es el *nombre completo de tu pareja* (nombre y apellidos)?")]

    @staticmethod
    def on(s, op, txt):
        if not parece_nombre(txt):
            return None
        s["data"]["pareja"] = txt.strip()[:80]
        return ([], "acc_metodo")


@etapa("acc_metodo")
class _AccMetodo:
    @staticmethod
    def ask(s):
        return [M(gracias(s) + "¿Cómo prefieres realizar tu pago?",
                  buttons=[("am_ofi", "En oficinas"), ("am_trans", "Transferencia")])]

    @staticmethod
    def on(s, op, txt):
        if op in ("am_ofi", "am_trans"):
            s["data"]["metodo"] = "En oficinas" if op == "am_ofi" else "Transferencia"
            return (pasar_a_humano(s, txt_pago(s, s.get("monto_inicio") or inicial(s)), venta=True), "pv_horario")
        return None


@etapa("pv_horario")
class _PvHorario:
    @staticmethod
    def ask(s):
        return [M("Para agilizar tu atención{}, ¿en qué *horario* prefieres que te contactemos?".format(nm(s)),
                  buttons=[("pvh_m", "Por la mañana"), ("pvh_t", "Por la tarde"), ("pvh_c", "Cualquier horario")])]

    @staticmethod
    def on(s, op, txt):
        m = {"pvh_m": "Por la mañana", "pvh_t": "Por la tarde", "pvh_c": "Cualquier horario"}
        if op in m:
            s["data"]["horario_contacto"] = m[op]
        elif len(txt.strip()) >= 3 and "?" not in txt:
            s["data"]["horario_contacto"] = txt.strip()[:80]
        else:
            return None
        return ([], "pv_docs")


@etapa("pv_docs")
class _PvDocs:
    @staticmethod
    def ask(s):
        doc = ("las *actas de nacimiento de tus hijos*" if s.get("servicio") == "pension"
               else "tu *acta de matrimonio*")
        return [M(gracias(s) + "Una pregunta más para adelantar tu expediente: ¿ya tienes a la mano {}?".format(doc),
                  buttons=[("pvd_si", "Sí, la tengo"), ("pvd_no", "Todavía no")])]

    @staticmethod
    def on(s, op, txt):
        if op in ("pvd_si", "pvd_no"):
            s["data"]["documentos"] = "Ya los tiene" if op == "pvd_si" else "Todavía no"
            extra = ("¡Excelente! Tenlos listos para tu visita."
                     if op == "pvd_si" else
                     "No te preocupes, no es necesario para iniciar; nuestro equipo te orienta para obtenerlos.")
            return ([M(gracias(s) + extra + " Todo quedó anotado en tu expediente. 📁")], "pv_mas")
        return None


MAS_SERVICIOS = [
    ("ms_pension", "Pensión alimenticia", "Trámite de pensión para tus hijos"),
    ("ms_conv", "Convivencia con hijos", "Cuando no te dejan verlos"),
    ("ms_acta", "Acta de divorcio", "Trámite de tu acta al terminar"),
    ("ms_suc", "Testamento o sucesión", "Herencias, testamentos e intestados"),
    ("ms_lab", "Asunto laboral", "Despidos, liquidaciones y contratos"),
    ("ms_emp", "Contratos y marcas", "Contratos, marcas y empresas"),
    ("ms_no", "Ninguno por ahora", "Solo mi trámite actual"),
]


@etapa("pv_mas")
class _PvMas:
    @staticmethod
    def ask(s):
        rows = [r for r in MAS_SERVICIOS
                if not (r[0] == "ms_pension" and s.get("servicio") in ("pension", "incausado"))]
        return [M("Por cierto{}: además de tu trámite, también podemos apoyarte en otros asuntos con la "
                  "misma atención. ¿Te interesa que te orientemos en alguno? Toca *Ver servicios* 👇".format(nm(s)),
                  rows=rows, list_button="Ver servicios")]

    @staticmethod
    def on(s, op, txt):
        nombres = {r[0]: r[1] for r in MAS_SERVICIOS}
        if op == "ms_no":
            return ([M("Perfecto{}. Si más adelante necesitas algo, aquí estamos. Cualquier duda sobre tu "
                       "trámite, escríbela por aquí y con gusto te atendemos. 🤝".format(nm(s)))], "post")
        if op in nombres:
            anotar(s, "interes_adicional", nombres[op])
            print("LEAD " + json.dumps({"tel": s.get("tel"), **s["data"]}, ensure_ascii=False), flush=True)
            return ([M("¡Con gusto{}! Anotamos tu interés en *{}*. Nuestro equipo te dará los detalles cuando "
                       "se comunique contigo.\n\nSi tienes alguna duda, escríbela por aquí.".format(
                           nm(s), nombres[op]))], "post")
        return None


@etapa("post")
class _Post:
    """Después del pase al equipo: el bot contesta dudas y anota lo que no sabe."""
    @staticmethod
    def ask(s):
        return []

    @staticmethod
    def on(s, op, txt):
        low = norm(txt)
        if not low:
            return ([], "post")
        r = faq(s, low)
        extra = venta_adicional(s, low)
        if r or extra:
            return ([M("\n\n".join(x for x in (r, extra) if x)
                       + "\n\n¿Tienes alguna otra duda? Con gusto te atendemos.")], "post")
        if low in ("gracias", "muchas gracias", "ok gracias", "mil gracias", "gracias muy amable"):
            return ([M("¡Gracias a ti{}! Estamos para servirte. 🤝".format(nm(s)))], "post")
        if low in ("hola", "buenas", "buenos dias", "buenas tardes", "buenas noches", "buen dia"):
            return ([M("¡Hola{}! Seguimos atentos a tu trámite. Nuestro equipo se pondrá en contacto contigo "
                       "en breve; si tienes alguna duda, escríbela por aquí.".format(nm(s)))], "post")
        pregunta = "?" in txt or low.split(" ")[0] in PALABRAS_PREGUNTA or "duda" in low or "pregunta" in low
        if pregunta and s.get("notas_post", 0) < 3:
            s["notas_post"] = s.get("notas_post", 0) + 1
            if low in ("tengo una duda", "una duda", "duda", "tengo dudas", "tengo una pregunta", "una pregunta"):
                return ([M("Con gusto{}. Cuéntanos tu duda y te la resolvemos.".format(nm(s)))], "post")
            prev = s["data"].get("dudas")
            s["data"]["dudas"] = ((prev + " | ") if prev else "") + txt.strip()[:200]
            return ([M(gracias(s) + "Anotamos tu pregunta en tu expediente para que nuestro equipo jurídico "
                       "te la responda a detalle según tu caso.")], "post")
        if len(low.split()) >= 6 and s.get("notas_post", 0) < 5:
            s["notas_post"] = s.get("notas_post", 0) + 1
            anotar(s, "situacion", txt)
            return ([M(gracias(s) + "Anotamos lo que nos cuentas en tu expediente para que nuestro equipo "
                       "jurídico lo revise con detalle.")], "post")
        return ([], "post")


@etapa("duda_mas")
class _DudaMas:
    @staticmethod
    def ask(s):
        return [M("¿Tienes alguna otra duda{}?".format(nm(s)),
                  buttons=[("dm_si", "Sí, otra duda"), ("dm_no", "No, continuar")])]

    @staticmethod
    def on(s, op, txt):
        vuelta = "a_medida" if s.get("medida_vista") else "cierre"
        if op == "dm_si":
            return ([], "duda")
        if op == "dm_no":
            return ([], vuelta)
        return _Duda.on(s, op, txt)


@etapa("ex_redirige")
class _ExRedirige:
    @staticmethod
    def ask(s):
        return [M("Entendemos{}. Si tu pareja no quiere firmar, o no tienes la certeza de que lo haga, "
                  "no te preocupes: existe el *Divorcio Incausado*, que no necesita su firma ni su permiso.\n\n"
                  "¿Cómo ves tu situación?".format(nm(s)),
                  buttons=[("exr_inc", "No va a firmar"), ("exr_ns", "No estoy seguro"), ("exr_si", "Sí va a firmar")])]

    @staticmethod
    def on(s, op, txt):
        volver = s.get("volver") or "cierre"
        if op == "exr_inc":
            for k in ("modalidad", "plan_txt", "metodo", "prisa"):
                s["data"].pop(k, None)
            s["servicio"] = "incausado"
            s["data"]["servicio_nombre"] = "Divorcio Incausado"
            s["data"]["acuerdo"] = "No"
            s["neg"] = 0
            s["inicial"] = None
            s["plan"] = None
            s["en_oferta"] = False
            return ([M("Perfecto{}, cambiamos tu trámite a *Divorcio Incausado*. Te haremos unas preguntas "
                       "para definir la estrategia.".format(nm(s)))], "in_dom")
        if op == "exr_ns":
            s["data"]["acuerdo"] = "No está seguro(a)"
            return ([M("Te recomendamos platicarlo primero con tu pareja. Si acepta, seguimos con el Divorcio "
                       "Express, que es más rápido y económico; si no, cambiamos a Divorcio Incausado sin "
                       "ningún problema. Mientras tanto, tu trámite queda como está.")], volver)
        if op == "exr_si":
            s["data"]["acuerdo"] = "Sí"
            return ([M("Perfecto{}, continuamos con tu Divorcio Express.".format(nm(s)))], volver)
        return None


@etapa("humano")
class _Humano:
    @staticmethod
    def ask(s):
        return []

    @staticmethod
    def on(s, op, txt):
        return ([], "humano")


# ---------------------------------------------------------------------------
# Preguntas frecuentes (se contestan en cualquier momento y se retoma la pregunta)
# ---------------------------------------------------------------------------
PALABRAS_PREGUNTA = ("cuanto", "cuanta", "cuantos", "como", "donde", "cuando", "que", "cual", "tienen",
                     "aceptan", "puedo", "puedes", "y", "pero", "entonces")
NO_FIRMA = ("no quiere firmar", "no va a firmar", "no quiera firmar", "no firma", "no se si firm",
            "no esta de acuerdo", "no creo que firme", "se niega a firmar", "no quiere divorciarse",
            "no quiere el divorcio", "no quiera divorciarse", "no acepta el divorcio", "no acepta firmar")
DUDOSAS = ("no estoy seguro", "no estoy segura", "no esta seguro", "no esta segura", "quiza no", "tal vez no",
           "a lo mejor no", "no sabe si", "no se si quiera", "no se si acepte", "se niega", "no acepta")
SOBRE_PAREJA = ("firm", "pareja", "espos", "marido", "mi mujer", "divorci", " el ", " ella ")


def no_firma(low):
    if any(w in low for w in NO_FIRMA):
        return True
    t = " " + low + " "
    return any(w in low for w in DUDOSAS) and any(w in t for w in SOBRE_PAREJA)



def faq(s, low):
    """Junta hasta 3 respuestas cuando el cliente pregunta varias cosas en un mensaje."""
    k = s.get("servicio")
    out = []
    if no_firma(low) and k != "express":
        out.append("Si tu pareja no quiere firmar, existe el *Divorcio Incausado*: no necesitas su firma "
                   "ni su permiso para divorciarte.")
    if "pension" in low:
        if k == "express":
            out.append("*Sobre la pensión:* en el Divorcio Express queda definida en el convenio que ambos "
                       "firman (monto, forma y fechas de pago), y el juez lo aprueba.")
        elif k == "incausado":
            out.append("*Sobre la pensión:* al contratar el Divorcio Incausado, el trámite de pensión "
                       "alimenticia va incluido. El abogado define la mejor estrategia según tu caso.")
        else:
            out.append("*Sobre la pensión:* la fija un juez, tomando en cuenta las necesidades de tus hijos "
                       "y las posibilidades de quien debe darla.")
    if any(w in low for w in ("bienes", "la casa", "terreno", "el carro", "propiedad", "propiedades")):
        if k == "incausado":
            out.append("*Sobre los bienes:* en tu asesoría el abogado define la mejor estrategia según tu "
                       "caso, para cuidar tus intereses.")
        else:
            out.append("*Sobre los bienes:* en el convenio pueden dejar definida la división de los bienes "
                       "que tengan en común.")
    if any(w in low for w in ("custodia", "convivencia", "con quien se quedan", "mis hijos", "los ninos")):
        if k == "incausado":
            out.append("*Sobre tus hijos:* la custodia y las convivencias se definen con la estrategia que "
                       "el abogado arma según tu caso.")
        else:
            out.append("*Sobre tus hijos:* el convenio deja por escrito la custodia y las convivencias, "
                       "para que todo quede claro y protegido.")
    if any(w in low for w in ("juzgado", "tengo que ir", "cuantas veces", "audiencia")) and "ratific" not in low:
        if k == "incausado":
            out.append("*Sobre el juzgado:* acudes dos veces, primero a ratificar tu demanda y después a la "
                       "audiencia preliminar. En ambas te acompañamos.")
        elif k == "pension":
            out.append("*Sobre el juzgado:* acudes solo tú a una cita, con tu INE.")
        else:
            out.append("*Sobre el juzgado:* hay una sola cita, 15 a 20 días después de presentar la demanda, "
                       "a la que acuden ambos.")
    base = _faq_base(s, low)
    if base and not (out and base.startswith("Con gusto te seguimos atendiendo")):
        out.append(base)
    return "\n\n".join(out[:3]) if out else None


def _faq_base(s, low):
    k = s.get("servicio")
    if any(w in low for w in ("total", "cuanto voy a pagar", "cuanto termino pagando", "cuanto seria todo")):
        return TOTAL_TXT
    if "ratific" in low and any(w in low for w in ("cuando", "fecha", "dia")):
        return ("La fecha la asigna el juzgado y depende del tiempo que tarde en procesar tu documentación. "
                "Aproximadamente es de 7 a 15 días hábiles después de presentar tu demanda. En cuanto el "
                "juzgado nos la confirme, te avisamos de inmediato por este medio.")
    if "ratific" in low:
        return ("El día de la ratificación te acompañamos al juzgado y tu procedimiento inicia formalmente "
                "con su número de expediente. Por eso una parte de tu plan se cubre un día antes de esa "
                "fecha, y así tus pagos semanales quedan más bajos.")
    if any(w in low for w in ("cuanto tarda", "cuanto tiempo", "cuanto dura", "duracion", "tardan", "demora")):
        if k == "incausado":
            return ("El juzgado te cita a ratificar aproximadamente 7 a 15 días hábiles después de presentar "
                    "la demanda, y la audiencia preliminar llega 30 a 60 días hábiles después de ratificar.")
        return "El trámite tarda aproximadamente de 30 a 45 días hábiles."
    if any(w in low for w in ("cuanto cuesta", "precio", "costo", "cuanto cobran", "cuanto sale", "cuanto es")):
        if k:
            return ("Tu trámite de {} es de {} de contado, y también puedes iniciar con {} y pagar "
                    "el resto a plazos.").format(svc(s)["nombre"], pesos(svc(s)["base"]), pesos(inicial(s)))
        return ("El Divorcio Express y la Pensión Alimenticia son de {} de contado, y el Divorcio "
                "Incausado desde {}. En todos puedes iniciar con un pago inicial y el resto a plazos."
                ).format(pesos(SERVICIOS["express"]["base"]), pesos(SERVICIOS["incausado"]["base"]))
    if any(w in low for w in ("requisito", "documento", "papeles", "que necesito", "que ocupo")):
        return REQUISITOS
    if any(w in low for w in ("ubicacion", "direccion", "donde estan", "donde se encuentran", "oficina", "domicilio de ustedes")):
        return "📍 *Nuestras oficinas:* " + OFICINAS
    if any(w in low for w in ("horario", "a que hora", "abren", "cierran")):
        return "🕘 Atendemos de " + HORARIO
    if "privacidad" in low:
        return "Aquí puedes ver nuestro aviso de privacidad:\n" + PUBLIC_URL + "/privacidad"
    if "factura" in low:
        return "Ese punto lo revisas directamente con el abogado al formalizar tu contratación."
    if any(w in low for w in ("transferencia", "deposito", "efectivo", "tarjeta", "como pago", "formas de pago", "medios de pago")):
        return ("Aceptamos transferencia, depósito en banco y efectivo en nuestras oficinas. "
                "Los medios de pago te los proporciona nuestro equipo al formalizar.")
    if "fiador" in low:
        return ("El fiador alimentista es cualquier persona con INE que acompaña el día de la cita en el "
                "juzgado a quien no tendrá la custodia. Solo se requiere cuando hay hijos menores.")
    if any(w in low for w in ("asesor", "humano", "una persona", "alguien", "abogado", "llamar", "telefono", "llamada")):
        return ("Con gusto te seguimos atendiendo por este medio. Si lo prefieres, también puedes "
                "llamarnos a nuestra línea directa: 📞 {}".format(LINEA))
    if any(w in low for w in ("garantia", "garantizan", "seguro que", "es seguro")):
        return ("Trabajamos con seriedad y transparencia. " + CONFIANZA +
                " En tu asesoría el abogado define la mejor estrategia para tu caso.")
    return None


ETAPAS_CIERRE = ("cierre", "fin_tipo", "etapas", "semanal", "plan", "obj1", "obj_precio", "dos_exh",
                 "obj_pensar", "oferta", "duda_mas", "a_medida", "nudge")
SIN_DINERO = ("no tengo dinero", "no tengo el dinero", "no me alcanza", "no puedo pagar", "no puedo pagarlo",
              "muy caro", "esta caro", "es caro", "es mucho", "no tengo para", "no cuento con", "ahorita no puedo",
              "no tengo ahorita", "sin dinero", "no traigo", "no completo", "no tengo tanto", "muy alto", "muy altos")
SE_DESPIDE = ("gracias", "muchas gracias", "ok gracias", "okey gracias", "gracias luego", "luego", "despues",
              "al rato", "lo pienso", "lo voy a pensar", "lo pensare", "dejame pensarlo", "deja lo pienso",
              "te aviso", "les aviso", "yo les aviso", "luego les escribo", "luego les aviso", "lo checo",
              "lo platico", "lo voy a platicar", "adios", "bye", "hasta luego", "no gracias", "gracias por la informacion",
              "gracias por la info", "ya vere", "voy a ver", "lo consulto")
ETAPAS_REDIRIGE = ETAPAS_CIERRE + ("duda", "ex_hijos", "ex_bienes", "ex_ciudad", "ex_prisa", "acc_nombre",
                                   "acc_pareja", "acc_metodo", "pv_horario", "pv_docs", "post")

PELIGRO = ("me golpe", "me pega", "me amenaz", "tengo miedo", "estoy en peligro", "me quiere matar",
           "me esta agrediendo", "violencia")


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------
def elegir(s, raw):
    opts = s.get("opts") or []
    if not opts:
        return None
    ids = [o[0] for o in opts]
    if raw in ids:
        return raw
    low = norm(raw)
    if not low:
        return None
    for oid, title in opts:
        if low == norm(title):
            return oid
    if low.isdigit() and 1 <= int(low) <= len(opts):
        return opts[int(low) - 1][0]
    si = [o for o in ids if o.endswith("_si")]
    no = [o for o in ids if o.endswith("_no")]
    if low in SI and len(si) == 1:
        return si[0]
    if low in NO and len(no) == 1:
        return no[0]
    cand = [oid for oid, title in opts
            if len(low) >= 4 and (low in norm(title)
                                  or (len(norm(title)) >= 6 and (" " + norm(title) + " ") in (" " + low + " ")))]
    if len(cand) == 1:
        return cand[0]
    return None


def preguntar(s, stage):
    """Avanza por etapas sin pregunta (ask vacío) hasta llegar a una con pregunta."""
    for _ in range(6):
        msgs = ASK[stage](s)
        if msgs or stage in ("humano", "espera", "post"):
            s["stage"] = stage
            return msgs
        res = ON[stage](s, None, "")
        if not res:
            s["stage"] = stage
            return []
        stage = res[1]
    s["stage"] = stage
    return []


def fijar_opts(s, msgs):
    s["opts"] = []
    for m in msgs:
        if m.get("buttons"):
            s["opts"] = [(b[0], b[1]) for b in m["buttons"]]
        elif m.get("rows"):
            s["opts"] = [(r[0], r[1]) for r in m["rows"]]
    # Se recuerda de qué etapa es cada botón, por si el cliente toca uno de un mensaje anterior.
    hist = s.setdefault("hist", {})
    for oid, _t in s["opts"]:
        hist[oid] = s["stage"]
    while len(hist) > 60:
        hist.pop(next(iter(hist)))


def unir(pre, ask):
    """Une el texto previo con la pregunta para mandar menos mensajes."""
    if pre and ask and len(pre) == 1 and not pre[0].get("buttons") and not pre[0].get("rows"):
        junto = pre[0]["text"] + "\n\n" + ask[0]["text"]
        if len(junto) <= 1000:
            primero = dict(ask[0])
            primero["text"] = junto
            return [primero] + ask[1:]
    return pre + ask


def handle_message(sender, raw, kind="text"):
    """Devuelve la lista de mensajes a enviar a `sender`."""
    now = time.time()
    s = SESSIONS.get(sender)
    if s is None:
        s = SESSIONS[sender] = nueva_sesion()
    s["tel"] = sender
    previo = s.get("last_in") or 0
    s["last_in"] = now
    s["avisos"] = 0
    low = norm(raw)

    if s["opted_out"]:
        if low in ("hola", "menu", "alta", "inicio"):
            s["opted_out"] = False
            s["stage"] = "nuevo" if not s["data"].get("nombre") else "menu"
        else:
            return []
    if low in ("baja", "alto", "stop", "no me escriban", "dejen de escribirme"):
        s["opted_out"] = True
        return [M("Listo, no te enviaremos más mensajes. Si más adelante necesitas ayuda, "
                  "escríbenos *hola* y con gusto te atendemos.")]

    regreso = False
    if s["stage"] == "humano":
        if now < s["paused_until"]:
            return []
        regreso = True
    elif (previo and now - previo > 72 * 3600
          and s["stage"] not in ("nuevo", "nombre", "oferta_vigencia", "espera")):
        regreso = True
    if regreso:
        s["neg"] = 0
        s["misses"] = 0
        if not s["data"].get("nombre"):
            s["stage"] = "nuevo"
        else:
            msgs = preguntar(s, "menu")
            fijar_opts(s, msgs)
            msgs[0] = dict(msgs[0], text="¡Hola de nuevo, {}! ".format(s["data"]["nombre"]) + TXT_MENU)
            return msgs

    if s["stage"] == "nuevo":
        if len(low.split()) >= 6:
            anotar(s, "situacion", raw)
        destino = detectar_servicio(low)
        if destino:
            s["intent"] = destino
        msgs = preguntar(s, "nombre")
        fijar_opts(s, msgs)
        return msgs

    if kind == "audio":
        msgs = ASK[s["stage"]](s)
        fijar_opts(s, msgs)
        return [M("Por este medio no podemos escuchar audios. ¿Nos lo escribes, por favor? 🙏")] + msgs

    if low in ("menu", "inicio", "0", "volver al menu", "ver menu", "ver el menu"):
        msgs = preguntar(s, "menu")
        fijar_opts(s, msgs)
        return msgs

    stage = s["stage"]
    op = elegir(s, raw.strip())
    viejo = s.get("hist", {}).get(raw.strip())
    if op is None and viejo and viejo in ASK and viejo not in ("menu", "otros") and stage not in ("post", "humano"):
        # Botón de un mensaje anterior: se retoma esa etapa.
        s["stage"] = stage = viejo
        fijar_opts(s, ASK[viejo](s))
        op = elegir(s, raw.strip())
    if stage in ("menu", "otros") and low.isdigit():
        op = "m" + low if 1 <= int(low) <= 9 else None
    if op is None and stage in ("menu", "otros", "nombre", "duda") and any(p in low for p in PELIGRO):
        return urgente(s, "Posible situación de violencia o peligro: " + raw.strip()[:150])

    # El cliente de Divorcio Express dice que su pareja quizá no firme: se le redirige.
    if (op is None and s.get("servicio") == "express" and stage in ETAPAS_REDIRIGE
            and no_firma(low)):
        s["volver"] = "post" if stage in ("post", "pv_horario", "pv_docs") else "cierre"
        msgs = preguntar(s, "ex_redirige")
        fijar_opts(s, msgs)
        return msgs
    # "Tengo una duda" escrito durante el cierre.
    if (op is None and stage in ETAPAS_CIERRE and ("duda" in low or "pregunta" in low) and not faq(s, low)):
        msgs = preguntar(s, "duda")
        fijar_opts(s, msgs)
        return msgs

    # El cliente se despide o dice que no puede pagar durante el cierre: se intenta retenerlo.
    if op is None and stage in ETAPAS_CIERRE and not faq(s, low):
        r_ret = None
        if any(w in low for w in SIN_DINERO):
            s["neg"] = max(s["neg"], 1)
            anotar(s, "objecion", raw)
            r_ret = ([], "a_medida") if not (stage == "a_medida") else None
        elif low in SE_DESPIDE or (low.startswith("gracias") and len(low.split()) <= 5):
            r_ret = negativa(s)
        if r_ret:
            ask = preguntar(s, r_ret[1])
            fijar_opts(s, ask)
            return unir(r_ret[0], ask)

    res = None
    es_pregunta = "?" in raw or low.split(" ")[0] in PALABRAS_PREGUNTA
    en_menu = stage in ("menu", "otros") and detectar_servicio(low)
    if (op is None and stage not in ("duda", "post") and not en_menu
            and (es_pregunta or s.get("opts")) and faq(s, low)):
        res = None
    else:
        res = ON[stage](s, op, raw)

    if res is None:
        r = faq(s, low)
        ask = ASK[stage](s)
        fijar_opts(s, ask)
        if r and not (stage in ("menu", "otros") and len(low.split()) >= 6):
            return unir([M(r)], ask)
        extra = venta_adicional(s, low)
        largo = len(low.split()) >= 6
        if stage in ("menu", "otros") and (largo or extra):
            # Asunto que no está en el menú: se anota y se ofrece asesoría.
            s["data"]["motivo"] = raw.strip()[:200]
            ask = preguntar(s, "ci_tipo")
            fijar_opts(s, ask)
            return [M("Gracias por contárnoslo{}. Por supuesto que podemos ayudarte. Lo más conveniente es "
                      "que uno de nuestros abogados revise tu caso en una asesoría.".format(nm(s)))] + ask
        if largo or extra:
            anotar(s, "situacion", raw)
            partes = ["Gracias por contárnoslo{}. Lo anotamos en tu expediente para que nuestro equipo "
                      "jurídico lo revise con detalle.".format(nm(s))]
            if extra:
                partes.append(extra)
            partes.append("Para seguir avanzando con tu trámite 👇")
            return unir([M("\n\n".join(partes))], ask)
        s["misses"] += 1
        aviso = "Para continuar, elige una de las opciones 👇" if s["opts"] else "¿Nos lo puedes escribir de nuevo, por favor?"
        if s["misses"] >= 3:
            s["misses"] = 0
            aviso += "\n\nSi lo prefieres, también puedes llamarnos a nuestra línea directa: 📞 " + LINEA
        return [M(aviso)] + ask

    s["misses"] = 0
    pre, nxt = res
    if nxt.startswith("menu>"):
        s["stage"] = "menu"
        r2 = ON["menu"](s, nxt[5:], "")
        pre = pre + r2[0]
        nxt = r2[1]
    ask = preguntar(s, nxt)
    out = unir(pre, ask)
    fijar_opts(s, ask)
    return out


# ---------------------------------------------------------------------------
# Envío por la Graph API
# ---------------------------------------------------------------------------
def _post_graph(payload):
    token = os.environ.get("WHATSAPP_TOKEN", "")
    phone_id = os.environ.get("PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        print("SIN TOKEN (simulación):", json.dumps(payload, ensure_ascii=False)[:300], flush=True)
        return None
    req = urllib.request.Request(
        "{}/{}/messages".format(GRAPH_URL, phone_id),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode() or "{}")
            mid = (data.get("messages") or [{}])[0].get("id")
            if mid:
                SENT_IDS.append(mid)
                del SENT_IDS[:-500]
            return mid
    except Exception as e:  # noqa: BLE001
        detalle = ""
        if hasattr(e, "read"):
            try:
                detalle = e.read().decode()[:300]
            except Exception:
                pass
        print("ERROR WhatsApp API:", e, detalle, flush=True)
        return None


def construir_payload(to, m):
    base = {"messaging_product": "whatsapp", "to": to}
    if m.get("buttons"):
        base.update({"type": "interactive", "interactive": {
            "type": "button", "body": {"text": m["text"][:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": b[0], "title": b[1][:20]}}
                                   for b in m["buttons"][:3]]}}})
    elif m.get("rows"):
        base.update({"type": "interactive", "interactive": {
            "type": "list", "body": {"text": m["text"][:1024]},
            "action": {"button": m.get("list_button", "Ver opciones")[:20],
                       "sections": [{"title": "Opciones", "rows": [
                           {"id": r[0], "title": r[1][:24], "description": r[2][:72]}
                           for r in m["rows"][:10]]}]}}})
    else:
        base.update({"type": "text", "text": {"body": m["text"][:4096]}})
    return base


def send_messages(to, messages):
    for m in messages:
        _post_graph(construir_payload(to, m))
        time.sleep(0.4)


# ---------------------------------------------------------------------------
# Recordatorio de la oferta (solo dentro de las 24 h del último mensaje del cliente)
# ---------------------------------------------------------------------------
SIN_AVISO = ("nuevo", "nombre", "post", "espera", "humano", "oferta_vigencia", "pv_horario", "pv_docs",
             "pv_mas", "nudge")


def revisar_inactividad(now):
    """Un recordatorio a los 10 minutos de silencio y otro a las 20 horas (solo en el cierre),
    siempre dentro de las 24 horas del último mensaje del cliente."""
    enviados = []
    for tel, s in list(SESSIONS.items()):
        if s.get("opted_out") or not s.get("last_in"):
            continue
        quieto = now - s["last_in"]
        if quieto >= 23.5 * 3600:
            continue
        stage = s.get("stage")
        avisos = s.get("avisos", 0)
        if avisos == 0 and quieto >= AVISO_INACTIVIDAD_MIN * 60 and stage not in SIN_AVISO:
            s["avisos"] = 1
            if stage in ETAPAS_CIERRE:
                msgs = preguntar(s, "nudge")
            else:
                msgs = ASK[stage](s)
                if msgs:
                    msgs = [M("¿Sigues ahí{}? 🙂 Con gusto continuamos con tu trámite.".format(nm(s)))] + msgs
            fijar_opts(s, msgs)
            enviados.append((tel, msgs))
        elif avisos == 1 and quieto >= RECORDATORIO_HORAS * 3600 and stage in ETAPAS_CIERRE:
            s["avisos"] = 2
            msgs = preguntar(s, "nudge")
            msgs[0] = dict(msgs[0], text="Hola{}. Seguimos con la mejor disposición de ayudarte con tu trámite. "
                           "¿Te armamos un plan *exclusivo a tu medida*?".format(nm(s)))
            fijar_opts(s, msgs)
            enviados.append((tel, msgs))
    return enviados


def recordatorios():
    while True:
        time.sleep(60)
        try:
            with LOCK:
                now = time.time()
                for tel, msgs in revisar_inactividad(now):
                    if msgs:
                        send_messages(tel, msgs)
                for tel, s in list(SESSIONS.items()):
                    if (s.get("stage") == "oferta_vigencia" and not s.get("reminded")
                            and not s.get("opted_out") and s.get("offer_ts")
                            and RECORDATORIO_HORAS * 3600 <= now - s["offer_ts"] < 23.5 * 3600
                            and now - s.get("last_in", 0) < 23.5 * 3600):
                        s["reminded"] = True
                        m = M("Hola{}. Tu oferta exclusiva para comenzar tu trámite con {} vence en unas "
                              "horas. ¿Te gustaría aprovecharla?".format(nm(s), pesos(svc(s)["oferta"])),
                              buttons=[("rec_si", "Sí, quiero comenzar"), ("rec_no", "No, gracias")])
                        s["opts"] = [("rec_si", "Sí, quiero comenzar"), ("rec_no", "No, gracias")]
                        send_messages(tel, [m])
                guardar_sesiones()
        except Exception as e:  # noqa: BLE001
            print("ERROR recordatorios:", e, flush=True)


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
PRIVACY_HTML = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Aviso de Privacidad — Divorcio Express Saltillo</title></head>
<body style="font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px">
<h1>Aviso de Privacidad — Divorcio Express Saltillo</h1>
<p>Última actualización: 16 de noviembre de 2026.</p>
<p>Divorcio Express Saltillo (Saltillo, Coahuila, México) opera un asistente
automático por WhatsApp para atender a sus clientes.</p>
<h2>Datos que recopilamos</h2>
<p>Cuando usted nos escribe por WhatsApp, recibimos su número de teléfono, su
nombre y la información que usted decida compartir sobre su asunto (por
ejemplo, datos de su pareja o expareja, de sus hijos y de su situación
familiar), únicamente para orientarle, cotizar el servicio, integrar su
expediente, agendar una cita y dar seguimiento a su contratación y pagos.</p>
<h2>Uso de los datos</h2>
<p>Sus datos se usan solo para la atención de su caso. No se venden, no se
comparten con terceros con fines publicitarios y no se usan para ningún
otro fin.</p>
<h2>Sus derechos</h2>
<p>Usted puede pedir en cualquier momento que dejemos de escribirle o que
eliminemos sus datos, escribiendo "baja" por WhatsApp o llamando a la
Línea Directa (844) 688-01-88.</p>
<h2>Contacto</h2>
<p>Divorcio Express Saltillo — WhatsApp (844) 538-03-91 — Línea Directa
(844) 688-01-88 — Blvd. Jesús Valdés Sánchez esquina con Abasolo, Plaza Santa
Lucía, segunda planta, oficina 15, Saltillo, Coahuila, México.</p>
</body></html>"""


def procesar(body):
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            # Mensajes que el equipo manda desde la app de WhatsApp Business:
            # el bot guarda silencio con ese cliente para no estorbar.
            for eco in value.get("message_echoes", []) or []:
                if eco.get("id") in SENT_IDS:
                    continue
                to = eco.get("to")
                if to:
                    s = SESSIONS.setdefault(to, nueva_sesion())
                    s["stage"] = "humano"
                    s["paused_until"] = time.time() + HANDOFF_HOURS * 3600
            for msg in value.get("messages", []) or []:
                sender = msg.get("from", "")
                mid = msg.get("id")
                if not sender or (mid and mid in SEEN_IDS):
                    continue
                if mid:
                    SEEN_IDS.append(mid)
                    del SEEN_IDS[:-1000]
                tipo = msg.get("type")
                kind = "text"
                text = ""
                if tipo == "text":
                    text = msg.get("text", {}).get("body", "")
                elif tipo == "interactive":
                    inter = msg.get("interactive", {})
                    r = inter.get("button_reply") or inter.get("list_reply") or {}
                    text = r.get("id", "") or r.get("title", "")
                elif tipo == "button":
                    text = msg.get("button", {}).get("text", "")
                elif tipo in ("audio", "voice"):
                    kind, text = "audio", "[audio]"
                elif tipo in ("image", "document", "video", "sticker", "location", "contacts"):
                    text = "[archivo recibido]"
                if text:
                    send_messages(sender, handle_message(sender, text, kind))
    guardar_sesiones()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
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
        if (q.get("hub.mode", [""])[0] == "subscribe" and os.environ.get("VERIFY_TOKEN")
                and q.get("hub.verify_token", [""])[0] == os.environ.get("VERIFY_TOKEN")):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(q.get("hub.challenge", [""])[0].encode())
            return
        if path in ("/", "/salud", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
            return
        self.send_response(403)
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        secret = os.environ.get("APP_SECRET", "")
        if secret:
            firma = self.headers.get("X-Hub-Signature-256", "")
            esperado = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(firma, esperado):
                self.send_response(403)
                self.end_headers()
                return
        # Responder de inmediato a Meta y procesar después.
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")
        self.wfile.flush()
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return
        try:
            with LOCK:
                procesar(body)
        except Exception as e:  # noqa: BLE001
            print("ERROR procesando:", e, flush=True)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    cargar_sesiones()
    threading.Thread(target=recordatorios, daemon=True).start()
    port = int(os.environ.get("PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
