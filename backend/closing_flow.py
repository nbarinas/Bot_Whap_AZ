"""
Flujo de cierre diario por WhatsApp.

Vive aparte de `main.py` a proposito: el bot ya tiene un arbol de estados
grande y este es otro, con sus propias preguntas.

El reparto no lo pide nadie: en cuanto la persona escribe y se abre su sesion,
si ya registro cuotas hoy, arranca esto solo. No hay palabra clave ni boton.

    (la persona escribe cualquier cosa)
      -> se le muestra lo que tiene que cuadrar
      -> estudio por estudio: cuantas personas, y de cada una nombre,
         encuestas y censos
      -> a cada persona se le pregunta la plata (incentivos, transporte y
         gasto), pero una sola vez por persona y dia: si ya trabajo en otro
         estudio, no se le vuelve a preguntar
      -> se guarda todo de una vez y se le dice si le cuadro

No hay "¿quieres guardar?": se guarda cuando termino de nombrar a toda la
gente que dijo. Guardar a medias dejaria al supervisor en verde con el reparto
aun incompleto.

Si las cuentas no dan, se le dice exactamente que estudio no cuadra y con
*corregir* vuelve a empezar. Al reabrir un estudio se borra lo que habia
reportado de ese estudio hoy, para que lo viejo no se mezcle con lo nuevo.
"""

from . import closing, name_search

# Tres intentos y se cae la sesion: igual que el resto del bot.
MAX_INTENTOS = 3

# Se queda dentro del cierre para rehacer las cuentas sin esperar a que expire
# la sesion. No hace falta una palabra para empezar: eso lo dispara `main`.
COMANDO_CORREGIR = "corregir"


# --- lectura de lo que escribe la gente ----------------------------------

def _entero(valor, minimo=0):
    """True si el texto es un entero >= minimo. '03' y ' 7 ' cuentan."""
    try:
        return int(str(valor).strip()) >= minimo
    except (TypeError, ValueError):
        return False


def _es_no(valor):
    """'no', 'n', '0', 'na'... todo lo que significa que no."""
    return str(valor).strip().lower() in ("no", "n", "0", "na", "nel", "ninguno")


def _dinero(valor):
    """Lee '25000', '$25.000' o '25 mil' como 25000. None si no se entiende."""
    texto = str(valor).strip().lower().replace("$", "").replace(".", "")
    if texto.endswith("mil"):
        texto = texto[:-3].strip()
        return int(texto) * 1000 if texto.isdigit() else None
    return int(texto) if texto.isdigit() else None


# --- datos del supervisor ------------------------------------------------

def pendientes_del_supervisor(db, phone, fecha):
    """
    Lo que le falta a este numero hoy.

    Devuelve el registro de `get_pending_supervisors`, o None si ese numero no
    registro nada ese dia o es observador (los observadores miran el reporte,
    no lo llenan).
    """
    from .main import es_observador

    if es_observador(phone):
        return None

    mio = closing.normalizar_telefono(phone)
    for e in closing.get_pending_supervisors(db, fecha):
        if e["phone"] == mio:
            return e
    return None


def estudios_pendientes(db, phone, fecha):
    """Los estudios de hoy que todavia no cuadran, con lo que falta en cada uno."""
    pendiente = pendientes_del_supervisor(db, phone, fecha)
    if pendiente is None:
        return None, {}

    mio = closing.normalizar_telefono(phone)
    declarado = closing._declarado_por_supervisor(db, fecha).get(mio) or {}

    faltan = {}
    for estudio, reg in pendiente["studies"].items():
        if declarado.get(estudio, 0) != reg["surveys"]:
            faltan[estudio] = reg
    return pendiente, faltan


# --- textos --------------------------------------------------------------

def _resumen(pendiente, faltan, fecha):
    """Lo que hay que cuadrar hoy, agrupado por estudio."""
    lineas = []
    for estudio, reg in sorted(faltan.items()):
        lineas.append("• {}: {} encuesta(s)".format(estudio, reg["surveys"]))
    return (
        "📋 *CIERRE DEL {}*\n\n"
        "Tus estudios de hoy:\n{}\n\n"
        "Total del día: {} encuesta(s).\n\n"
        "¿En qué estudio quieres empezar? Escribe el número.".format(
            fecha, "\n".join(lineas), pendiente["surveys"]
        )
    )


def _opciones(estudios):
    return "\n".join(
        "{}. {}".format(i, e) for i, e in enumerate(sorted(estudios), start=1)
    )


def _ayuda(campo):
    """El texto de ayuda de cada paso, para no repetir la pregunta a mano."""
    return {
        "estudio": "Escribe el número del estudio.",
        "personas": "Responde solo con el número de personas, por ejemplo *3*.",
        "encuestas": "Escribe el número de encuestas, por ejemplo *12*.",
        "censos": "Escribe el número de censos. Si no hizo ninguno, escribe *0*.",
        "incentivo_agente": "Responde *sí* o *no*.",
        "monto_agente": "Escribe el monto en pesos, por ejemplo *25000*.",
        "incentivo_supervisor": "Responde *sí* o *no*.",
        "monto_supervisor": "Escribe el monto en pesos, por ejemplo *50000*.",
        "gasto": "Escribe *no* si no hubo gasto extra.",
        "transporte": (
            "Escribe los transportes separados por un espacio: primero los "
            "completos y despues los medios. Por ejemplo *2 1*."
        ),
    }.get(campo, "Responde con un número, por ejemplo *5*.")


# --- la maquina de estados ------------------------------------------------

def iniciar(db, db_users, phone, fecha):
    """
    Arranca el cierre.

    Returns:
        (texto, estado, ctx). `(None, None, ...)` cuando ya no hay nada que
        cerrar.
    """
    pendiente, faltan = estudios_pendientes(db, phone, fecha)
    if pendiente is None:
        return (
            "No tienes registros de hoy, así que no hay nada que cerrar. 👍",
            None, {},
        )
    if not faltan:
        return _ya_cerrado(pendiente), None, {}

    ctx = {
        "cierre_fecha": fecha,
        "estudios_abiertos": sorted(faltan),
        "conteos": {e: r["surveys"] for e, r in faltan.items()},
        "censos_sistema": {e: r.get("census", 0) for e, r in faltan.items()},
        "personas": [],
        "con_plata": [],
        "indice": 0,
        "estudio": None,
        "campo": None,
        "intentos": 0,
    }

    if len(faltan) == 1:
        # Un solo estudio: no hay nada que preguntar.
        estudio = list(faltan)[0]
        return _abrir_estudio(
            db, db_users, phone, fecha, estudio, faltan[estudio]["surveys"], ctx
        )

    return _resumen(pendiente, faltan, fecha), "CIERRE_ESTUDIO", ctx


def _ya_cerrado(pendiente):
    return (
        "✅ Tu cierre de hoy ya está guardado y las cuentas dan.\n"
        "Gracias por reportar."
    )


def _abrir_estudio(db, db_users, phone, fecha, estudio, encuestas, ctx):
    """
    Abre un estudio para reportarlo, borrando lo que hubiera de el hoy.

    El borrado es lo que hace que *corregir* sirva: si el supervisor se
    equivocaba en la gente o en las cuentas, lo anterior se mezcla con lo nuevo
    y las cifras ya no dan. Al abrir el estudio se empieza de cero.
    """
    supervisor_id = _supervisor_id(db_users, phone)
    if supervisor_id:
        closing.borrar_filas_del_estudio(db, fecha, estudio, supervisor_id)
    return _preguntar_personas(estudio, encuestas, ctx)


def _preguntar_personas(estudio, encuestas, ctx):
    """Arranca el estudio: cuanta gente hay que repartir."""
    ctx = _con(ctx, estudio=estudio, campo="personas", intentos=0)
    return (
        "📌 *{}*\n\nTienes {} encuesta(s) que reportar de este estudio.\n\n"
        "¿Cuántas personas trabajaron? Responde solo el número."
        .format(estudio, encuestas),
        "CIERRE_PERSONAS",
        ctx,
    )


def _con(ctx, **cambios):
    """Copia del contexto con campos cambiados."""
    nuevo = dict(ctx)
    nuevo.update(cambios)
    return nuevo


def _con_marca_plata(ctx):
    """
    Anota que a esta persona ya se le pregunto la plata en este cierre.

    Sin esta lista, si el mismo id aparece dos veces en el mismo estudio se le
    volveria a preguntar y la plata quedaria duplicada.
    """
    persona = _persona(ctx)
    ids = list(ctx.get("con_plata", []))
    interviewer_id = persona.get("interviewer_id")
    if interviewer_id and interviewer_id not in ids:
        ids.append(interviewer_id)
    return _con(ctx, con_plata=ids)


def _supervisor_id(db_users, phone):
    """El `users.id` de quien cierra, o None si no esta en la lista."""
    encontrado = name_search.buscar_por_telefono(db_users, phone)
    return encontrado["id"] if encontrado else None


def _persona(ctx):
    """La persona que se esta llenando."""
    return ctx["personas"][ctx["indice"]]


def _poner(ctx, campo, valor):
    """Escribe un campo de la persona en curso."""
    personas = [dict(p) for p in ctx["personas"]]
    personas[ctx["indice"]][campo] = valor
    return _con(ctx, personas=personas)


def paso(db, db_users, phone, estado, ctx, msg):
    """
    Avanza un paso del cierre.

    Returns:
        (texto, nuevo_estado, ctx). `nuevo_estado` en None cierra la sesion.
    """
    fecha = ctx.get("cierre_fecha") or closing.colombia_hoy()
    texto = str(msg).strip()
    campo = ctx.get("campo")

    def error(que_falta):
        intentos = ctx.get("intentos", 0) + 1
        if intentos >= MAX_INTENTOS:
            return (
                "🚫 Seguimos sin entender la respuesta. Empecemos de nuevo.\n"
                "Escribe *corregir* cuando quieras.",
                None, {},
            )
        return (
            "⚠️ {}\n\n{}".format(que_falta, _ayuda(campo)),
            estado,
            _con(ctx, intentos=intentos),
        )

    # --- elegir estudio ---
    if estado == "CIERRE_ESTUDIO":
        estudios = ctx.get("estudios_abiertos", [])
        if not _entero(texto, 1) or int(texto) > len(estudios):
            return error("Ese número no está en la lista.")
        elegido = estudios[int(texto) - 1]
        return _abrir_estudio(
            db, db_users, phone, fecha, elegido, ctx["conteos"].get(elegido, 0), ctx
        )

    # --- cuantas personas ---
    if estado == "CIERRE_PERSONAS":
        if not _entero(texto, 1) or int(texto) > 50:
            return error("No entendí cuántas personas fueron.")
        return (
            "¿Quién fue la primera persona?\n\n"
            "El nombre se puede escribir como quieras, también al revés "
            "(por ejemplo *cardenas juli*).",
            "CIERRE_NOMBRE",
            _con(ctx, personas=[{} for _ in range(int(texto))], indice=0,
                 campo="nombre", intentos=0),
        )

    # --- nombre de la persona ---
    if estado == "CIERRE_NOMBRE":
        return _elegir_nombre(db_users, texto, ctx, estado, error)

    if estado == "CIERRE_NOMBRE_ESCOGE":
        sugerencias = ctx.get("sugerencias", [])
        if not _entero(texto, 1) or int(texto) > len(sugerencias):
            return error("Ese número no está en la lista.")
        elegido = sugerencias[int(texto) - 1]
        ctx = _con(ctx, intentos=0)
        ctx.pop("sugerencias", None)
        return _preguntar_cifras(ctx, elegido)

    # --- cifras ---
    if estado == "CIERRE_ENCUESTAS":
        if not _entero(texto):
            return error("No entendí el número de encuestas.")
        return (
            "¿Y cuántos censos hizo? Escribe *0* si no hizo ninguno.",
            "CIERRE_CENSOS",
            _poner(_con(ctx, campo="censos", intentos=0), "surveys_declared",
                   int(texto)),
        )

    if estado == "CIERRE_CENSOS":
        if not _entero(texto):
            return error("No entendí el número de censos.")
        ctx = _poner(_con(ctx, intentos=0), "census_declared", int(texto))
        return _despues_de_cifras(db, db_users, phone, fecha, ctx)

    # --- dinero: una vez por persona y dia ---
    # Una persona puede trabajar en varios estudios, y la plata se cuenta una
    # sola vez. Quien ya tiene fila con plata de hoy no se le vuelve a preguntar.
    if estado == "CIERRE_INCENTIVO_AGENTE":
        hubo = not _es_no(texto)
        ctx = _poner(_con(ctx, intentos=0), "incentive_agent", 1 if hubo else 0)
        if not hubo:
            ctx = _poner(ctx, "incentive_agent_amount", 0)
            return _preguntar_incentivo_supervisor(ctx)
        return (
            "¿De cuánto fue el incentivo para ella? (en pesos)",
            "CIERRE_MONTO_AGENTE",
            _con(ctx, campo="monto_agente"),
        )

    if estado == "CIERRE_MONTO_AGENTE":
        plata = _dinero(texto)
        if plata is None:
            return error("No entendí el monto.")
        ctx = _poner(ctx, "incentive_agent_amount", plata)
        return _preguntar_incentivo_supervisor(ctx)

    if estado == "CIERRE_INCENTIVO_SUPERVISOR":
        hubo = not _es_no(texto)
        ctx = _poner(_con(ctx, intentos=0), "incentive_supervisor", 1 if hubo else 0)
        if not hubo:
            ctx = _poner(ctx, "incentive_supervisor_amount", 0)
            return _preguntar_transporte(ctx)
        return (
            "¿De cuánto fue el incentivo para el supervisor? (en pesos)",
            "CIERRE_MONTO_SUPERVISOR",
            _con(ctx, campo="monto_supervisor"),
        )

    if estado == "CIERRE_MONTO_SUPERVISOR":
        plata = _dinero(texto)
        if plata is None:
            return error("No entendí el monto.")
        ctx = _poner(ctx, "incentive_supervisor_amount", plata)
        return _preguntar_transporte(ctx)

    if estado == "CIERRE_TRANSPORTE":
        partes = texto.split()
        if len(partes) != 2 or not _entero(partes[0]) or not _entero(partes[1]):
            return error("No entendí los transportes.")
        ctx = _poner(_con(ctx, intentos=0), "transport_full", int(partes[0]))
        ctx = _poner(ctx, "transport_partial", int(partes[1]))
        return (
            "¿Hubo algún gasto extra ese día? Escribe *no* si no hubo.",
            "CIERRE_GASTO",
            _con(ctx, campo="gasto"),
        )

    if estado == "CIERRE_GASTO":
        if _es_no(texto):
            ctx = _poner(_con(ctx, intentos=0), "extra_expense_amount", 0)
            ctx = _con_marca_plata(ctx)
            return _despues_de_cifras(db, db_users, phone, fecha, ctx)
        return (
            "Describe el gasto en pocas palabras.",
            "CIERRE_GASTO_DETALLE",
            _con(ctx, campo="gasto_detalle"),
        )

    if estado == "CIERRE_GASTO_DETALLE":
        ctx = _poner(_con(ctx, intentos=0), "extra_expense_desc", texto[:150])
        return (
            "¿De cuánto fue el gasto? (en pesos)",
            "CIERRE_GASTO_MONTO",
            _con(ctx, campo="gasto_monto"),
        )

    if estado == "CIERRE_GASTO_MONTO":
        plata = _dinero(texto)
        if plata is None:
            return error("No entendí el monto.")
        ctx = _poner(ctx, "extra_expense_amount", plata)
        ctx = _con_marca_plata(ctx)
        return _despues_de_cifras(db, db_users, phone, fecha, ctx)

    return (
        "📋 Cuando quieras reportar el dia, escribeme y arrancamos.",
        None, {},
    )


def _elegir_nombre(db_users, texto, ctx, estado, error):
    """Busca la persona y resuelve el caso ambiguo con una lista numerada."""
    encontrado = name_search.buscar_personas(db_users, texto, limite=5)

    if not encontrado["encontrado"]:
        intentos = ctx.get("intentos", 0) + 1
        if intentos >= MAX_INTENTOS:
            return (
                "🚫 No encontré a nadie con eso.\n\n"
                "Escribe *corregir* para empezar de nuevo.",
                None, {},
            )
        return (
            "🔎 No encontré a nadie con *{}*.\n\n"
            "Prueba con otra forma del nombre, por ejemplo *juli cardenas*.".format(
                texto[:60]
            ),
            estado,
            _con(ctx, intentos=intentos),
        )

    if encontrado["ambiguo"]:
        lista = "\n".join(
            "{}. {} ({}%)".format(i, s["nombre"], int(s["score"] * 100))
            for i, s in enumerate(encontrado["sugerencias"], start=1)
        )
        return (
            "🤔 Hay varias personas parecidas:\n\n{}\n\n"
            "Escribe el número de la correcta.".format(lista),
            "CIERRE_NOMBRE_ESCOGE",
            _con(ctx, sugerencias=encontrado["sugerencias"], intentos=0),
        )

    elegido = encontrado["sugerencias"][0]
    return _preguntar_cifras(_con(ctx, intentos=0), elegido)


def _preguntar_cifras(ctx, elegido):
    """Confirma a quien se le esta preguntando y pide las encuestas."""
    ctx = _poner(ctx, "interviewer_id", elegido["id"])
    ctx = _poner(ctx, "interviewer", elegido["nombre"])
    return (
        "👤 *{}*\n\n¿Cuántas encuestas hizo hoy?".format(elegido["nombre"]),
        "CIERRE_ENCUESTAS",
        _con(ctx, campo="encuestas"),
    )


def _preguntar_incentivo_supervisor(ctx):
    return (
        "¿Se le pagaron incentivos al supervisor hoy? (sí/no)",
        "CIERRE_INCENTIVO_SUPERVISOR",
        _con(ctx, campo="incentivo_supervisor"),
    )


def _preguntar_transporte(ctx):
    return (
        "Transportes de esa persona: primero los completos, después los medios.\n"
        "Por ejemplo *2 1*. (Si no tuvo, escribe *0 0*.)",
        "CIERRE_TRANSPORTE",
        _con(ctx, campo="transporte"),
    )


def _despues_de_cifras(db, db_users, phone, fecha, ctx):
    """
    O pregunta el dinero, o sigue con la siguiente persona, o guarda.

    Guardar aca y no despues es lo que evita el cierre a medias: hasta que
    termine de nombrar a su gente no queda nada escrito, asi que en el panel
    sigue en rojo.

    La plata se pregunta por persona y dia. Al reportar el segundo estudio, la
    persona del primero ya tiene fila guardada, asi que no se le pregunta de
    nuevo: se le reconoce por `interviewer_id`, no por su posicion en la lista.
    """
    persona = _persona(ctx)
    if not _tiene_plata(db, db_users, phone, fecha, persona, ctx):
        return _preguntar_incentivo_agente(ctx)

    siguiente = ctx["indice"] + 1
    if siguiente < len(ctx["personas"]):
        return (
            "👥 ¿Quién fue la persona número {}?".format(siguiente + 1),
            "CIERRE_NOMBRE",
            _con(ctx, indice=siguiente, campo="nombre", intentos=0),
        )
    return _guardar_estudio(db, db_users, phone, fecha, ctx)


def _tiene_plata(db, db_users, phone, fecha, persona, ctx):
    """
    False si toca preguntarle la plata a esta persona ahora.

    True si ya se le pregunto en este cierre, o si ya tiene plata guardada de
    hoy (porque Trabajó en otro estudio antes de este).
    """
    interviewer_id = persona.get("interviewer_id")
    if not interviewer_id:
        return True

    if interviewer_id in ctx.get("con_plata", []):
        return True

    supervisor_id = _supervisor_id(db_users, phone)
    if supervisor_id is None:
        return True

    if closing.plata_ya_registrada(
        db, fecha, supervisor_id, interviewer_id
    ):
        return True

    # Se marca ya para que la segunda persona con el mismo id no se skipee:
    # el contexto no distingue ids repetidos todavia.
    return False


def _preguntar_incentivo_agente(ctx):
    return (
        "💰 A la plata se le pregunta una sola vez por persona y día, así que "
        "te la pregunto ahora.\n\n"
        "¿Se le pagaron incentivos a ella hoy? (sí/no)",
        "CIERRE_INCENTIVO_AGENTE",
        _con(ctx, campo="incentivo_agente"),
    )


def _guardar_estudio(db, db_users, phone, fecha, ctx):
    """Escribe las filas del estudio que acaba de cerrar y ofrece el siguiente."""
    supervisor = _supervisor_id(db_users, phone)
    if not supervisor:
        return (
            "⚠️ Tu número no está en la lista de personal, así que no puedo "
            "guardar el cierre.\n\nAvisa al equipo para que te agreguen.",
            None, {},
        )
    supervisor_id = supervisor

    estudio = ctx["estudio"]
    for persona in ctx["personas"]:
        if not persona.get("interviewer_id"):
            continue
        closing.upsert_closing_row(
            db, fecha, estudio, supervisor_id, persona["interviewer_id"],
            filled_by=phone,
            surveys_declared=persona.get("surveys_declared", 0),
            census_declared=persona.get("census_declared", 0),
            system_surveys=ctx["conteos"].get(estudio, 0),
            system_census=ctx.get("censos_sistema", {}).get(estudio, 0),
            incentive_agent=persona.get("incentive_agent", 0),
            incentive_agent_amount=persona.get("incentive_agent_amount"),
            incentive_supervisor=persona.get("incentive_supervisor", 0),
            incentive_supervisor_amount=persona.get("incentive_supervisor_amount"),
            transport_full=persona.get("transport_full", 0),
            transport_partial=persona.get("transport_partial", 0),
            extra_expense_desc=persona.get("extra_expense_desc"),
            extra_expense_amount=persona.get("extra_expense_amount"),
        )
        # La plata vive en la primera fila del dia de esa persona.
        closing.marcar_propietario_del_gasto(
            db, fecha, supervisor_id, persona["interviewer_id"]
        )

    abiertos = [e for e in ctx.get("estudios_abiertos", []) if e != estudio]
    resumen = "{}Personas: {} ({} encuestas, {} censos).".format(
        "• " + estudio + "\n",
        ", ".join(p.get("interviewer", "?") for p in ctx["personas"]),
        sum(p.get("surveys_declared", 0) for p in ctx["personas"]),
        sum(p.get("census_declared", 0) for p in ctx["personas"]),
    )

    if not abiertos:
        return _texto_final(db, fecha, phone), None, {}

    return (
        "✅ Guardé *{}*.\n\n{}\n\nQueda(n) {} estudio(s):\n{}\n\n"
        "¿Cuál sigues?".format(
            estudio, resumen, len(abiertos), _opciones(abiertos)
        ),
        "CIERRE_ESTUDIO",
        _con(ctx, estudios_abiertos=abiertos, personas=[], indice=0,
             campo=None, intentos=0),
    )


def _texto_final(db, fecha, phone):
    """Dice si le cuadró y, si no, cuánto le sobra o le falta en cada estudio."""
    pendiente, faltan = estudios_pendientes(db, phone, fecha)

    if pendiente is None:
        return "✅ Guardé tu cierre."

    if not faltan:
        return (
            "🎉 ¡Listo! Cerraste todos tus estudios y las cuentas dan.\n\n"
            "Gracias por reportar."
        )

    mio = closing.normalizar_telefono(phone)
    declarado = closing._declarado_por_supervisor(db, fecha).get(mio) or {}

    detalle = []
    for estudio, reg in sorted(faltan.items()):
        diferencia = reg["surveys"] - declarado.get(estudio, 0)
        if diferencia > 0:
            detalle.append("• {}: te faltan {} encuesta(s)".format(estudio, diferencia))
        else:
            detalle.append("• {}: te sobran {} encuesta(s)".format(estudio, -diferencia))

    return (
        "⚠️ Guardé lo que me dijiste, pero todavía no cuadra:\n\n{}\n\n"
        "Escríbeme *corregir* y lo ajustamos.".format("\n".join(detalle))
    )
