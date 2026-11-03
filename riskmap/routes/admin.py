from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash
from ..auth import requiere_admin
from ..constants import TABLAS
from ..database import conectar
from ..services.schema import obtener_campos

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@requiere_admin
def admin_inicio():
    return render_template("admin/index.html", titulo="Administrador", tablas=TABLAS)


@bp.route("/admin/<tabla>")
@requiere_admin
def admin_tabla(tabla):
    if tabla not in TABLAS:
        abort(404)
    conexion = conectar()
    try:
        campos, pk = obtener_campos(tabla, conexion)
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM `{tabla}` ORDER BY `{pk}` DESC LIMIT 500")
        filas = cursor.fetchall()
        registro = None
        if request.args.get("editar"):
            cursor.execute(f"SELECT * FROM `{tabla}` WHERE `{pk}`=%s", (request.args["editar"],))
            registro = cursor.fetchone()
        cursor.close()
    finally:
        conexion.close()
    return render_template("admin/tabla.html", titulo=tabla, tabla=tabla, campos=campos, pk=pk, filas=filas, registro=registro)


@bp.post("/admin/<tabla>/guardar")
@requiere_admin
def guardar_registro(tabla):
    if tabla not in TABLAS:
        abort(404)
    conexion = conectar()
    cursor = None
    try:
        campos, pk = obtener_campos(tabla, conexion)
        cursor = conexion.cursor()
        accion = request.form.get("accion")
        if accion == "eliminar":
            cursor.execute(f"DELETE FROM `{tabla}` WHERE `{pk}`=%s", (request.form["pk_value"],))
        elif accion in ("crear", "actualizar"):
            values = {}
            for campo in campos:
                nombre = campo["name"]
                if campo["auto"]:
                    continue
                valor = request.form.get(nombre, "").strip()
                if tabla == "usuario" and nombre == "clave":
                    if valor:
                        values["password_hash"] = generate_password_hash(valor)
                    elif accion == "crear":
                        raise ValueError("La contraseña es obligatoria para crear una cuenta.")
                    continue
                values[nombre] = valor if valor != "" else None
            if accion == "crear":
                columnas = list(values)
                sql_cols = ", ".join(f"`{c}`" for c in columnas)
                placeholders = ", ".join(["%s"] * len(columnas))
                cursor.execute(f"INSERT INTO `{tabla}` ({sql_cols}) VALUES ({placeholders})", tuple(values[c] for c in columnas))
            else:
                if not values:
                    raise ValueError("No hay campos para actualizar.")
                asignaciones = ", ".join(f"`{c}`=%s" for c in values)
                cursor.execute(f"UPDATE `{tabla}` SET {asignaciones} WHERE `{pk}`=%s", (*values.values(), request.form["pk_value"]))
        else:
            abort(400)
        conexion.commit()
        flash("Registro guardado correctamente." if accion != "eliminar" else "Registro eliminado.")
    except Exception as error:
        conexion.rollback()
        flash(f"No se pudo guardar el registro: {error}", "error")
    finally:
        if cursor:
            cursor.close()
        conexion.close()
    return redirect(url_for("admin.admin_tabla", tabla=tabla))


