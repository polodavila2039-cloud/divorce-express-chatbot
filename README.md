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
   una cita o es un caso urgente. Después del pase el bot sigue atento:
   agradece, pregunta horario de contacto y documentos, contesta dudas y
   anota en el expediente las que no sabe. Si el cliente de Divorcio Express
   dice que su pareja quizá no firme, lo redirige a Divorcio Incausado.
6. "baja" detiene los mensajes; "menú" regresa al menú.

## Retención

- Si el cliente se despide ("gracias", "luego les aviso") o dice que no puede
  pagar durante el cierre, el bot pregunta qué no le convenció y ofrece un plan
  a la medida: pago inicial de oferta y plazo más largo (`PLAZOS_EXTRA`), sin
  subir el margen más allá del máximo de `PLANES`.
- Recordatorio a los 10 minutos de silencio y otro a las 20 horas (solo en el
  cierre), siempre dentro de las 24 horas del último mensaje del cliente.
- Lo que el cliente cuenta fuera del guion se anota en el expediente; si
  menciona otro asunto (sucesiones, laboral, etc.) se registra como interés.

## Cambiar precios o plazos

En `webhook.py`, al inicio: `SERVICIOS` (precio de contado, pago inicial,
oferta) y `PLANES` (semanas y porcentaje de aumento).

## Variables en Render

- `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN` (obligatorias)
- `APP_SECRET` (recomendada: valida que los avisos vengan de Meta)
- `HANDOFF_HOURS`, `PUBLIC_URL` (opcionales)

## Hoja de expedientes (Google)

`expedientes_apps_script.gs` se pega en el Apps Script de una hoja de Google y se
implementa como aplicación web. Con `EXPEDIENTES_URL` y `EXPEDIENTES_CLAVE` en
Render, el bot mantiene una fila por cliente (teléfono como llave) con su estado,
etapa, plan elegido y todo lo que contó.

## Límites conocidos

- Las conversaciones se guardan en memoria. En el plan gratuito de Render el
  servicio se duerme; al despertar, una conversación a medias se reinicia.
- El recordatorio de la oferta (a las 20 horas) solo sale si el servicio
  está despierto.
