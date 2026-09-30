"""
Busqueda difusa de personas (encuestadores / supervisores) sobre la tabla `users`.

El personal ya esta registrado en `users` (full_name, phone_number, role).
Lo unico que faltaba era la forma de encontrarlo: la gente escribe mal,
omite acentos y escribe abreviado ("jmy cardena" -> "Jinny Cardenas").

El scoring se hace en Python con difflib para que funcione igual en
SQLite (dev) y Postgres/MySQL (produccion), sin depender de pg_trgm.
"""

import difflib
import re
import unicodedata

# Umbral minimo para considerar que hay una coincidencia.
UMBRAL_MINIMO = 0.55
# Si el segundo candidato esta mas cerca de este margen, hay que preguntar.
MARGEN_AMBIGUEDAD = 0.10
# Cada palabra escrita tiene que parecerse a alguna del nombre candidato.
# Sin este piso, "jose pineda" promedia 0.55 contra "Johana Pinzon" (pineda ~0.5
# y jose ~0.4) y el cierre le cuelga la plata a la persona equivocada.
# Medido sobre los 100 usuarios reales: contra la persona correcta el token
# mas flojo nunca baja de 0.8, con abreviaturas ("jmy" -> "jinny") llega a 0.5.
UMBRAL_TOKEN = 0.5

# Peso de cada componente del puntaje (suman 1.0).
PESO_TOKENS = 0.45
PESO_TEXTO = 0.40
PESO_INICIAL = 0.15


def normalizar(texto):
    """Quita acentos, pasa a minusculas y deja solo letras y digitos.

    "Tatiana Muñoz" -> ['tatiana', 'munoz']
    """
    if not texto:
        return []
    limpio = unicodedata.normalize("NFKD", str(texto))
    limpio = limpio.encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^a-z0-9 ]", " ", limpio.lower())
    return limpio.split()


def _variantes(token):
    """
    Como se puede escribir mal un token, en orden de preferencia.

    Se usa para "el nombre invertido": la gente escribe "cardenas juli" para
    'Juli Cardenas', y comparar token a token en el mismo orden no lo ve.
    """
    variantes = [token]
    partes = re.split(r"(\d+)", token)
    if len(partes) > 2:
        # "juli3" -> "juli" (julio, julia...)
        con_digitos = re.sub(r"\d+$", "", token)
        sin_digitos = re.sub(r"\d", "", token)
        if con_digitos and con_digitos != token:
            variantes.append(con_digitos)
        if sin_digitos and sin_digitos != token:
            variantes.append(sin_digitos)
    if len(token) > 3 and token.endswith("s"):
        variantes.append(token[:-1])
    return variantes


def puntuar(consulta_norm, candidato_norm):
    """Similitud entre 0.0 y 1.0 entre una consulta y un nombre ya normalizados."""
    if not consulta_norm or not candidato_norm:
        return 0.0

    # Cada token de la consulta contra su mejor equivalente en el candidato.
    # Se prueban las variantes (sin digitos, sin 's' final) porque la gente
    # abrevia: "juli" por "julio", "vergara" por "Vergara".
    candidatos_token = []
    for otro in candidato_norm:
        candidatos_token.extend(_variantes(otro))

    tokens = []
    for token in consulta_norm:
        tokens.append(
            max(difflib.SequenceMatcher(None, v, otro).ratio()
                for v in _variantes(token)
                for otro in candidatos_token)
        )

    # Una palabra que no se parece a ninguna del nombre descarta al candidato.
    # El promedio solo no alcanza: con dos palabras, una buena y otra inventada,
    # el promedio queda en medio y el nombre equivocado pasa el filtro.
    if min(tokens) < UMBRAL_TOKEN:
        return 0.0

    puntaje_tokens = sum(tokens) / len(tokens)

    # Comparacion de la frase completa.
    puntaje_texto = difflib.SequenceMatcher(
        None, " ".join(consulta_norm), " ".join(candidato_norm)
    ).ratio()

    # Los nombres propios arrancan distinto,asi que un fallo ahi pesa.
    puntaje_inicial = 1.0 if candidato_norm[0][:2] == consulta_norm[0][:2] else 0.0

    return (
        PESO_TOKENS * puntaje_tokens
        + PESO_TEXTO * puntaje_texto
        + PESO_INICIAL * puntaje_inicial
    )


def buscar_personas(db_users, texto, rol=None, limite=5):
    """
    Busca personas por nombre en `users`.

    Parametros:
        db_users: sesion contra la base de usuarios
        texto:    lo que escribio la persona
        rol:      filtro opcional ('supervisor', 'agent', 'superuser')
        limite:   maximo de sugerencias

    Returns:
        {
            "consulta": "jmy cardena",
            "encontrado": True,
            "exacto": "Jinny Cardenas",   # unico candidato claro
            "sugerencias": [{"id":127, "nombre":"Jinny Cardenas",
                             "telefono":"3136623816", "rol":"agent",
                             "score":0.64}, ...],
            "ambiguo": False,
        }
    """
    from sqlalchemy import text

    consulta_norm = normalizar(texto)
    vacio = {
        "consulta": texto or "",
        "encontrado": False,
        "exacto": None,
        "sugerencias": [],
        "ambiguo": False,
    }
    if not consulta_norm:
        return vacio

    sql = text("""
        SELECT id, full_name, phone_number, role
        FROM users
        WHERE full_name IS NOT NULL AND TRIM(full_name) != ''
    """)
    try:
        registros = db_users.execute(sql).fetchall()
    except Exception:
        return vacio

    candidatos = []
    for reg in registros:
        if rol and (reg.role or "") != rol:
            continue
        nombre = (reg.full_name or "").strip()
        score = puntuar(consulta_norm, normalizar(nombre))
        if score >= UMBRAL_MINIMO:
            candidatos.append(
                {
                    "id": reg.id,
                    "nombre": nombre,
                    "telefono": reg.phone_number or "",
                    "rol": reg.role or "",
                    "score": round(score, 3),
                }
            )

    if not candidatos:
        vacio["consulta"] = texto
        return vacio

    candidatos.sort(key=lambda c: c["score"], reverse=True)
    sugerencias = candidatos[:limite]

    primero = sugerencias[0]
    segundo = sugerencias[1]["score"] if len(sugerencias) > 1 else 0.0
    hay_claro = primero["score"] - segundo >= MARGEN_AMBIGUEDAD

    return {
        "consulta": texto,
        "encontrado": True,
        "exacto": primero["nombre"] if hay_claro else None,
        "sugerencias": sugerencias,
        "ambiguo": not hay_claro,
    }


def buscar_por_telefono(db_users, telefono):
    """Busca la persona cuyo numero coincide, con o sin prefijo 57."""
    from sqlalchemy import text

    if not telefono:
        return None
    digitos = "".join(ch for ch in str(telefono) if ch.isdigit())
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]

    sql = text("""
        SELECT id, full_name, phone_number, role
        FROM users
        WHERE REPLACE(REPLACE(phone_number, '+', ''), ' ', '') = :p
           OR phone_number = :p
        ORDER BY LENGTH(phone_number) DESC
        LIMIT 1
    """)
    try:
        reg = db_users.execute(sql, {"p": digitos}).first()
    except Exception:
        return None
    if not reg:
        return None
    return {
        "id": reg.id,
        "nombre": (reg.full_name or "").strip(),
        "telefono": reg.phone_number or "",
        "rol": reg.role or "",
    }
