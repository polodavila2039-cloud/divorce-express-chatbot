# Chatbot WhatsApp — Divorcio Express Saltillo

Estado: en preparación. Polo eligió la opción 2 (chatbot completo con API).
Ya tiene API de WhatsApp Business, cuenta de Meta Business y un número.
Token permanente: guardado por el enlace seguro y verificado el 2026-11-14 (Graph /me = whatsapp-api, id 122107468035539993).
Phone Number ID: 1422322744300738, verificado el 2026-11-14 por Graph API (+52 1 844 538 0391, Divorcio Express Saltillo).
WhatsApp Business Account ID: 1600411648433093, verificado el 2026-11-14 por Graph API (phones devuelve el mismo Phone Number ID 1422322744300738).
Falta: el catálogo completo (nombre, precio, descripción
de cada producto — se piden por captura, igual que para los videos), y la decisión del hosting del webhook / URL pública. WhatsApp Manager advierte que falta un método de pago válido para enviar mensajes fuera del periodo gratuito.

## Lo que hace el bot

1. Saluda y presenta el menú principal con botones.
2. Muestra el catálogo: nombre, precio y beneficio de cada producto.
3. Responde lo que más preguntan los clientes:
   - ¿Cuánto tarda? En Coahuila toma 30-45 días desde que se presenta
     la solicitud hasta la sentencia final (según el video original).
   - ¿Hay juicio o conflicto? No, es el proceso más rápido y económico
     para terminar un matrimonio cuando ambos cónyuges están de acuerdo.
   - ¿Hay financiamiento? Sí, pregunta por financiamiento.
4. Toma los datos del cliente (nombre, si es divorcio de mutuo acuerdo,
   teléfono) y los pasa a Polo para que un humano siga la conversación.
5. Si el cliente escribe "asesor" / "humano" / "hablar con alguien",
   el bot avisa que un asesor lo atenderá y deja de contestar solo.

## Archivos

- `FLOW.md` — guiones exactos de cada mensaje, listos para aprobar.
- `catalog.json` — primer producto llenado el 2026-11-14: PENSIÓN ALIMENTICIA, $8,500 (antes $12,500), financiamiento $2,500 de enganche y 24 pagos semanales de $599. Faltan los demás productos del catálogo.
- `webhook.py` — servidor webhook (solo librería estándar de Python).
  Verifica el webhook de Meta, recibe mensajes y contesta por la
  Graph API. No guarda ningún token en el código.
- `README.md` — cómo conectar el webhook en Meta y probarlo.

## Datos que faltan (bloquean la prueba real)

- Token permanente de WhatsApp (enlace seguro ya enviado a Polo).
- Phone Number ID y WhatsApp Business Account ID.
- Catálogo completo.
- Horario de atención y número / persona para pasar los clientes.
