# Chatbot de WhatsApp — Divorcio Express Saltillo (v8)

Chatbot de ventas guiado. No usa IA que improvise: sigue un guion fijo con
botones y listas, agradece cada dato, sigue preguntando y cierra por forma de pago.

## Qué hace

1. Pide el nombre y muestra los 3 servicios principales con botones; al escribir "otro" muestra los demás.
2. Divorcio Express, Divorcio Incausado y Pensión Alimenticia: preguntas de
   situación con botones, resumen y cierre (contado o financiamiento).
3. Objeciones: máximo dos insistencias. En Express y Pensión, la segunda
   negativa activa la oferta de $900, una sola vez y con vigencia de 24 horas.
4. Planes de pago calculados desde la tabla `PLANES` de `webhook.py`.
   El chat nunca muestra el total; ese desglose lo entrega el equipo.
5. Pasa a una persona del equipo solo cuando el cliente acepta pagar, pide
   una cita o es un caso urgente. Después guarda silencio con ese cliente
   durante `HANDOFF_HOURS` (24 por defecto).
6. "baja" detiene los mensajes; "menú" regresa al menú.

## Cambiar precios o plazos

En `webhook.py`, al inicio: `SERVICIOS` (precio de contado, pago inicial,
oferta) y `PLANES` (semanas y porcentaje de aumento).

## Variables en Render

- `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` (obligatorias)
- `APP_SECRET` (recomendada: valida que los avisos vengan de Meta)
- `HANDOFF_HOURS`, `PUBLIC_URL` (opcionales)

## Límites conocidos

- Las conversaciones se guardan en memoria. En el plan gratuito de Render el
  servicio se duerme; al despertar, una conversación a medias se reinicia.
- El recordatorio de la oferta (a las 20 horas) solo sale si el servicio
  está despierto.
