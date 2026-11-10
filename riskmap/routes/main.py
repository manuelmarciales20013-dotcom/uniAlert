import base64
import io

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..auth import requiere_login
from ..constants import CORTES
from ..database import conectar
from ..services.calificaciones import cargar_calificaciones_excel
from ..services.grupos import (
    listar_grupos_usuario,
    obtener_dashboard_usuario,
    obtener_detalle_grupo,
    obtener_grupo,
    obtener_perfil_estudiante,
    usuario_puede_modificar_grupo,
    usuario_puede_ver_grupo,
)
from ..services.importacion import importar_estudiantes
from ..services.inasistencias import (
    cargar_inasistencias_excel,
    comparar_grupo_excel,
    corte_inasistencia_ocupado,
    leer_titulo_excel,
)
from ..services.pdf_inasistencia import (
    convertir_pdf_a_excel_bytes,
    convertir_pdf_tabla_a_excel_bytes,
)

bp = Blueprint("main", __name__)


def _a_excel_en_memoria(archivo):
    """Recibe un PDF subido y devuelve su Excel (.xlsx) en memoria."""
    nombre = (archivo.filename if archivo else "").lower()
    if not archivo or not (nombre.endswith(".pdf") or nombre.endswith(".xlsx")):
        raise ValueError("Selecciona un archivo en formato .pdf.")
    if nombre.endswith(".pdf"):
        return convertir_pdf_tabla_a_excel_bytes(archivo)
    return io.BytesIO(archivo.read())


@bp.route("/")
@requiere_login
def inicio():
    programas = []
    grupos = []
    dashboard = {"kpis": {"total": 0, "normal": 0, "atencion": 0, "prioritario": 0}, "barras": [], "prioritarios": []}
    rol = session["usuario"]["rol"]

    if rol in ("profesor", "director_programa"):
        conexion = conectar()
        try:
            if rol == "profesor":
                cursor = conexion.cursor()
                cursor.execute("SELECT id_programa,nombre FROM programa ORDER BY nombre")
                programas = cursor.fetchall()
                cursor.close()
            grupos = listar_grupos_usuario(session["usuario"], conexion=conexion)
            dashboard = obtener_dashboard_usuario(session["usuario"], grupos, conexion=conexion)
        finally:
            conexion.close()

    return render_template(
        "main/inicio.html",
        titulo="Inicio",
        programas=programas,
        grupos=grupos,
        dashboard=dashboard,
    )


@bp.post("/importar")
@requiere_login
def importar():
    if session["usuario"]["rol"] != "profesor":
        abort(403)
    try:
        id_programa = int(request.form.get("id_programa", ""))
        excel_bytes = _a_excel_en_memoria(request.files.get("archivo"))
        resumen = importar_estudiantes(excel_bytes, id_programa)
        flash(f"Importación completada: {resumen['nuevos']} nuevos, {resumen['existentes']} ya existentes.")
    except Exception as error:
        flash(f"No se pudo procesar el archivo: {error}", "error")
    return redirect(url_for("main.inicio"))


def _renderizar_vista_grupo(grupo, confirmacion_pendiente=None):
    detalle = obtener_detalle_grupo(grupo["id_grupo"])
    return render_template(
        "main/grupo.html",
        titulo=f"{grupo['asignatura']} - {grupo['nombre_grupo']}",
        grupo=grupo,
        estudiantes=detalle["estudiantes"],
        cortes_inasistencia=detalle["cortes_inasistencia"],
        resumen_riesgo=detalle["resumen_riesgo"],
        en_riesgo=detalle.get("en_riesgo", []),
        cortes=CORTES,
        puede_modificar=usuario_puede_modificar_grupo(session["usuario"], grupo),
        confirmacion_pendiente=confirmacion_pendiente,
    )


@bp.route("/grupos/<int:id_grupo>")
@requiere_login
def ver_grupo(id_grupo):
    grupo = obtener_grupo(id_grupo)
    if not grupo:
        abort(404)
    if not usuario_puede_ver_grupo(session["usuario"], grupo):
        abort(403)
    return _renderizar_vista_grupo(grupo)


@bp.route("/estudiantes/<int:id_estudiante>")
@requiere_login
def ver_estudiante(id_estudiante):
    perfil = obtener_perfil_estudiante(id_estudiante)
    if not perfil:
        abort(404)

    usuario = session["usuario"]
    if usuario.get("rol") == "profesor":
        correo_prof = (usuario.get("correo") or "").strip().lower()
        tiene_grupo = any(
            (m.get("correo_docente") or "").strip().lower() == correo_prof
            for m in perfil["materias"]
        )
        if not tiene_grupo:
            abort(403)

    return render_template(
        "main/estudiante.html",
        titulo=f"Estudiante: {perfil['estudiante']['nombre']}",
        estudiante=perfil["estudiante"],
        materias=perfil["materias"],
        riesgo_global=perfil["riesgo_global"],
    )


@bp.post("/grupos/<int:id_grupo>/inasistencias")
@requiere_login
def cargar_inasistencias(id_grupo):
    grupo = obtener_grupo(id_grupo)
    if not grupo:
        abort(404)
    if not usuario_puede_modificar_grupo(session["usuario"], grupo):
        abort(403)

    corte = request.form.get("corte", "").strip()
    confirmar = request.form.get("confirmar", "")
    archivo_b64 = request.form.get("archivo_b64", "")
    archivo = request.files.get("archivo")

    try:
        if corte not in CORTES:
            raise ValueError("Selecciona un corte válido (P1, P2 o Exa).")

        if archivo_b64:
            excel_bytes = io.BytesIO(base64.b64decode(archivo_b64))
        else:
            if not archivo or not archivo.filename.lower().endswith(".pdf"):
                raise ValueError("Selecciona un reporte de inasistencia en formato .pdf.")
            excel_bytes = convertir_pdf_a_excel_bytes(archivo)

        if confirmar != "si":
            avisos = []
            aviso_grupo = comparar_grupo_excel(leer_titulo_excel(excel_bytes), grupo)
            if aviso_grupo:
                avisos.append(aviso_grupo)
            if corte_inasistencia_ocupado(id_grupo, corte):
                avisos.append(
                    f"El corte {corte} ya tiene inasistencias registradas en este grupo. "
                    "Si confirmas, se sobrescribirán los datos de este corte."
                )
            if avisos:
                return _renderizar_vista_grupo(
                    grupo,
                    confirmacion_pendiente={
                        "titulo": f"Confirmar carga de inasistencias ({corte})",
                        "url_destino": url_for("main.cargar_inasistencias", id_grupo=id_grupo),
                        "corte": corte,
                        "avisos": avisos,
                        "archivo_b64": base64.b64encode(excel_bytes.getvalue()).decode("ascii"),
                    },
                )

        resumen = cargar_inasistencias_excel(excel_bytes, id_grupo, corte)
        flash(
            f"Inasistencias de {corte} cargadas: "
            f"{resumen['nuevos']} nuevos, {resumen['actualizados']} actualizados."
        )
        for msj in resumen["omitidos"] + resumen["errores"]:
            flash(msj, "error")

    except Exception as error:
        flash(f"No se pudo procesar la carga de inasistencias: {error}", "error")

    return redirect(url_for("main.ver_grupo", id_grupo=id_grupo))


@bp.post("/grupos/<int:id_grupo>/calificaciones")
@requiere_login
def cargar_calificaciones(id_grupo):
    grupo = obtener_grupo(id_grupo)
    if not grupo:
        abort(404)
    if not usuario_puede_modificar_grupo(session["usuario"], grupo):
        abort(403)

    try:
        excel_bytes = _a_excel_en_memoria(request.files.get("archivo"))
        resumen = cargar_calificaciones_excel(excel_bytes, id_grupo)
        cortes_txt = ", ".join(resumen["cortes_activos"]) or "ningún corte activo"
        flash(
            f"Calificaciones actualizadas ({cortes_txt}): "
            f"{resumen['nuevos']} nuevos, {resumen['actualizados']} actualizados."
        )
        for msj in resumen["omitidos"] + resumen["errores"]:
            flash(msj, "error")

    except Exception as error:
        flash(f"No se pudo procesar la carga de calificaciones: {error}", "error")

    return redirect(url_for("main.ver_grupo", id_grupo=id_grupo))
