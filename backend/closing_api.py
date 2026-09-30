"""
API del cierre diario de campo.

El superusuario dispara el cierre desde el panel: mira quien falta, envia el
reporte a superusuario y observadores y descarga la imagen o el Excel. No hay
agenda ni recordatorios: cada envio es manual.

El formulario lo llena el supervisor por WhatsApp; estos endpoints son la vista
del superusuario y el respaldo cuando algo quedo mal.
"""

import io
import os
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import auth, closing, database, models, render_utils, upload_media


def _destinatarios():
    """A quien le llega el reporte: superusuario y observadores.

    Se resuelve por dentro porque `main` registra este router al final: si se
    importara arriba del todo, `closing_api` arrastraria a `main` y no al reves.
    """
    from .main import CLOSING_RECIPIENTS

    return list(CLOSING_RECIPIENTS)


def _enviar_imagen(phone, media_id, caption):
    """Manda la imagen por WhatsApp."""
    from .main import send_whatsapp_media

    return send_whatsapp_media(phone, "image", media_id, caption)

router = APIRouter(prefix="/api/closing", tags=["cierre"])

ROLES_CIERRE = ("superuser", "coordinator")

# Orden de las columnas: el mismo del reporte que ve la gente en WhatsApp.
COLUMNAS_EXCEL = [
    "estudio", "fecha", "codigo", "supervisor", "encuestador",
    "inc_enc", "inc_sup", "t_compl", "t_med", "gasto",
    "censos", "encuestas", "nota",
]

# Encabezados que se leen en el Excel: cada clave interna tiene su rotulo,
# porque "t_compl" no le dice nada a nadie.
ENCABEZADOS_EXCEL = {
    "estudio": "Estudio",
    "fecha": "Fecha",
    "codigo": "Código",
    "supervisor": "Supervisor",
    "encuestador": "Encuestador",
    "inc_enc": "Incent. Enc",
    "inc_sup": "Incent. Sup",
    "t_compl": "T. completos",
    "t_med": "T. medios",
    "gasto": "Gasto adic.",
    "censos": "Censos",
    "encuestas": "Encuestas",
    "nota": "Nota",
}


def _requiere_rol_cierre(current_user):
    if current_user.role not in ROLES_CIERRE:
        raise HTTPException(
            status_code=403,
            detail="Solo el superusuario puede ver el cierre diario.",
        )
    return current_user


def _pedir_fecha(fecha):
    """Valida el YYYY-MM-DD que llega por query."""
    if not fecha:
        raise HTTPException(status_code=400, detail="Falta la fecha del cierre.")
    try:
        datetime.strptime(fecha, closing.FECHA_FORMATO)
    except ValueError:
        raise HTTPException(status_code=400, detail="La fecha debe ir en formato YYYY-MM-DD.")
    return fecha


def columna_letra(indice):
    """1 -> A, 2 -> B, ... para dar ancho a las columnas del Excel."""
    letra = ""
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letra = chr(65 + resto) + letra
    return letra


def _filas_presentacion(datos):
    """Los mismos textos de la imagen, fila por fila.

    Se reutiliza el formateo del render para que el Excel y el PNG no se
    contradigan (por ejemplo "$25.000" en vez de 25000).
    """
    _, total = render_utils._filas_cierre(datos)
    presentacion = []
    for fila in datos:
        filas, _ = render_utils._filas_cierre([fila])
        presentacion.append({c: filas[0].get(c, "") for c in COLUMNAS_EXCEL})
    return presentacion, total


# --- consulta ------------------------------------------------------------

@router.get("/pending")
def pendientes(
    fecha: str = "",
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Quien registro ese dia y si ya mando su cierre."""
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)

    lista = closing.get_pending_supervisors(db, fecha)
    faltantes = [e for e in lista if not e["enviado"]]
    en_proceso = [e for e in lista if e.get("en_proceso")]
    return {
        "fecha": fecha,
        "total": len(lista),
        "enviados": len(lista) - len(faltantes),
        "faltantes": len(faltantes),
        "en_proceso": len(en_proceso),
        "completo": not faltantes,
        "supervisores": lista,
    }


@router.get("/rows")
def filas(
    fecha: str = "",
    study_code: str = "",
    db: Session = Depends(database.get_db),
    db_users: Session = Depends(database.get_users_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Lo guardado del dia, con los nombres resueltos desde `users`."""
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)

    datos = closing.get_closing_rows(db, db_users, fecha, study_code or None)
    return {"fecha": fecha, "rows": datos, "count": len(datos)}


@router.get("/validate")
def validar(
    fecha: str = "",
    study_code: str = "",
    db: Session = Depends(database.get_db),
    db_users: Session = Depends(database.get_users_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Si lo declarado por las personas cuadra con el total real del sistema.

    La comparacion es por supervisor y por estudio, no sobre el total del dia:
    cada uno responde por lo suyo y no se le endosa a otro lo que le falta.
    """
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)

    datos = closing.get_closing_rows(db, db_users, fecha, study_code or None)

    # El sistema mide por telefono, la tabla guarda `users.id`: hay que pasar
    # de uno a otro para comparar lo mismo con lo mismo.
    telefonos = closing.telefonos_de_supervisores(db_users)

    # Sistema: total por (supervisor, estudio).
    sistema = {}
    for t in closing.get_day_totals_by_supervisor(db, fecha):
        if study_code and t["study_code"] != study_code:
            continue
        clave = (t["phone"], t["study_code"])
        sistema[clave] = sistema.get(clave, 0) + t["surveys"]

    # Cerrado: por supervisor y estudio.
    cerrado = {}
    for f in datos:
        phone = telefonos.get(f["supervisor_id"], "")
        clave = (phone, f["study_code"])
        cerrado.setdefault(clave, []).append(f)

    grupos = []
    for clave in sorted(set(cerrado) | set(sistema)):
        phone, estudio = clave
        filas = cerrado.get(clave, [])
        total = sistema.get(clave, 0)
        resultado = closing.validar_reparto(filas, total)
        resultado["correcciones"] = closing.falta_por_asignar(filas, total)
        resultado.update({
            "phone": phone,
            "supervisor": filas[0]["supervisor"] if filas else "",
            "study_code": estudio,
            "personas": len(filas),
        })
        grupos.append(resultado)

    return {
        "fecha": fecha,
        "ok": all(g["ok"] for g in grupos),
        "grupos": grupos,
        "total_sistema": sum(sistema.values()),
        "total_declarado": sum(g["declarado"] for g in grupos),
    }


# --- correccion puntual ---------------------------------------------------

class FilaRequest(BaseModel):
    fecha: str
    study_code: str
    supervisor_id: int
    interviewer_id: int
    surveys_declared: int = 0
    census_declared: int = 0
    incentive_agent: bool = False
    incentive_agent_amount: int = 0
    incentive_supervisor: bool = False
    incentive_supervisor_amount: int = 0
    transport_full: int = 0
    transport_partial: int = 0
    extra_expense_desc: str = ""
    extra_expense_amount: int = 0
    note: str = ""


@router.post("/row")
def guardar_fila(
    req: FilaRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Respaldo para corregir una fila sin pasar por WhatsApp."""
    _requiere_rol_cierre(current_user)
    _pedir_fecha(req.fecha)

    fila = closing.upsert_closing_row(
        db, req.fecha, req.study_code, req.supervisor_id, req.interviewer_id,
        filled_by="panel:{}".format(current_user.username),
        surveys_declared=req.surveys_declared,
        census_declared=req.census_declared,
        system_surveys=0,
        system_census=0,
        incentive_agent=1 if req.incentive_agent else 0,
        incentive_agent_amount=req.incentive_agent_amount if req.incentive_agent else None,
        incentive_supervisor=1 if req.incentive_supervisor else 0,
        incentive_supervisor_amount=req.incentive_supervisor_amount if req.incentive_supervisor else None,
        transport_full=req.transport_full,
        transport_partial=req.transport_partial,
        extra_expense_desc=req.extra_expense_desc or None,
        extra_expense_amount=req.extra_expense_amount or None,
        note=req.note or None,
    )
    closing.marcar_propietario_del_gasto(
        db, req.fecha, req.supervisor_id, req.interviewer_id
    )
    return {"ok": True, "id": fila.id}


# --- reportes ------------------------------------------------------------

def _generar_imagen(db, db_users, fecha):
    """Dibuja el reporte y devuelve la ruta del PNG."""
    datos = closing.get_closing_rows(db, db_users, fecha)
    if not datos:
        raise HTTPException(status_code=404, detail="Ese dia todavia no tiene cierre.")

    ruta = os.path.join(tempfile.gettempdir(), "cierre_{}.png".format(fecha))
    render_utils.generate_closing_report_image(datos, fecha, ruta)
    return datos, ruta


@router.get("/report/image")
def imagen(
    fecha: str = "",
    db: Session = Depends(database.get_db),
    db_users: Session = Depends(database.get_users_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """La imagen del reporte tal como se manda por WhatsApp."""
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)
    _, ruta = _generar_imagen(db, db_users, fecha)

    return FileResponse(
        ruta,
        media_type="image/png",
        filename="cierre_{}.png".format(fecha),
    )


@router.get("/report/excel")
def excel(
    fecha: str = "",
    db: Session = Depends(database.get_db),
    db_users: Session = Depends(database.get_users_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    El mismo reporte en Excel, una fila por persona y estudio.

    El TOTAL cuenta el dinero una sola vez por persona, igual que la imagen.
    """
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)

    datos = closing.get_closing_rows(db, db_users, fecha)
    if not datos:
        raise HTTPException(status_code=404, detail="Ese dia todavia no tiene cierre.")

    import pandas as pd

    presentacion, total = _filas_presentacion(datos)
    tabla = pd.DataFrame(presentacion, columns=COLUMNAS_EXCEL).rename(
        columns=ENCABEZADOS_EXCEL
    )
    fila_total = pd.DataFrame(
        [{ENCABEZADOS_EXCEL[c]: total.get(c, "") for c in COLUMNAS_EXCEL}],
        columns=[ENCABEZADOS_EXCEL[c] for c in COLUMNAS_EXCEL],
    )

    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        tabla.to_excel(escritor, sheet_name="Cierre", index=False)
        # Una fila de separacion antes del TOTAL para que resalte.
        fila_total.to_excel(
            escritor, sheet_name="Cierre", index=False, startrow=len(tabla) + 2
        )

        # Negrita en el encabezado y en la fila TOTAL.
        hoja = escritor.sheets["Cierre"]
        for celda in hoja[1]:
            celda.font = celda.font.copy(bold=True)
        for celda in hoja[len(tabla) + 3]:
            celda.font = celda.font.copy(bold=True)
        for indice, columna in enumerate(tabla.columns, start=1):
            ancho = max(len(str(columna)), 12)
            hoja.column_dimensions[columna_letra(indice)].width = ancho
    salida.seek(0)

    return Response(
        salida.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="cierre_{}.xlsx"'.format(fecha)
        },
    )


@router.get("/recipients")
def recipients(current_user: models.User = Depends(auth.get_current_user)):
    """A quien le llega el reporte: superusuario y observadores."""
    _requiere_rol_cierre(current_user)
    return {"recipients": _destinatarios()}


@router.post("/broadcast")
def broadcast(
    fecha: str = "",
    db: Session = Depends(database.get_db),
    db_users: Session = Depends(database.get_users_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Envia la imagen del reporte a superusuario y observadores.

    Siempre es una llamada manual: no hay agenda ni recordatorios. Si todavia
    falta alguien, se responde igual y la respuesta lo dice.
    """
    _requiere_rol_cierre(current_user)
    fecha = _pedir_fecha(fecha)

    _, ruta = _generar_imagen(db, db_users, fecha)

    faltantes = [
        e["phone"] for e in closing.get_pending_supervisors(db, fecha)
        if not e["enviado"]
    ]

    media_id = upload_media.upload_media(ruta, "image/png")
    if not media_id:
        raise HTTPException(
            status_code=502, detail="No se pudo subir la imagen a WhatsApp."
        )

    total = closing.get_day_totals_by_supervisor(db, fecha)
    encabezado = "📊 *CIERRE DIARIO DE CAMPO* — {}".format(fecha)
    resumen_linea = "{} encuesta(s) en {} estudio(s).".format(
        sum(t["surveys"] for t in total),
        len({t["study_code"] for t in total}),
    )
    pie = (
        "⚠️ Aún faltan {} supervisor(es) por reportar: {}".format(
            len(faltantes), ", ".join(faltantes)
        )
        if faltantes else "✅ Todos los supervisores reportaron."
    )
    caption = "{}\n{}\n{}".format(encabezado, resumen_linea, pie)

    destinos = sorted(set(_destinatarios()))
    errores = []
    for phone in destinos:
        try:
            _enviar_imagen(phone, media_id, caption)
        except Exception as e:
            print("Error enviando el cierre a {}: {}".format(phone, e))
            errores.append(phone)

    return {
        "ok": True,
        "media_id": media_id,
        "enviados_a": [p for p in destinos if p not in errores],
        "errores": errores,
        "faltantes": faltantes,
        "completo": not faltantes,
    }
