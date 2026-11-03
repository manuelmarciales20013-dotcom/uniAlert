from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from ..auth import requiere_login
from ..database import conectar
from ..services.importacion import importar_estudiantes

bp = Blueprint("main", __name__)


@bp.route("/")
@requiere_login
def inicio():
    programas = []
    if session["usuario"]["rol"] == "profesor":
        conexion = conectar()
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT id_programa,nombre FROM programa ORDER BY nombre")
            programas = cursor.fetchall()
            cursor.close()
        finally:
            conexion.close()
    return render_template("main/inicio.html", titulo="Inicio", programas=programas)


@bp.post("/importar")
@requiere_login
def importar():
    if session["usuario"]["rol"] != "profesor":
        abort(403)
    archivo = request.files.get("archivo")
    try:
        id_programa = int(request.form.get("id_programa", ""))
        if not archivo or not archivo.filename.lower().endswith(".xlsx"):
            raise ValueError("Selecciona un archivo .xlsx.")
        resumen = importar_estudiantes(archivo, id_programa)
        flash(f"Importación completada: {resumen['nuevos']} nuevos, {resumen['existentes']} ya existentes.")
    except Exception as error:
        flash(f"No se pudo procesar el archivo: {error}", "error")
    return redirect(url_for("main.inicio"))


