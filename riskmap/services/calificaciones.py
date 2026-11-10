import pandas as pd
from ..database import conectar


def cargar_calificaciones_excel(archivo_excel, id_grupo):
    # Leer el archivo Excel
    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    df = pd.read_excel(archivo_excel, dtype={"Código": str})

    if "Código" not in df.columns:
        raise ValueError("Al archivo le falta la columna 'Código'.")

    # Revisar qué cortes tienen notas mayores a 0.
    # Si toda la columna de un corte es 0 (o no existe), se guardará como NULL.
    cortes = ["P1", "P2", "Exa"]
    corte_activo = {"P1": False, "P2": False, "Exa": False}

    for corte in cortes:
        if corte in df.columns:
            for _, fila in df.iterrows():
                if pd.isna(fila["Código"]) or pd.isna(fila[corte]):
                    continue
                texto_nota = str(fila[corte]).strip().replace(",", ".")
                if texto_nota == "":
                    continue
                if float(texto_nota) > 0:
                    corte_activo[corte] = True
                    break

    conexion = conectar()
    cursor = conexion.cursor()

    nuevos = 0
    actualizados = 0
    omitidos = []
    errores = []

    try:
        for _, fila in df.iterrows():

            # Validar código del estudiante
            if pd.isna(fila["Código"]):
                continue

            codigo = str(fila["Código"]).strip()
            if codigo.endswith(".0"):
                codigo = codigo[:-2]

            if not codigo or codigo.lower().startswith("promedio"):
                continue

            # Extraer la nota de cada corte (o dejarla en None si el corte completo es 0)
            notas = {"P1": None, "P2": None, "Exa": None}

            for corte in cortes:
                if corte_activo[corte] and not pd.isna(fila[corte]):
                    texto = str(fila[corte]).strip().replace(",", ".")
                    if texto != "":
                        notas[corte] = round(float(texto), 2)

            # 1. Buscar al estudiante por su código institucional
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

            # 2. Verificar si ya existe una calificación para este estudiante en este grupo
            cursor.execute(
                """
                SELECT id_calificacion
                FROM calificacion
                WHERE id_estudiante = %s
                  AND id_grupo = %s
                """,
                (id_estudiante, id_grupo)
            )
            resultado_calificacion = cursor.fetchone()

            if resultado_calificacion:
                # 3. Si existe, actualizar los cortes
                id_calificacion = resultado_calificacion[0]

                cursor.execute(
                    """
                    UPDATE calificacion
                    SET corte_1 = %s, corte_2 = %s, corte_3 = %s
                    WHERE id_calificacion = %s
                    """,
                    (notas["P1"], notas["P2"], notas["Exa"], id_calificacion)
                )
                actualizados += 1

            else:
                # 4. Si no existe, insertar la calificación (los cortes no evaluados quedan en NULL)
                cursor.execute(
                    """
                    INSERT INTO calificacion
                        (id_estudiante, id_grupo, corte_1, corte_2, corte_3)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (id_estudiante, id_grupo, notas["P1"], notas["P2"], notas["Exa"])
                )
                nuevos += 1

            # 5. Registrar al estudiante en el grupo si aún no está asociado
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

        # Confirmar todos los cambios
        conexion.commit()

        cortes_cargados = [c for c in cortes if corte_activo[c]]
        return {
            "cortes_activos": cortes_cargados,
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
