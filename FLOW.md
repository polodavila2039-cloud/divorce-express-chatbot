# Flujos del chatbot — Divorcio Express Saltillo
# Textos en español, listos para que Polo los apruebe o ajuste.
# Los precios y los nombres exactos de los productos se llenan
# con el catálogo; donde dice [PENDIENTE] falta ese dato.

## 1. Saludo inicial (cuando alguien escribe por primera vez o escribe "hola")

> ¡Hola! 👋 Soy el asistente de Divorcio Express Saltillo.
> Te ayudamos a terminar tu matrimonio de forma rápida, económica y sin juicio ni conflicto.
>
> ¿Qué te gustaría saber?
> [1] Ver servicios y precios
> [2] ¿Cuánto tarda el divorcio?
> [3] Financiamiento
> [4] Agendar una cita / hablar con un asesor

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

## 8. Mensaje fuera de horario / no entendido

> Gracias por tu mensaje. Nuestro equipo te atiende en horario de atención.
> Mientras tanto, puedes ver nuestros servicios escribiendo "catálogo", o preguntar por precio, tiempo o financiamiento.
