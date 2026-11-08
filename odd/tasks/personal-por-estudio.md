# Personal por estudio en el panel de encuestadores

Vincular encuestadores a cada estudio permitido de un supervisor, y mostrarlos en la descarga CSV/Excel.
Alcance autorizado: Parte A (panel + API + descarga). La Parte B (bot WhatsApp) queda fuera, solo se prepara el dato.

## Specs

S1. En el modal "Gestión de Encuestadores" el personal se elige desde la lista de usuarios del sistema, con búsqueda tipeada y scroll. Fuente del dato: `/api/agents` (usuarios con teléfono).
S2. El vínculo es por par (supervisor, estudio permitido): cada estudio tildado tiene su propia lista de encuestadores, independiente de los otros estudios del mismo supervisor.
S3. Caso de referencia del usuario, textual: "Supervisor Pepe tiene activo el estudio xxx con los encuestadores 1 y encuestador 2".
S4. La asignación se guarda con la misma acción de guardado por fila que ya existe hoy ("Guardar Estudios"), que pasa a guardar estudios + personal.
S5. Al tocar el botón de descarga de datos de un estudio ("Descargar Reporte Excel") el archivo debe mostrar el encuestador y el supervisor que cargó la encuesta.
S6. Parte B (no se implementa en esta entrega, solo se deja el dato listo): al final del flujo de WhatsApp deben aparecer, con botones, los encuestadores que el superuser le agregó a ese estudio más el mismo que está cargando la encuesta.
S7. Un agente sin personal asignado no debe notar ningún cambio de comportamiento frente al sistema actual.
S8. Todo local: sin push, sin PR, con commits en rama propia.

## Tasks

- T1 — S1/S2: modelo `BotAgentInterviewer` (agent_phone, study_code, interviewer_name, UNIQUE). Test primero. Commit 1.
- T2 — S1/S2/S4: `GET /api/agents` expone `interviewers_by_study`; `POST /api/agents/interviewers` con guardas (superuser, agente activo, estudio permitido) y semántica de reemplazo; `/api/agents/assign` limpia el personal de los estudios que se destildan. Test primero. Commit 1.
- T3 — S1/S2/S4: front del modal — buscador tipeado de personas, bloque de personal por estudio con chips y typeahead, guardado único por fila. Verificación manual (no hay runner de front). Commit 3.
- T4 — S5: la descarga CSV/Excel agrega "Encuestador" (ya existía, ahora alimentado) y "Supervisor" resuelto desde `users`. Test primero. Commit 2.
- T5 — S7/S8: suite completa, verificación de no-regresión y commits en `feature/personal-por-estudio`.
- T6 — S6: estado `WAITING_INTERVIEWER`; la pregunta ofrece primero al que carga y después el personal del par (agente, estudio). Siempre pregunta, nunca asigna directo. `tests/interviewer_question_test.py`. Sin commit.
- T7 — S6: paginación con "Ver más" cuando hay más de 10 opciones (límite de WhatsApp), y `QuotaSubmission.interviewer_name` con el nombre elegido.
- T8 — S6/S7: la cuota llena se valida ANTES de preguntar el encuestador; la ruta de texto libre también pasa por la pregunta.

## Log

L1 (pedido original, textual): "cuando en este sofwear en el control de encuestadores, se escoje el estudio que puede ver y agregar quiero que se escoja de la lista de encuestadoresel personal (con buscada tipeado y scrol) y que cuando luego se quiera por medio de whapsap la persona queira agregar una encuesta lo ultimo que pida (con botones) esten los encuestadores que el superuser le agrego (y el mismo que este cargando la encuesta) plan a ver si procedemos primer"

L2 (alcance de la Parte A, textual): "vamos a planear por pasos, parte A, en el front: tenemos ya el telefono, Nombre/rol estudio permitidos y si esta activo o no (al terminar guardar) quiero que se vincule con esa persona a ese estudio permitido los encuestadores, ejemplo: Supervisor Pepe tiene activo el estudio xxx con los encuestadores 1 y encuestador 2, para que eso en la parte B que es cuando el supervisor quiera agregar una encuesta y pase todos los pasos que estan al final le aparezca si va a vincular esa encuesta con el encuestador 1, encuestador 2 o con el mismo (todavia en modo planear cero modificaciones)"

L3 (decisión de origen de la lista): el usuario eligió "De la lista de usuarios del sistema" para el typeahead.

L4 (autorización de implementación, textual): "ok me gusta el plan, quiero que tambien esto se vea cuando el usuario decida tocar el boton de descargas en excel, procede en local y commit"

L5 (baseline): `python test_bot_quota_completeness.py` pasa; `python test_validation.py` ya fallaba antes de esta feature (tabla `users` en memoria sin `full_name`, porque `models.User` no declara esa columna). No se toca.

## Evidence

- Commits en `feature/personal-por-estudio`: `feb9102` (T1/T2), `e8a32dc` (T4), `c31505f` (T3).
- `python tests/agent_interviewers_api_test.py` → 6 OK.
- `python tests/export_interviewer_test.py` → 1 OK.
- `python test_bot_quota_completeness.py` → 4 OK (sin cambios respecto del baseline).
- `node --check frontend/quotas.js` → OK.
- Smoke ASGI (sin tocar la DB real): `GET /` 200 con `#agentsSearch`, `GET /static/quotas.js` 200 con `saveAgentSettings`.
- Pendiente de verificación manual: abrir el modal en el navegador y probar el typeahead y el guardado real.
- La tabla `bot_agent_interviewers` se crea sola en el próximo arranque del servidor (`Base.metadata.create_all`).
- Preexistente, no de esta feature: `python test_validation.py` falla porque `models.User` no declara `full_name`.

L6 (decisión Parte B, textual): "ahora parte b entonces sin commit, lo de asignar directo no porque no sabemos si es de cual encuestador, procde y me dices al terminar como termino de ir"

L7 (estilo): el usuario pidió no usar español rioplatense. Respuestas en español neutro.

L8 (verificación Parte B): RED probado revirtiendo `backend/main.py` (sin el cambio el bot guardaba directo: "No preguntó: ✅ ¡Guardado con éxito!"). Suite: 6 + 1 + 5 + 4 en verde. `test_validation.py` sigue roto por causa preexistente.

L9 (pendiente): la revisión nativa quedó en `reviewing` para el candidato `sha256:3b44c59f…` (solo los 4 commits anteriores); el host no tiene modelo configurado para las lentes. La Parte B está sin commitear y por lo tanto fuera de ese candidato.
