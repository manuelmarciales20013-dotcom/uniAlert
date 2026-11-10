"""Consultas de grupos, dashboards de riesgo y perfil individual del estudiante."""

from ..database import conectar
from .riesgo import (
    evaluar_riesgo_global_estudiante,
    evaluar_riesgo_materia,
    resumen_conteos_riesgo,
)

SQL_GRUPOS = """
    SELECT
        g.id_grupo,
        g.cod_grupo,
        g.nombre AS nombre_grupo,
        a.cod_asignatura,
        a.nombre AS asignatura,
        a.semestre,
        p.id_programa,
        p.nombre AS programa,
        pe.nombre AS periodo,
        d.nombre AS docente,
        d.correo AS correo_docente
    FROM grupo g
    JOIN asignatura a ON g.id_asignatura = a.id_asignatura
    JOIN programa p ON a.id_programa = p.id_programa
    JOIN periodo pe ON g.id_periodo = pe.id_periodo
    JOIN docente d ON g.id_docente = d.id_docente
"""


def _limpiar_cortes_no_evaluados(registros):
    """Si en un grupo toda la columna de un corte es 0, se pasa a None (NULL)."""
    por_grupo = {}
    for r in registros:
        id_g = r.get("id_grupo")
        if id_g not in por_grupo:
            por_grupo[id_g] = []
        por_grupo[id_g].append(r)

    for filas in por_grupo.values():
        for col in ("nota_1", "nota_2", "nota_3"):
            tiene_notas = False
            for f in filas:
                if f.get(col) is not None and float(f[col]) > 0:
                    tiene_notas = True
                    break
            if not tiene_notas:
                for f in filas:
                    f[col] = None


def listar_grupos_usuario(usuario, conexion=None):
    """Lista los grupos del profesor o todos los grupos para el director."""
    cerrar = conexion is None
    if cerrar:
        conexion = conectar()

    cursor = conexion.cursor(dictionary=True)
    try:
        if usuario.get("rol") == "profesor":
            correo = (usuario.get("correo") or "").strip().lower()
            cursor.execute(
                SQL_GRUPOS + " WHERE LOWER(d.correo) = %s ORDER BY pe.nombre DESC, a.nombre ASC",
                (correo,)
            )
        else:
            cursor.execute(
                SQL_GRUPOS + " ORDER BY pe.nombre DESC, p.nombre ASC, a.semestre ASC, a.nombre ASC"
            )
        filas = cursor.fetchall() or []
        return [fila for fila in filas if isinstance(fila, dict)]
    finally:
        cursor.close()
        if cerrar:
            conexion.close()


def obtener_grupo(id_grupo):
    """Busca un grupo por su ID."""
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(SQL_GRUPOS + " WHERE g.id_grupo = %s", (id_grupo,))
        grupo = cursor.fetchone()
        return grupo if isinstance(grupo, dict) else None
    finally:
        cursor.close()
        conexion.close()


def usuario_puede_modificar_grupo(usuario, grupo):
    """Verifica si el usuario es el profesor titular del grupo."""
    if not usuario or not grupo or usuario.get("rol") != "profesor":
        return False
    correo_usuario = (usuario.get("correo") or "").strip().lower()
    correo_docente = (grupo.get("correo_docente") or "").strip().lower()
    return correo_usuario != "" and correo_usuario == correo_docente


def usuario_puede_ver_grupo(usuario, grupo):
    """El director y el administrador ven todos los grupos; el profesor solo los suyos."""
    if not usuario or not grupo:
        return False
    if usuario.get("rol") in ("director_programa", "administrador"):
        return True
    return usuario_puede_modificar_grupo(usuario, grupo)


def obtener_detalle_grupo(id_grupo):
    """Obtiene los estudiantes de un grupo y calcula el riesgo de cada uno."""
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                %s AS id_grupo,
                e.id_estudiante,
                e.cod_estudiante,
                e.nombre,
                e.correo,
                c.corte_1 AS nota_1,
                c.corte_2 AS nota_2,
                c.corte_3 AS nota_3,
                i.corte_1 AS inas_1,
                i.corte_2 AS inas_2,
                i.corte_3 AS inas_3
            FROM estudiante e
            LEFT JOIN calificacion c
                ON c.id_estudiante = e.id_estudiante AND c.id_grupo = %s
            LEFT JOIN inasistencia i
                ON i.id_estudiante = e.id_estudiante AND i.id_grupo = %s
            LEFT JOIN grupo_estudiante ge
                ON ge.id_estudiante = e.id_estudiante AND ge.id_grupo = %s
            WHERE c.id_calificacion IS NOT NULL
               OR i.id_inasistencia IS NOT NULL
               OR ge.id_grupo_estudiante IS NOT NULL
            ORDER BY e.nombre ASC
            """,
            (id_grupo, id_grupo, id_grupo, id_grupo)
        )
        filas = cursor.fetchall() or []
        estudiantes = [f for f in filas if isinstance(f, dict)]

        _limpiar_cortes_no_evaluados(estudiantes)

        cortes_inasistencia = {"P1": False, "P2": False, "Exa": False}
        en_riesgo = []

        for est in estudiantes:
            if est.get("inas_1") is not None:
                cortes_inasistencia["P1"] = True
            if est.get("inas_2") is not None:
                cortes_inasistencia["P2"] = True
            if est.get("inas_3") is not None:
                cortes_inasistencia["Exa"] = True

            riesgo = evaluar_riesgo_materia(
                est.get("nota_1"), est.get("nota_2"), est.get("nota_3"),
                est.get("inas_1"), est.get("inas_2"), est.get("inas_3"),
            )
            est.update(riesgo)

            if est["nivel"] in ("prioritario", "atencion"):
                en_riesgo.append(est)

        en_riesgo.sort(key=lambda e: e["puntaje"], reverse=True)

        return {
            "estudiantes": estudiantes,
            "cortes_inasistencia": cortes_inasistencia,
            "resumen_riesgo": resumen_conteos_riesgo(estudiantes),
            "en_riesgo": en_riesgo,
        }
    finally:
        cursor.close()
        conexion.close()


def obtener_dashboard_usuario(usuario, grupos, conexion=None):
    """Calcula los datos del dashboard principal para el profesor o director."""
    vacio = {
        "kpis": resumen_conteos_riesgo([]),
        "barras": [],
        "prioritarios": [],
    }
    ids_grupos = [g["id_grupo"] for g in grupos if "id_grupo" in g]
    if not ids_grupos:
        return vacio

    cerrar = conexion is None
    if cerrar:
        conexion = conectar()

    cursor = conexion.cursor(dictionary=True)
    try:
        placeholders = ", ".join(["%s"] * len(ids_grupos))
        cursor.execute(
            f"""
            SELECT
                g.id_grupo,
                g.nombre AS nombre_grupo,
                a.nombre AS asignatura,
                a.semestre,
                e.id_estudiante,
                e.cod_estudiante,
                e.nombre AS nombre_estudiante,
                c.corte_1 AS nota_1,
                c.corte_2 AS nota_2,
                c.corte_3 AS nota_3,
                i.corte_1 AS inas_1,
                i.corte_2 AS inas_2,
                i.corte_3 AS inas_3
            FROM grupo g
            JOIN asignatura a ON g.id_asignatura = a.id_asignatura
            JOIN estudiante e ON (
                EXISTS (SELECT 1 FROM calificacion c2 WHERE c2.id_grupo = g.id_grupo AND c2.id_estudiante = e.id_estudiante)
                OR EXISTS (SELECT 1 FROM inasistencia i2 WHERE i2.id_grupo = g.id_grupo AND i2.id_estudiante = e.id_estudiante)
                OR EXISTS (SELECT 1 FROM grupo_estudiante ge WHERE ge.id_grupo = g.id_grupo AND ge.id_estudiante = e.id_estudiante)
            )
            LEFT JOIN calificacion c ON c.id_grupo = g.id_grupo AND c.id_estudiante = e.id_estudiante
            LEFT JOIN inasistencia i ON i.id_grupo = g.id_grupo AND i.id_estudiante = e.id_estudiante
            WHERE g.id_grupo IN ({placeholders})
            """,
            tuple(ids_grupos)
        )
        filas = cursor.fetchall() or []
        registros = [r for r in filas if isinstance(r, dict)]

        _limpiar_cortes_no_evaluados(registros)

        por_estudiante = {}
        for reg in registros:
            riesgo = evaluar_riesgo_materia(
                reg.get("nota_1"), reg.get("nota_2"), reg.get("nota_3"),
                reg.get("inas_1"), reg.get("inas_2"), reg.get("inas_3"),
            )
            reg.update(riesgo)

            id_est = reg["id_estudiante"]
            if id_est not in por_estudiante:
                por_estudiante[id_est] = {
                    "id_estudiante": id_est,
                    "cod_estudiante": reg["cod_estudiante"],
                    "nombre": reg["nombre_estudiante"],
                    "materias": [],
                }
            por_estudiante[id_est]["materias"].append(reg)

        estudiantes_globales = []
        prioritarios = []
        for est in por_estudiante.values():
            est.update(evaluar_riesgo_global_estudiante(est["materias"]))
            estudiantes_globales.append(est)
            if est["nivel"] == "prioritario":
                prioritarios.append(est)

        prioritarios.sort(key=lambda e: e["puntaje"], reverse=True)

        barras = []
        if usuario.get("rol") == "profesor":
            for g in grupos:
                items = [r for r in registros if r["id_grupo"] == g["id_grupo"]]
                res = resumen_conteos_riesgo(items)
                res["etiqueta"] = f"{g['asignatura']} ({g['nombre_grupo']})"
                res["id_grupo"] = g["id_grupo"]
                barras.append(res)
        else:
            semestres = sorted({r["semestre"] for r in registros if r.get("semestre") is not None})
            for sem in semestres:
                items = [r for r in registros if r.get("semestre") == sem]
                res = resumen_conteos_riesgo(items)
                res["etiqueta"] = f"{sem}°"
                barras.append(res)

        return {
            "kpis": resumen_conteos_riesgo(estudiantes_globales),
            "barras": barras,
            "prioritarios": prioritarios,
        }
    finally:
        cursor.close()
        if cerrar:
            conexion.close()


def obtener_perfil_estudiante(id_estudiante):
    """Obtiene los datos de un estudiante y el detalle de riesgo en sus materias."""
    conexion = conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                e.id_estudiante,
                e.cod_estudiante,
                e.nombre,
                e.correo,
                p.nombre AS programa
            FROM estudiante e
            JOIN programa p ON e.id_programa = p.id_programa
            WHERE e.id_estudiante = %s
            """,
            (id_estudiante,)
        )
        estudiante = cursor.fetchone()
        if not isinstance(estudiante, dict):
            return None

        cursor.execute(
            """
            SELECT
                g.id_grupo,
                g.cod_grupo,
                g.nombre AS nombre_grupo,
                a.cod_asignatura,
                a.nombre AS asignatura,
                a.semestre,
                pe.nombre AS periodo,
                d.nombre AS docente,
                d.correo AS correo_docente,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c1 WHERE c1.id_grupo = g.id_grupo AND c1.corte_1 > 0) THEN c.corte_1 ELSE NULL END AS nota_1,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c2 WHERE c2.id_grupo = g.id_grupo AND c2.corte_2 > 0) THEN c.corte_2 ELSE NULL END AS nota_2,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c3 WHERE c3.id_grupo = g.id_grupo AND c3.corte_3 > 0) THEN c.corte_3 ELSE NULL END AS nota_3,
                i.corte_1 AS inas_1,
                i.corte_2 AS inas_2,
                i.corte_3 AS inas_3
            FROM grupo g
            JOIN asignatura a ON g.id_asignatura = a.id_asignatura
            JOIN periodo pe ON g.id_periodo = pe.id_periodo
            JOIN docente d ON g.id_docente = d.id_docente
            LEFT JOIN calificacion c
                ON c.id_grupo = g.id_grupo AND c.id_estudiante = %s
            LEFT JOIN inasistencia i
                ON i.id_grupo = g.id_grupo AND i.id_estudiante = %s
            LEFT JOIN grupo_estudiante ge
                ON ge.id_grupo = g.id_grupo AND ge.id_estudiante = %s
            WHERE c.id_calificacion IS NOT NULL
               OR i.id_inasistencia IS NOT NULL
               OR ge.id_grupo_estudiante IS NOT NULL
            ORDER BY pe.nombre DESC, a.semestre ASC, a.nombre ASC
            """,
            (id_estudiante, id_estudiante, id_estudiante)
        )
        filas = cursor.fetchall() or []
        materias = [m for m in filas if isinstance(m, dict)]

        for m in materias:
            riesgo = evaluar_riesgo_materia(
                m.get("nota_1"), m.get("nota_2"), m.get("nota_3"),
                m.get("inas_1"), m.get("inas_2"), m.get("inas_3"),
            )
            m.update(riesgo)

        return {
            "estudiante": estudiante,
            "materias": materias,
            "riesgo_global": evaluar_riesgo_global_estudiante(materias),
        }
    finally:
        cursor.close()
        conexion.close()
