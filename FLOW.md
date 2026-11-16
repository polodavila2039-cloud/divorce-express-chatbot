# Flujo del chatbot (v8)

El guion completo vive en `webhook.py`, una etapa por bloque `@etapa(...)`.

Bienvenida y nombre → menú (3 botones; "otro" abre la lista de los demás servicios)
- 1 Divorcio Express: acuerdo → hijos → bienes → ciudad → cuándo iniciar → cierre
- 2 Divorcio Incausado: acuerdo → domicilio → localización → trabajo → pensión → violencia → formulario → cierre
- 3 Pensión alimenticia: hijos → trabajo → aporta → ciudad → cierre
- 4, 6, 7 Urgentes: pase inmediato a un abogado y línea directa
- 5, 8, 9 Asesoría: tipo (presencial o llamada) → día y hora → pase al equipo

Cierre: contado / iniciar con pago inicial / ahora no
- Financiamiento: 2 pagos sin aumento, o pagos por semana (lista de montos)
- Primera negativa: ¿qué te detiene? (precio, pensarlo, dudas)
- Segunda negativa: oferta de $900 con vigencia de 24 h (Express y Pensión)
- Al aceptar: nombre completo, nombre de la pareja, medio de pago → pase al equipo
