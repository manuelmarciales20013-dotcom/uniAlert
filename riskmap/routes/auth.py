import mysql.connector
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from ..database import conectar, asegurar_tabla_usuarios

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    try:
        asegurar_tabla_usuarios()
    except mysql.connector.Error as error:
        flash(f"No se pudo conectar con la base de datos: {error}", "error")
        return render_template("auth/login.html", titulo="Iniciar sesión"), 503
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")
        conexion = conectar()
        try:
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario,nombre,correo,password_hash,rol,id_programa FROM usuario WHERE correo=%s", (correo,))
            cuenta = cursor.fetchone()
            cursor.close()
        finally:
            conexion.close()
        if cuenta and check_password_hash(cuenta["password_hash"], clave):
            session.clear()
            session["usuario"] = {k: cuenta[k] for k in ("id_usuario", "nombre", "correo", "rol", "id_programa")}
            return redirect(url_for("main.inicio"))
        flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth/login.html", titulo="Iniciar sesión")


@bp.route("/logout")
def cerrar_sesion():
    session.clear()
    return redirect(url_for("auth.login"))


