import openpyxl
import pandas as pd
from ..database import conectar

# Relación entre el corte seleccionado, la columna de MySQL y los cortes anteriores
CORTES = {
    "P1": ("corte_1", []),
    "P2": ("corte_2", ["corte_1"]),
    "Exa": ("corte_3", ["corte_1", "corte_2"])
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
        asignatura = partes[1].strip()
        grupo = partes[2].replace("Grupo", "").replace("grupo", "").strip()
        return {"titulo": titulo, "asignatura": asignatura, "grupo": grupo}

    return {"titulo": titulo, "asignatura": "", "grupo": ""}


def comparar_grupo_excel(info_excel, grupo_bd):
    """Compara la asignatura y el grupo del Excel con el grupo seleccionado en pantalla."""
    asig_excel = info_excel.get("asignatura", "").lower().strip()
    grupo_excel = info_excel.get("grupo", "").lower().strip().lstrip("0")

    if not asig_excel and not grupo_excel:
        return None

    asig_bd = str(grupo_bd.get("asignatura", "")).lower().strip()
    cod_grupo = str(grupo_bd.get("cod_grupo", "")).lower().strip()
    nom_grupo = str(grupo_bd.get("nombre_grupo", "")).lower().strip()

    coincide_asig = True
    if asig_excel and asig_bd:
        coincide_asig = (asig_excel in asig_bd) or (asig_bd in asig_excel)

    coincide_grupo = True
    if grupo_excel:
        coincide_grupo = (grupo_excel in cod_grupo) or (grupo_excel in nom_grupo)

    if not coincide_asig or not coincide_grupo:
        return (
            f"El archivo indica «{info_excel.get('titulo')}», pero estás cargando en "
            f"«{grupo_bd.get('asignatura')} - {grupo_bd.get('nombre_grupo')} ({grupo_bd.get('cod_grupo')})»."
        )
    return None


def corte_inasistencia_ocupado(id_grupo, corte_actual):
    """Revisa si el corte elegido ya tiene inasistencias guardadas en este grupo."""
    columna_sql, _ = CORTES[corte_actual]
    conexion = conectar()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            f"""
            SELECT COUNT({columna_sql})
            FROM inasistencia
            WHERE id_grupo = %s
            """,
            (id_grupo,)
        )
        cantidad = cursor.fetchone()[0]
        return cantidad > 0
    finally:
        cursor.close()
        conexion.close()


def cargar_inasistencias_excel(archivo_excel, id_grupo, corte_actual):
    # Validar el corte seleccionado
    if corte_actual not in CORTES:
        raise ValueError("Corte inválido. Selecciona P1, P2 o Exa.")

    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    # Leer el archivo Excel de inasistencias
    df = pd.read_excel(archivo_excel, header=2, dtype=str)

    columna_sql, cortes_anteriores = CORTES[corte_actual]

    conexion = conectar()
    cursor = conexion.cursor()

    nuevos = 0
    actualizados = 0
    omitidos = []
    errores = []

    try:
        for _, fila in df.iterrows():

            # Extraer el código del estudiante
            if pd.isna(fila["Código"]):
                continue

            codigo = str(fila["Código"]).strip()
            if codigo.endswith(".0"):
                codigo = codigo[:-2]

            if not codigo or codigo.lower().startswith("promedio"):
                continue

            # Extraer el total acumulado de inasistencias
            if pd.isna(fila["Total"]):
                errores.append(f"Estudiante {codigo}: total vacío.")
                continue

            total_excel = float(fila["Total"])
            if total_excel < 0 or not total_excel.is_integer():
                errores.append(f"Estudiante {codigo}: total inválido.")
                continue

            total_excel = int(total_excel)

            # 1. Buscar al estudiante por su código
            cursor.execute(
                """
                SELECT id_estudiante
                FROM estudiante
                WHERE cod_estudiante = %s
                """,
                (codigo,)
            )
            resultado = cursor.fetchone()

            if not resultado:
                omitidos.append(f"Estudiante no encontrado: {codigo}")
                continue

            id_estudiante = resultado[0]

            # 2. Buscar el registro de inasistencias del estudiante para el grupo seleccionado
            cursor.execute(
                """
                SELECT id_inasistencia, corte_1, corte_2, corte_3
                FROM inasistencia
                WHERE id_estudiante = %s
                  AND id_grupo = %s
                """,
                (id_estudiante, id_grupo)
            )
            resultado = cursor.fetchone()

            if resultado:
                id_inasistencia = resultado[0]
                inasistencias = {
                    "corte_1": resultado[1],
                    "corte_2": resultado[2],
                    "corte_3": resultado[3]
                }

                # 3. Calcular el acumulado de los cortes anteriores
                total_anterior = sum(
                    inasistencias[columna] or 0
                    for columna in cortes_anteriores
                )

                # 4. Calcular las inasistencias del corte actual
                inasistencias_actuales = total_excel - int(total_anterior)

                if inasistencias_actuales < 0:
                    errores.append(
                        f"Error para {codigo}: el total acumulado ({total_excel}) "
                        f"es menor que el registrado anteriormente ({int(total_anterior)})."
                    )
                    continue

                # 5. Actualizar el corte actual y limpiar cortes posteriores para que este sea el último corte cargado
                if columna_sql == "corte_1":
                    consulta_update = """
                        UPDATE inasistencia
                        SET corte_1 = %s, corte_2 = NULL, corte_3 = NULL
                        WHERE id_inasistencia = %s
                    """
                elif columna_sql == "corte_2":
                    consulta_update = """
                        UPDATE inasistencia
                        SET corte_2 = %s, corte_3 = NULL
                        WHERE id_inasistencia = %s
                    """
                else:
                    consulta_update = """
                        UPDATE inasistencia
                        SET corte_3 = %s
                        WHERE id_inasistencia = %s
                    """
                cursor.execute(
                    consulta_update,
                    (inasistencias_actuales, id_inasistencia)
                )
                actualizados += 1

            else:
                # Solo podemos crear el registro desde P1,
                # porque los demás cortes necesitan el acumulado anterior
                if cortes_anteriores:
                    errores.append(
                        f"Estudiante {codigo}: no existe un registro previo para calcular {corte_actual}."
                    )
                    continue

                # 6. Insertar el registro inicial de inasistencias
                cursor.execute(
                    """
                    INSERT INTO inasistencia
                        (id_estudiante, id_grupo, corte_1)
                    VALUES (%s, %s, %s)
                    """,
                    (id_estudiante, id_grupo, total_excel)
                )
                nuevos += 1

            # Registrar al estudiante en el grupo si aún no está asociado
            cursor.execute(
                """
                SELECT id_grupo_estudiante
                FROM grupo_estudiante
                WHERE id_grupo = %s AND id_estudiante = %s
                """,
                (id_grupo, id_estudiante)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO grupo_estudiante (id_grupo, id_estudiante) VALUES (%s, %s)",
                    (id_grupo, id_estudiante)
                )

        # Confirmar los cambios
        conexion.commit()

        return {
            "corte": corte_actual,
            "nuevos": nuevos,
            "actualizados": actualizados,
            "omitidos": omitidos,
            "errores": errores,
        }

    except Exception as e:
        conexion.rollback()
        print("Error durante la carga:", e)
        raise

    finally:
        cursor.close()
        conexion.close()
