# Flujos del chatbot — Divorcio Express Saltillo
# Textos en español, listos para que Polo los apruebe o ajuste.
# Los precios y los nombres exactos de los productos se llenan
# con el catálogo; donde dice [PENDIENTE] falta ese dato.
#
# Menú 1-9 actualizado 2026-11-14: es el menú del mensaje de
# bienvenida de WhatsApp Business de Polo (captura 22:33 CST).
# El bot contesta con ese mismo menú, opción por opción.

## 1. Saludo inicial (cuando alguien escribe por primera vez o escribe "hola")

> ¡Hola! Gracias por contactar a Divorcio Express Saltillo ⚖️
> Estamos para servirte. ¿En qué te podemos ayudar?
> Responde con un NÚMERO:
> [1] Divorcio Express (mutuo acuerdo)
> [2] Divorcio Incausado (cuando NO quiere firmar)
> [3] Pensión alimenticia (trámite de pensión para menores)
> [4] Fui demandado/a (requiero atención urgente)
> [5] No me dejan ver a mis hijos
> [6] Me llegó citatorio de fiscalía (requiero atención urgente)
> [7] Quiero denunciar violencia de mi pareja
> [8] Requiero tramitar mi acta de Divorcio
> [9] Me gustaría agendar una cita con un abogado
> Solo escribe el número (1, 2, 3...) y te enviamos la info al instante 👇

## 1b. Respuestas por opción
> 1: Divorcio Exprés, 30-45 días en Coahuila, sin juicio ni conflicto.
> 2: Sí te puedes divorciar aunque no quiera firmar.
> 3: Pensión alimenticia, derecho de los hijos, parte del aguinaldo,
>    precio $8,500 MXN de contado (sin repetir el beneficio);
>    financiamiento solo lo explica un asesor.
> 4: Demandado/a, atención urgente, no dejar pasar los plazos.
> 5: No me dejan ver a mis hijos, derecho de convivencia.
> 6: Citatorio de fiscalía, atención urgente, no faltar.
> 7: Denunciar violencia, primero la seguridad (911 si hay peligro),
>    ayuda legal y asesor urgente.
> 8: Tramitar el acta de divorcio.
> 9: Agendar cita: nombre, mutuo acuerdo sí/no/no sé, teléfono.

## 2. Ver servicios y precios

> Estos son nuestros servicios:
> [se genera la lista desde catalog.json: nombre — precio — beneficio en 1 línea]
>
> ¿Cuál te interesa? Escríbeme su número o su nombre.
> Si quieres, también puedo pasarte con un asesor.

## 3. Detalle de un producto

> *[Nombre del producto]*
> Precio: [PENDIENTE]
> [Beneficio principal en 1-2 frases]
> Dato destacado: [tiempo / requisito — PENDIENTE]
>
> ¿Quieres que te agende una cita para este servicio? [Sí / Hablar con un asesor]

## 4. ¿Cuánto tarda?

> En Coahuila toma 30-45 días desde que presentamos la solicitud hasta la sentencia final.
> El tiempo exacto depende de tu caso, por eso te recomendamos agendar una cita para revisarlo.

## 5. Financiamiento

> Sí, tenemos financiamiento. Pregunta por financiamiento y un asesor te explica las opciones y los pagos.

<!-- Decisión de Polo, 2026-11-14: el bot NO cita los términos exactos de financiamiento; un asesor los explica. Los términos exactos quedan guardados en catalog.json solo como referencia para el asesor. -->
> ¿Quieres que te pase con un asesor? [Sí / Ver servicios]

## 6. Agendar / datos del cliente

> Claro, con gusto te agendo. Solo necesito:
> 1. Tu nombre completo
> 2. ¿El divorcio es de mutuo acuerdo? (sí / no / no sé)
> 3. Tu teléfono para confirmarte la cita
>
> En cuanto me los pases, le aviso a nuestro equipo.

## 7. Pasar con humano

Cliente escribe "asesor", "humano", "hablar con alguien" o pide cita:
> Perfecto, te paso con un asesor de Divorcio Express Saltillo. Te atenderá en horario de atención. Gracias por escribirnos.

El bot deja de contestar solo en ese chat hasta que Polo lo reactive.

## 7b. Privacidad

Cliente escribe "privacidad":
> Claro, aquí puedes ver nuestro aviso de privacidad:
> https://divorce-express-chatbot.onrender.com/privacidad

## 8. Mensaje fuera de horario / no entendido

> Gracias por tu mensaje. Nuestro equipo te atiende en horario de atención.
> Mientras tanto, puedes ver nuestros servicios escribiendo "catálogo", o preguntar por precio, tiempo o financiamiento.


## 9. Flujo completo Divorcio Incausado (texto de Polo, 2026-11-15) — v7

La opción 2 del menú ya no da una respuesta corta: inicia este flujo con
botones interactivos y formulario paso a paso. El estado vive en memoria
por número de teléfono (SESSIONS). Escribir "hola" reinicia al menú.

A. Identificar la situación
- Botón: "¿Ambas partes están de acuerdo en presentar el divorcio, o solo una persona quiere iniciarlo?"
  [Estamos de acuerdo] [Solo yo quiero]
- Si hay acuerdo → información de mutuo acuerdo (opción 1).
- Si solo una persona quiere → "¿Consideras que, si lograras comunicarte con tu pareja y le propusieras el divorcio, estaría dispuesto(a) a llegar a un acuerdo?" [Sí, creo que sí] [No, no creo]
- Si responde que no → "Perfecto, no hay ningún problema, podemos continuar con el trámite. Solo te haré algunas preguntas para definir la estrategia."

B. Preguntas para definir la estrategia (se guardan)
1. Domicilio de la expareja.
2. Familiares/amigos/conocidos en Saltillo o lugar donde pueda ser localizado(a).
   Si no conoce ninguno → "No te preocupes, continuamos con el trámite."
   Si da una ubicación → el equipo jurídico valora si procede para una notificación legal. NO se asegura que se pueda emplazar ahí sin revisión jurídica.
3. Trabajo fijo de la expareja y dónde.
4. ¿Paga pensión alimenticia a los hijos? [Sí] [No]
5. ¿Existió violencia por parte de la expareja? [Sí] [No]
   Si sí → primero seguridad (911 si hay peligro) y luego: "¿Cuentas con documentos de la denuncia?" [Sí, los tengo] [No]

C. Transición al formulario
> "¡Perfecto! Con la información que nos has proporcionado, podemos continuar con tu trámite de Divorcio Exprés Incausado, incluso si tu expareja no está de acuerdo o se niega a firmar..."

D. Formulario (una pregunta por mensaje; el cliente contesta con texto)
1. Nombre completo de quien contacta. 2. Nombre completo de la expareja.
3. Domicilio(s) para notificar. 4. Nombre de los hijos y sus edades.
5. Teléfono de quien contacta. 6. Teléfono de la expareja (opcional: escribir "saltar").
7. Lugar de trabajo de la expareja (opcional: escribir "saltar").
Al final se muestra la plantilla resumen "📋 Tu información:" con todos los datos
para que el cliente la revise, y se agradece. No se cierra la conversación.

E. Modalidad de pago [De contado] [Financiamiento]
F. Contado: $8,500 pesos. Método [En oficinas] [Transferencia].
   - Oficinas: se agenda día y hora; requisitos (acta de matrimonio, actas de nacimiento de ambos, actas de los hijos aunque sean mayores, comprobante de domicilio, INE); no necesita llevar todos los documentos al pagar; confirmación de cita con día y hora; pregunta de llamada de confirmación; despedida.
   - Transferencia: el bot NO envía datos bancarios; le dice al cliente que un asesor le compartirá los datos por el mismo chat en unos momentos (el equipo ve la solicitud en vivo en la app de WhatsApp Business y responde ahí mismo), o que puede llamar a la línea directa si prefiere; se pide la captura; el equipo verifica el depósito; NO se confirma el pago hasta verificar; luego se agenda la cita. No se vuelve a pedir información ya proporcionada.
G. Financiamiento: solo se cita el pago inicial de $3,500 pesos. Las demás modalidades y formas de pago las explica el equipo en oficinas (regla de Polo: el bot NO cita montos ni plazos del financiamiento). Método [En oficinas] [Transferencia], igual que en F.
H. Confirmación final (financiamiento): no es necesario llevar documentación a la cita; el equipo entrega la lista de requisitos; pregunta de llamada de confirmación; despedida.
I. Ubicación: el cliente escribe "ubicación"/"dirección"/"oficinas" en cualquier momento → Blvd. Jesús Valdés Sánchez esquina con Abasolo, Oficina #15, planta alta, Plaza Santa Lucía, Saltillo, Coahuila, C.P. 25284. El enlace de Google Maps aún no está disponible: se comparte cuando Polo lo tenga.
J. Atención personalizada: el cliente escribe "asesor"/"hablar con alguien" o pregunta algo fuera del flujo → Línea Directa (844) 688-01-88.
K. Reglas del bot: no repetir preguntas ni pedir datos ya dados; conservar los datos toda la conversación; no inventar datos bancarios; pedir la captura del comprobante cuando hay transferencia; no confirmar transferencias sin verificación del despacho; no garantizar resultados jurídicos; no asegurar que un domicilio de familiar/conocido valga para emplazar; dar el teléfono si piden atención humana; no cerrar antes de completar las etapas; lenguaje amable, profesional, claro y breve; emojis profesionales y con moderación (⚖️ 📋 💳 🏦 📍 📞 📅 ✅).

## 10. Datos bancarios
Los datos bancarios NO van en el flujo del bot (decisión de Polo, 2026-11-15): el bot nunca muestra tarjeta ni CLABE, ni en el código ni en variables de entorno. Cuando el cliente elige transferencia, el bot le dice que un asesor le compartirá los datos por el mismo chat en unos momentos — el equipo ve la solicitud en vivo en la app de WhatsApp Business y le responde ahí mismo — o que puede llamar a la línea directa si prefiere. Así el cliente no se enfría. Luego el cliente envía la captura del comprobante y el equipo verifica el depósito.
