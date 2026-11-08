# Cierre diario de campo por WhatsApp

Botón "Cerrar día" en el menú del bot, que recorre a la gente asignada y termina en un resumen enviado al supervisor y a los superusuarios. Sin cálculo de plata y sin pantalla nueva: todo por WhatsApp.

## Specs

S1. El botón aparece solo si esa persona registró al menos una encuesta hoy en hora Colombia (UTC-5), sea a su nombre o al de otra persona de su gente.
S2. Recorre a la gente asignada al par (supervisor, estudio), una por una. Si no hay nadie asignado, cierra el supervisor a sí mismo.
S3. Censos: "¿Tiene censos el estudio?" Sí/No. Si Sí, opciones "Censo" / "Censo 2-3" / "Censo 4" y después la cantidad; se puede cargar más de un tipo el mismo día.
S4. Transporte: monto libre, solo si no hubo censos.
S5. Incentivo: Sí/No y monto libre, siempre.
S6. Las encuestas no se preguntan: se cuentan del sistema para esa persona y ese día.
S7. Al terminar se guarda y se manda un resumen al supervisor y a los superusuarios. Ejemplo del usuario: "encuestador 1 5 encuestas, 20 censos, 5000 transporte y 5000 incentivo".
S8. Cerrar de nuevo el mismo día reemplaza el cierre (no suma).
S9. La carga a nómina (Parte B) queda fuera de esta entrega.

## Tasks

- T1 — S1/S2: modelo `bot_daily_closings` + `bot_daily_closing_lines` y lectura del día (actividad, roster, encuestas por persona).
- T2 — S3/S4/S5: flujo de preguntas por persona (`backend/day_closing.py`).
- T3 — S6/S7: resumen y envío al supervisor + superusuarios.
- T4 — S8: sobrescritura del cierre del día.
- T5 — Tests `tests/day_closing_test.py` (5 casos) + suite existente sin regresiones.

## Log

L1 (pedido, textual): "ahora quiero que ya cuando alguno tenga por lo menos una encuesta durante el dia en curso con hora colombia aparezca un boton de cerrar dia que pregunte por las personas que tenga asignadas solamente si tienen censos uno a uno si si cuantos, sino que pregunte transporte cada uno sisi cuanto y si tienen incentivos y sisi cuanto"

L2 (respuestas de alcance): misma base de datos para nómina y bot; solo por WhatsApp; censos como opciones "censo", "censo 2-3" y "censo 4"; transporte con monto libre; sin cálculo, resumen final al supervisor y al superusuario.

L3 (censos, textual): "lo de censos serian opciones, uno solo censo y dos censos 2-3 y censo 4"

L4 (evidencia): `bot_closing_rows` del cierre revertido (`81e18f4`) está vacía (0 filas); se usan tablas nuevas para no alterar una tabla existente. Suite: 5 + 5 + 6 + 1 + 4 en verde.

## Evidence

- `tests/day_closing_test.py` → 5 OK.
- Regresión: `tests/interviewer_question_test.py` 5 OK, `tests/agent_interviewers_api_test.py` 6 OK, `tests/export_interviewer_test.py` 1 OK, `test_bot_quota_completeness.py` 4 OK.
- Pendiente manual: probar en el simulador con un supervisor que tenga encuestas del día.
- Las tablas se crean solas en el próximo arranque del servidor.
