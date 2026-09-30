"""
Logica de datos del cierre diario de campo.

El supervisor registra todas las encuestas desde su propio celular, asi que el
sistema solo puede medir el TOTAL por supervisor, estudio y dia. El desglose
por persona lo declara el supervisor en el formulario; lo unico automatico
es verificar que la suma de ese desglose cuadre con el total real.

Los nombres se resuelven contra la base de usuarios (`users`) por id, nunca
se copian a la tabla de cierre.
"""

from datetime import datetime, timedelta

from sqlalchemy import func

from . import models

# Colombia es UTC-5 todo el ano (no tiene horario de verano).
UTC_OFFSET_HORAS = 5
FECHA_FORMATO = "%Y-%m-%d"


def normalizar_telefono(phone):
    """
    Telefono en formato Meta (573 + 10 digitos), sin importarse de main.

    Vive aqui tambien porque `closing` se usa en pruebas sin levantar la app.
    """
    digitos = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digitos) == 10:
        return "57" + digitos
    return digitos


def colombia_hoy(utc_now=None):
    """
    Fecha local de Colombia (UTC-5) del momento dado, como texto YYYY-MM-DD.

    Se devuelve texto porque `close_date` es una columna de texto.
    """
    if utc_now is None:
        utc_now = datetime.utcnow()
    return (utc_now - timedelta(hours=UTC_OFFSET_HORAS)).strftime(FECHA_FORMATO)


def colombia_day_bounds(fecha):
    """
    Devuelve (inicio, fin) en UTC naive para un dia local de Colombia.

    `fecha` es un string YYYY-MM-DD en hora Colombia. Comparar timestamps en
    UTC contra un corte en hora local correria el dia 5 horas, justo en la
    franja en la que se hace el cierre.
    """
    dia = datetime.strptime(fecha, FECHA_FORMATO).date()
    inicio_utc = datetime(dia.year, dia.month, dia.day) + timedelta(hours=UTC_OFFSET_HORAS)
    return inicio_utc, inicio_utc + timedelta(days=1)


def get_day_totals_by_supervisor(db, fecha):
    """
    Total real por telefono, estudio y dia.

    'surveys' y 'census' son disjuntos: un censo NO cuenta como encuesta.
    Los censos viven en cuotas cuyo `value` arranca con 'Censos'.

    Returns:
        [{"phone": "573...", "study_code": "1465...", "surveys": 23, "census": 4}, ...]
    """
    inicio, fin = colombia_day_bounds(fecha)

    registros = (
        db.query(
            models.QuotaSubmission.phone_number.label("phone"),
            models.BotQuota.study_code.label("study_code"),
            func.lower(models.BotQuota.value).label("quota_value"),
        )
        .join(models.BotQuota, models.BotQuota.id == models.QuotaSubmission.bot_quota_id)
        .filter(
            models.QuotaSubmission.is_deleted == 0,
            models.QuotaSubmission.submitted_at >= inicio,
            models.QuotaSubmission.submitted_at < fin,
        )
        .all()
    )

    totales = {}
    for reg in registros:
        if not reg.phone or not reg.study_code:
            continue
        clave = (reg.phone, reg.study_code)
        if clave not in totales:
            totales[clave] = {"surveys": 0, "census": 0}
        if (reg.quota_value or "").strip().startswith("censos"):
            totales[clave]["census"] += 1
        else:
            totales[clave]["surveys"] += 1

    resultado = [
        {"phone": ph, "study_code": st, "surveys": c["surveys"], "census": c["census"]}
        for (ph, st), c in totales.items()
    ]
    resultado.sort(key=lambda r: (r["phone"], r["study_code"]))
    return resultado


def get_supervisor_day_studies(db, fecha, phone):
    """
    Estudios que trabajo un telefono en un dia, con su total real.

    Returns:
        {"1465 seguimiendo sh": {"surveys": 23, "census": 4}, ...}
    """
    estudios = {}
    telefono = normalizar_telefono(phone)
    for t in get_day_totals_by_supervisor(db, fecha):
        if normalizar_telefono(t["phone"]) == telefono:
            estudios[t["study_code"]] = {"surveys": t["surveys"], "census": t["census"]}
    return estudios


def _declarado_por_supervisor(db, fecha):
    """
    Lo que cada supervisor declaro, agrupado por telefono y estudio.

    Solo cuentan las filas que el supervisor guardo desde WhatsApp: una
    correccion hecha desde el panel (`filled_by` vacio) no lo pone en verde,
    porque es el superusuario hablando por el.
    """
    declarado = {}
    for f in db.query(models.BotClosingRow).filter(
        models.BotClosingRow.close_date == fecha
    ).all():
        phone = normalizar_telefono(f.filled_by) if f.filled_by else ""
        if not phone:
            continue
        grupo = declarado.setdefault(phone, {})
        grupo[f.study_code] = grupo.get(f.study_code, 0) + (f.surveys_declared or 0)
    return declarado


def _cerraron(estudios_del_sistema, declarado):
    """
    True si lo declarado cuadra estudio por estudio con lo que hay en el sistema.

    No basta con 'tiene alguna fila': el supervisor responde persona por
    persona y, a medio camino, el panel ya lo mostraria en verde aunque todavia
    le falte gente. Cerrar es que las cuentas den.
    """
    if not declarado:
        return False
    for estudio, total in estudios_del_sistema.items():
        if declarado.get(estudio, 0) != total:
            return False
    # Un estudio que el sistema nunca vio tampoco puede quedar "cerrado".
    return all(estudio in estudios_del_sistema for estudio in declarado)


def get_pending_supervisors(db, fecha):
    """
    Numeros que registraron algo ese dia y si enviaron su cierre.

    Los observadores quedan fuera: miran el reporte pero no lo llenan.
    'enviado' sale True cuando lo que declaro el supervisor cuadra con el total
    real de cada uno de sus estudios. No hay boton de "terminar", pero tampoco
    se marca en verde a la primera persona que responde.

    Returns:
        [{"phone": "573...", "studies": {...}, "surveys": int,
          "census": int, "enviado": bool, "en_proceso": bool}, ...]
    """
    from .main import es_observador

    por_telefono = {}
    for reg in get_day_totals_by_supervisor(db, fecha):
        if es_observador(reg["phone"]):
            continue
        phone = normalizar_telefono(reg["phone"])
        entry = por_telefono.setdefault(
            phone, {"studies": {}, "surveys": 0, "census": 0}
        )
        entry["studies"][reg["study_code"]] = {
            "surveys": reg["surveys"],
            "census": reg["census"],
        }
        entry["surveys"] += reg["surveys"]
        entry["census"] += reg["census"]

    declarado = _declarado_por_supervisor(db, fecha)

    salida = []
    for ph, datos in por_telefono.items():
        mando = declarado.get(ph) or {}
        # Solo las encuestas deciden el verde; el censo es informativo.
        totales = {est: reg["surveys"] for est, reg in datos["studies"].items()}
        enviado = _cerraron(totales, mando)
        salida.append({
            "phone": ph,
            "enviado": enviado,
            "en_proceso": bool(mando) and not enviado,
            **datos,
        })
    return sorted(salida, key=lambda p: p["phone"])


def upsert_closing_row(db, close_date, study_code, supervisor_id,
                       interviewer_id, filled_by=None, **campos):
    """
    Guarda o actualiza la fila de cierre de una persona en un estudio.

    Reintentar el mismo cierre no duplica: siempre actualiza la misma fila.
    Los nombres no se guardan; solo los `users.id`.
    """
    fila = (
        db.query(models.BotClosingRow)
        .filter(
            models.BotClosingRow.close_date == close_date,
            models.BotClosingRow.study_code == study_code,
            models.BotClosingRow.supervisor_id == supervisor_id,
            models.BotClosingRow.interviewer_id == interviewer_id,
        )
        .first()
    )
    if not fila:
        fila = models.BotClosingRow(
            close_date=close_date,
            study_code=study_code,
            supervisor_id=supervisor_id,
            interviewer_id=interviewer_id,
        )
        db.add(fila)

    for campo, valor in campos.items():
        setattr(fila, campo, valor)

    fila.filled_by = normalizar_telefono(filled_by) or None
    fila.filled_at = datetime.utcnow()
    db.commit()
    db.refresh(fila)
    return fila


def telefonos_de_supervisores(db_users):
    """
    {users.id: telefono en formato Meta} para toda la base de usuarios.

    El sistema mide por telefono y el cierre guarda `users.id`; esta tabla es
    el puente para comparar a cada supervisor con lo suyo.
    """
    from sqlalchemy import text

    try:
        filas = db_users.execute(
            text("SELECT id, phone_number FROM users WHERE phone_number IS NOT NULL")
        ).fetchall()
    except Exception:
        return {}
    return {
        f.id: normalizar_telefono(f.phone_number)
        for f in filas
        if f.phone_number
    }


def _nombre_de_usuario(db_users, user_id):
    """Nombre desde la base de usuarios; '' si el id ya no existe."""
    if not user_id:
        return ""
    try:
        reg = (
            db_users.query(models.User.id, models.User.full_name)
            .filter(models.User.id == user_id)
            .first()
        )
    except Exception:
        return ""
    if reg and reg.full_name:
        return reg.full_name.strip()
    return ""


def get_closing_rows(db, db_users, fecha, study_code=None):
    """
    Filas del cierre de un dia, ya con los nombres resueltos desde `users`.

    Los ids mandan: si manana se corrige un nombre en la base de usuarios,
    el reporte viejo sale con el nombre correcto.
    """
    consulta = db.query(models.BotClosingRow).filter(
        models.BotClosingRow.close_date == fecha
    )
    if study_code:
        consulta = consulta.filter(models.BotClosingRow.study_code == study_code)
    # Se ordena en memoria porque el nombre vive en la base de usuarios, no aqui.
    # Ademas el nombre es texto libre y "A" < "a": se compara sin distinguir.
    filas = consulta.all()

    resultado = []
    for f in filas:
        resultado.append({
            "id": f.id,
            "study_code": f.study_code or "",
            "close_date": f.close_date or fecha,
            "supervisor": _nombre_de_usuario(db_users, f.supervisor_id),
            "interviewer": _nombre_de_usuario(db_users, f.interviewer_id),
            "supervisor_id": f.supervisor_id,
            "interviewer_id": f.interviewer_id,
            "surveys_declared": f.surveys_declared or 0,
            "census_declared": f.census_declared or 0,
            "system_surveys": f.system_surveys or 0,
            "system_census": f.system_census or 0,
            "incentive_agent": bool(f.incentive_agent),
            "incentive_agent_amount": f.incentive_agent_amount,
            "incentive_supervisor": bool(f.incentive_supervisor),
            "incentive_supervisor_amount": f.incentive_supervisor_amount,
            "transport_full": f.transport_full or 0,
            "transport_partial": f.transport_partial or 0,
            "extra_expense_desc": f.extra_expense_desc or "",
            "extra_expense_amount": f.extra_expense_amount,
            "is_charging_owner": bool(f.is_charging_owner),
            "note": f.note or "",
            # Quien mando el cierre. Es el telefono, porque es lo unico que
            # conecta una fila con el supervisor que la lleno.
            "filled_by": f.filled_by or "",
        })

    resultado.sort(key=lambda r: (
        r["study_code"].lower(),
        r["supervisor"].lower(),
        r["interviewer"].lower(),
    ))
    return resultado


def validar_reparto(filas, system_surveys):
    """
    Comprueba que lo declarado por las personas cuadre con el total real.

    Returns:
        {"ok", "declarado", "sistema", "diferencia", "detalle": [...]}
    """
    detalle = []
    declarado = 0
    for f in filas:
        valor = f.get("surveys_declared", 0) or 0
        declarado += valor
        detalle.append({"nombre": f.get("interviewer", "?"), "surveys": valor})

    return {
        "ok": declarado == system_surveys,
        "declarado": declarado,
        "sistema": system_surveys,
        "diferencia": declarado - system_surveys,
        "detalle": detalle,
    }


def falta_por_asignar(filas, system_surveys):
    """
    Cuando no cuadra, a quien hay que corregirle.

    Sirve para decirle al supervisor exactamente a quien tocar en vez de
    limitarse a decir "no cuadra".
    """
    declarado = sum((f.get("surveys_declared", 0) or 0) for f in filas)
    diferencia = system_surveys - declarado
    if diferencia == 0:
        return []

    if diferencia > 0:
        # Faltan: la ultima persona registrada las absorbe.
        if not filas:
            return []
        return [{
            "nombre": filas[-1].get("interviewer", "?"),
            "ajuste": diferencia,
            "motivo": "le faltan {} para completar el total".format(diferencia),
        }]

    # Sobran: se las quitamos a quien mas se paso.
    sobra = -diferencia
    responsables = []
    for f in sorted(filas, key=lambda x: -(x.get("surveys_declared", 0) or 0)):
        if sobra <= 0:
            break
        quitado = min(sobra, f.get("surveys_declared", 0) or 0)
        if quitado <= 0:
            continue
        responsables.append({
            "nombre": f.get("interviewer", "?"),
            "ajuste": -quitado,
            "motivo": "se paso por {}".format(quitado),
        })
        sobra -= quitado
    return responsables


def marcar_propietario_del_gasto(db, close_date, supervisor_id, interviewer_id):
    """
    Deja en 1 la primera fila del dia de esa persona y en 0 las demas.

    Sin esto, alguien que trabajo en 2 estudios suma la misma plata dos
    veces en la fila TOTAL del reporte.
    """
    filas = (
        db.query(models.BotClosingRow)
        .filter(
            models.BotClosingRow.close_date == close_date,
            models.BotClosingRow.supervisor_id == supervisor_id,
            models.BotClosingRow.interviewer_id == interviewer_id,
        )
        .order_by(models.BotClosingRow.id)
        .all()
    )
    for i, f in enumerate(filas):
        f.is_charging_owner = 1 if i == 0 else 0
    if filas:
        db.commit()


def plata_ya_registrada(db, close_date, supervisor_id, interviewer_id):
    """
    True si esa persona ya tiene plata guardada hoy.

    La plata se cuenta una vez por persona y dia, no por estudio. Al reportar
    el segundo estudio hay que saber si se le pregunto antes: si ya tiene fila
    de gasto ese dia, no se le vuelve a preguntar y esa fila queda como dueña.
    """
    fila = (
        db.query(models.BotClosingRow)
        .filter(
            models.BotClosingRow.close_date == close_date,
            models.BotClosingRow.supervisor_id == supervisor_id,
            models.BotClosingRow.interviewer_id == interviewer_id,
        )
        .first()
    )
    if fila is None:
        return False
    return bool(
        fila.is_charging_owner
        or fila.incentive_agent
        or fila.incentive_supervisor
        or fila.transport_full
        or fila.transport_partial
        or fila.extra_expense_amount
    )


def borrar_filas_del_estudio(db, close_date, study_code, supervisor_id):
    """
    Borra lo que el supervisor habia reportado de un estudio hoy.

    Se usa cuando dice *corregir*: sin esto, lo que escribio la vez pasada se
    queda mezclado con lo nuevo y las cuentas nunca cuadran.
    """
    filas = (
        db.query(models.BotClosingRow)
        .filter(
            models.BotClosingRow.close_date == close_date,
            models.BotClosingRow.study_code == study_code,
            models.BotClosingRow.supervisor_id == supervisor_id,
        )
        .all()
    )
    for f in filas:
        db.delete(f)
    if filas:
        db.commit()
    return len(filas)
