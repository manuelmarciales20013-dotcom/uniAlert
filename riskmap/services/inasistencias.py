import openpyxl
import pandas as pd
from ..database import conectar

CORTES = {
    "P1": ("corte_1", [], "SET corte_1 = %s, corte_2 = NULL, corte_3 = NULL"),
    "P2": ("corte_2", ["corte_1"], "SET corte_2 = %s, corte_3 = NULL"),
    "Exa": ("corte_3", ["corte_1", "corte_2"], "SET corte_3 = %s"),
}


def leer_titulo_excel(archivo_excel):
    """Lee la celda A1 del Excel ('Inasistencia - <asignatura> - Grupo <grupo>')."""
    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    wb = openpyxl.load_workbook(archivo_excel, read_only=True, data_only=True)
    titulo = str(wb.active["A1"].value or "").strip()
    wb.close()

    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    partes = titulo.split(" - ")
    if len(partes) >= 3:
        grupo = partes[2].replace("Grupo", "").replace("grupo", "").strip()
        return {"titulo": titulo, "asignatura": partes[1].strip(), "grupo": grupo}
    return {"titulo": titulo, "asignatura": "", "grupo": ""}


def comparar_grupo_excel(info_excel, grupo_bd):
    """Compara la asignatura y el grupo del Excel con el grupo seleccionado."""
    asig_excel = info_excel.get("asignatura", "").lower().strip()
    grupo_excel = info_excel.get("grupo", "").lower().strip().lstrip("0")
    if not asig_excel and not grupo_excel:
        return None

    asig_bd = str(grupo_bd.get("asignatura", "")).lower().strip()
    cod_grupo = str(grupo_bd.get("cod_grupo", "")).lower().strip()
    nom_grupo = str(grupo_bd.get("nombre_grupo", "")).lower().strip()

    coincide_asig = not (asig_excel and asig_bd) or (asig_excel in asig_bd) or (asig_bd in asig_excel)
    coincide_grupo = not grupo_excel or (grupo_excel in cod_grupo) or (grupo_excel in nom_grupo)

    if not coincide_asig or not coincide_grupo:
        return (
            f"El archivo indica «{info_excel.get('titulo')}», pero estás cargando en "
            f"«{grupo_bd.get('asignatura')} - {grupo_bd.get('nombre_grupo')} ({grupo_bd.get('cod_grupo')})»."
        )
    return None


def corte_inasistencia_ocupado(id_grupo, corte_actual):
    """Revisa si el corte elegido ya tiene inasistencias guardadas en este grupo."""
    columna_sql = CORTES[corte_actual][0]
    conexion = conectar()
    cursor = conexion.cursor()
    try:
        cursor.execute(f"SELECT COUNT({columna_sql}) FROM inasistencia WHERE id_grupo = %s", (id_grupo,))
        return cursor.fetchone()[0] > 0
    finally:
        cursor.close()
        conexion.close()


def cargar_inasistencias_excel(archivo_excel, id_grupo, corte_actual):
    """Carga las inasistencias del corte indicado restando el acumulado de cortes previos."""
    if corte_actual not in CORTES:
        raise ValueError("Corte inválido. Selecciona P1, P2 o Exa.")

    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    df = pd.read_excel(archivo_excel, header=2, dtype=str)
    _, cortes_anteriores, clausula_set = CORTES[corte_actual]

    conexion = conectar()
    cursor = conexion.cursor()
    nuevos = actualizados = 0
    omitidos, errores = [], []

    try:
        for _, fila in df.iterrows():
            if pd.isna(fila["Código"]):
                continue

            codigo = str(fila["Código"]).strip().removesuffix(".0")
            if not codigo or codigo.lower().startswith("promedio"):
                continue

            if pd.isna(fila["Total"]):
                errores.append(f"Estudiante {codigo}: total vacío.")
                continue

            total_excel = float(fila["Total"])
            if total_excel < 0 or not total_excel.is_integer():
                errores.append(f"Estudiante {codigo}: total inválido.")
                continue
            total_excel = int(total_excel)

            cursor.execute("SELECT id_estudiante FROM estudiante WHERE cod_estudiante = %s", (codigo,))
            est_row = cursor.fetchone()
            if not est_row:
                omitidos.append(f"Estudiante no encontrado: {codigo}")
                continue

            id_estudiante = est_row[0]
            cursor.execute(
                "SELECT id_inasistencia, corte_1, corte_2, corte_3 FROM inasistencia WHERE id_estudiante = %s AND id_grupo = %s",
                (id_estudiante, id_grupo),
            )
            inas_row = cursor.fetchone()

            if inas_row:
                previos = {"corte_1": inas_row[1], "corte_2": inas_row[2], "corte_3": inas_row[3]}
                total_anterior = int(sum(previos[col] or 0 for col in cortes_anteriores))
                inas_actuales = total_excel - total_anterior

                if inas_actuales < 0:
                    errores.append(
                        f"Error para {codigo}: el total acumulado ({total_excel}) "
                        f"es menor que el registrado anteriormente ({total_anterior})."
                    )
                    continue

                cursor.execute(f"UPDATE inasistencia {clausula_set} WHERE id_inasistencia = %s", (inas_actuales, inas_row[0]))
                actualizados += 1
            else:
                if cortes_anteriores:
                    errores.append(f"Estudiante {codigo}: no existe un registro previo para calcular {corte_actual}.")
                    continue

                cursor.execute(
                    "INSERT INTO inasistencia (id_estudiante, id_grupo, corte_1) VALUES (%s, %s, %s)",
                    (id_estudiante, id_grupo, total_excel),
                )
                nuevos += 1

            cursor.execute(
                "SELECT id_grupo_estudiante FROM grupo_estudiante WHERE id_grupo = %s AND id_estudiante = %s",
                (id_grupo, id_estudiante),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO grupo_estudiante (id_grupo, id_estudiante) VALUES (%s, %s)",
                    (id_grupo, id_estudiante),
                )

        conexion.commit()
        return {
            "corte": corte_actual,
            "nuevos": nuevos,
            "actualizados": actualizados,
            "omitidos": omitidos,
            "errores": errores,
        }
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()
