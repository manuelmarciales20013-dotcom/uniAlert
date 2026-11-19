"""Consultas de grupos, dashboards de riesgo y perfil individual del estudiante."""

from ..database import conectar
from .riesgo import (
    evaluar_riesgo_global_estudiante,
    evaluar_riesgo_materia,
    resumen_conteos_riesgo,
)

SQL_GRUPOS = """
    SELECT
        g.id_grupo, g.cod_grupo, g.nombre AS nombre_grupo,
        a.cod_asignatura, a.nombre AS asignatura, a.semestre,
        p.id_programa, p.nombre AS programa,
        pe.nombre AS periodo,
        d.nombre AS docente, d.correo AS correo_docente
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
        por_grupo.setdefault(r.get("id_grupo"), []).append(r)

    for filas in por_grupo.values():
        for col in ("nota_1", "nota_2", "nota_3"):
            if not any(f.get(col) is not None and float(f[col]) > 0 for f in filas):
                for f in filas:
                    f[col] = None


def listar_grupos_usuario(usuario, conexion=None):
    """Lista los grupos del profesor o todos los grupos para el director."""
    cerrar = conexion is None
    conexion = conexion or conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        rol = usuario.get("rol")
        if rol == "profesor":
            correo = (usuario.get("correo") or "").strip().lower()
            cursor.execute(SQL_GRUPOS + " WHERE LOWER(d.correo) = %s ORDER BY pe.nombre DESC, a.nombre ASC", (correo,))
        elif rol == "director_programa" and usuario.get("id_programa"):
            cursor.execute(
                SQL_GRUPOS + " WHERE p.id_programa = %s ORDER BY pe.nombre DESC, a.semestre ASC, a.nombre ASC",
                (usuario["id_programa"],),
            )
        else:
            cursor.execute(SQL_GRUPOS + " ORDER BY pe.nombre DESC, p.nombre ASC, a.semestre ASC, a.nombre ASC")
        return [f for f in (cursor.fetchall() or []) if isinstance(f, dict)]
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
    correo_u = (usuario.get("correo") or "").strip().lower()
    correo_d = (grupo.get("correo_docente") or "").strip().lower()
    return bool(correo_u and correo_u == correo_d)


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
                %s AS id_grupo, e.id_estudiante, e.cod_estudiante, e.nombre, e.correo,
                c.corte_1 AS nota_1, c.corte_2 AS nota_2, c.corte_3 AS nota_3,
                i.corte_1 AS inas_1, i.corte_2 AS inas_2, i.corte_3 AS inas_3
            FROM estudiante e
            LEFT JOIN calificacion c ON c.id_estudiante = e.id_estudiante AND c.id_grupo = %s
            LEFT JOIN inasistencia i ON i.id_estudiante = e.id_estudiante AND i.id_grupo = %s
            LEFT JOIN grupo_estudiante ge ON ge.id_estudiante = e.id_estudiante AND ge.id_grupo = %s
            WHERE c.id_calificacion IS NOT NULL OR i.id_inasistencia IS NOT NULL OR ge.id_grupo_estudiante IS NOT NULL
            ORDER BY e.nombre ASC
            """,
            (id_grupo, id_grupo, id_grupo, id_grupo),
        )
        estudiantes = [f for f in (cursor.fetchall() or []) if isinstance(f, dict)]
        _limpiar_cortes_no_evaluados(estudiantes)

        cortes_inasistencia = {
            "P1": any(e.get("inas_1") is not None for e in estudiantes),
            "P2": any(e.get("inas_2") is not None for e in estudiantes),
            "Exa": any(e.get("inas_3") is not None for e in estudiantes),
        }

        for est in estudiantes:
            est.update(evaluar_riesgo_materia(
                est.get("nota_1"), est.get("nota_2"), est.get("nota_3"),
                est.get("inas_1"), est.get("inas_2"), est.get("inas_3"),
            ))

        en_riesgo = sorted(
            [e for e in estudiantes if e["nivel"] in ("prioritario", "atencion")],
            key=lambda e: e["puntaje"],
            reverse=True,
        )
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
    ids_grupos = [g["id_grupo"] for g in grupos if "id_grupo" in g]
    if not ids_grupos:
        return {"kpis": resumen_conteos_riesgo([]), "barras": [], "prioritarios": []}

    cerrar = conexion is None
    conexion = conexion or conectar()
    cursor = conexion.cursor(dictionary=True)
    try:
        placeholders = ", ".join(["%s"] * len(ids_grupos))
        cursor.execute(
            f"""
            SELECT
                g.id_grupo, g.nombre AS nombre_grupo, a.nombre AS asignatura, a.semestre,
                e.id_estudiante, e.cod_estudiante, e.nombre AS nombre_estudiante,
                c.corte_1 AS nota_1, c.corte_2 AS nota_2, c.corte_3 AS nota_3,
                i.corte_1 AS inas_1, i.corte_2 AS inas_2, i.corte_3 AS inas_3
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
            tuple(ids_grupos),
        )
        registros = [r for r in (cursor.fetchall() or []) if isinstance(r, dict)]
        _limpiar_cortes_no_evaluados(registros)

        por_estudiante = {}
        for reg in registros:
            reg.update(evaluar_riesgo_materia(
                reg.get("nota_1"), reg.get("nota_2"), reg.get("nota_3"),
                reg.get("inas_1"), reg.get("inas_2"), reg.get("inas_3"),
            ))
            est = por_estudiante.setdefault(reg["id_estudiante"], {
                "id_estudiante": reg["id_estudiante"],
                "cod_estudiante": reg["cod_estudiante"],
                "nombre": reg["nombre_estudiante"],
                "materias": [],
            })
            est["materias"].append(reg)

        estudiantes_globales = []
        for est in por_estudiante.values():
            est.update(evaluar_riesgo_global_estudiante(est["materias"]))
            materias_alerta = [
                m["asignatura"] for m in est["materias"]
                if m.get("nivel") in ("prioritario", "atencion") and m.get("asignatura")
            ]
            est["materias_en_riesgo"] = ", ".join(materias_alerta)
            estudiantes_globales.append(est)

        prioritarios = sorted(
            [e for e in estudiantes_globales if e["nivel"] == "prioritario"],
            key=lambda e: e["puntaje"],
            reverse=True,
        )

        barras = []
        for g in grupos:
            res = resumen_conteos_riesgo([r for r in registros if r["id_grupo"] == g["id_grupo"]])
            res.update({"etiqueta": f"{g['asignatura']} ({g['nombre_grupo']})", "id_grupo": g["id_grupo"]})
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
            SELECT e.id_estudiante, e.cod_estudiante, e.nombre, e.correo, p.nombre AS programa
            FROM estudiante e
            JOIN programa p ON e.id_programa = p.id_programa
            WHERE e.id_estudiante = %s
            """,
            (id_estudiante,),
        )
        estudiante = cursor.fetchone()
        if not isinstance(estudiante, dict):
            return None

        cursor.execute(
            """
            SELECT
                g.id_grupo, g.cod_grupo, g.nombre AS nombre_grupo,
                a.cod_asignatura, a.nombre AS asignatura, a.semestre,
                pe.nombre AS periodo, d.nombre AS docente, d.correo AS correo_docente,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c1 WHERE c1.id_grupo = g.id_grupo AND c1.corte_1 > 0) THEN c.corte_1 ELSE NULL END AS nota_1,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c2 WHERE c2.id_grupo = g.id_grupo AND c2.corte_2 > 0) THEN c.corte_2 ELSE NULL END AS nota_2,
                CASE WHEN EXISTS (SELECT 1 FROM calificacion c3 WHERE c3.id_grupo = g.id_grupo AND c3.corte_3 > 0) THEN c.corte_3 ELSE NULL END AS nota_3,
                i.corte_1 AS inas_1, i.corte_2 AS inas_2, i.corte_3 AS inas_3
            FROM grupo g
            JOIN asignatura a ON g.id_asignatura = a.id_asignatura
            JOIN periodo pe ON g.id_periodo = pe.id_periodo
            JOIN docente d ON g.id_docente = d.id_docente
            LEFT JOIN calificacion c ON c.id_grupo = g.id_grupo AND c.id_estudiante = %s
            LEFT JOIN inasistencia i ON i.id_grupo = g.id_grupo AND i.id_estudiante = %s
            LEFT JOIN grupo_estudiante ge ON ge.id_grupo = g.id_grupo AND ge.id_estudiante = %s
            WHERE c.id_calificacion IS NOT NULL OR i.id_inasistencia IS NOT NULL OR ge.id_grupo_estudiante IS NOT NULL
            ORDER BY pe.nombre DESC, a.semestre ASC, a.nombre ASC
            """,
            (id_estudiante, id_estudiante, id_estudiante),
        )
        materias = [m for m in (cursor.fetchall() or []) if isinstance(m, dict)]
        for m in materias:
            m.update(evaluar_riesgo_materia(
                m.get("nota_1"), m.get("nota_2"), m.get("nota_3"),
                m.get("inas_1"), m.get("inas_2"), m.get("inas_3"),
            ))

        return {
            "estudiante": estudiante,
            "materias": materias,
            "riesgo_global": evaluar_riesgo_global_estudiante(materias),
        }
    finally:
        cursor.close()
        conexion.close()
