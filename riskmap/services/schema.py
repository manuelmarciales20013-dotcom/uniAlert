"""Metadatos y opciones de campos para los formularios CRUD."""

import re
from ..config import BASE_DATOS
from ..constants import TABLAS, ETIQUETAS_ROL


def obtener_campos(tabla, conexion):
    cursor = conexion.cursor(dictionary=True)
    cursor.execute(f"SHOW COLUMNS FROM `{tabla}`")
    campos = cursor.fetchall()
    cursor.execute("""SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        AND REFERENCED_TABLE_NAME IS NOT NULL""", (BASE_DATOS["database"], tabla))
    for fk in cursor.fetchall():
        ref_tabla = fk["REFERENCED_TABLE_NAME"]
        ref_col = fk["REFERENCED_COLUMN_NAME"]
        if ref_tabla not in TABLAS:
            continue
        label_col = "nombre"
        cursor.execute(f"SHOW COLUMNS FROM `{ref_tabla}`")
        nombres = [x["Field"] for x in cursor.fetchall()]
        if label_col not in nombres:
            label_col = ref_col
        cursor.execute(f"SELECT `{ref_col}`, `{label_col}` FROM `{ref_tabla}` ORDER BY `{label_col}`")
        opciones = cursor.fetchall()
        for campo in campos:
            if campo["Field"] == fk["COLUMN_NAME"]:
                campo["options"] = [(o[ref_col], o[label_col]) for o in opciones]
    cursor.close()

    resultado = []
    pk = None
    for campo in campos:
        nombre, tipo = campo["Field"], campo["Type"]
        if campo["Key"] == "PRI":
            pk = nombre
        extra = campo["Extra"] or ""
        es_hash = tabla == "usuario" and nombre == "password_hash"
        es_clave = tabla == "usuario" and nombre == "clave"
        if es_hash:
            continue
        requerido = campo["Null"] == "NO" and not extra.lower().startswith("auto_increment")
        entrada = {
            "name": "clave" if es_clave else nombre,
            "auto": "auto_increment" in extra.lower() or es_hash,
            "required": requerido and not es_clave,
            "input_type": "number" if re.match(r"(tinyint|smallint|mediumint|int|bigint|decimal|float|double)", tipo) else None,
            "options": campo.get("options"),
        }
        enum = re.fullmatch(r"enum\((.*)\)", tipo, re.I)
        if enum:
            entrada["options"] = [(v, ETIQUETAS_ROL.get(v, v)) for v in re.findall(r"'((?:\\'|[^'])*)'", enum.group(1))]
        resultado.append(entrada)
    if tabla == "usuario":
        # Sustituye el campo oculto del hash por un campo de contraseña.
        resultado.append({"name": "clave", "auto": False, "required": False, "input_type": "password", "options": None})
    return resultado, pk


