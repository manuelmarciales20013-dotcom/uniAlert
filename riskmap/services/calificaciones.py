import pandas as pd
from ..database import conectar

CORTES = ("P1", "P2", "Exa")


def _a_flotante(valor):
    """Convierte un valor de celda a float o devuelve None si está vacío."""
    if pd.isna(valor):
        return None
    texto = str(valor).strip().replace(",", ".")
    return float(texto) if texto else None


def cargar_calificaciones_excel(archivo_excel, id_grupo):
    """Lee el Excel de calificaciones y actualiza los cortes activos en MySQL."""
    if hasattr(archivo_excel, "seek"):
        archivo_excel.seek(0)

    df = pd.read_excel(archivo_excel, dtype={"Código": str})
    if "Código" not in df.columns:
        raise ValueError("Al archivo le falta la columna 'Código'.")

    # Un corte está activo solo si existe en el archivo y tiene al menos una nota mayor a 0
    corte_activo = {}
    for c in CORTES:
        activo = False
        if c in df.columns:
            for _, fila in df.iterrows():
                if pd.isna(fila["Código"]):
                    continue
                try:
                    val = _a_flotante(fila[c])
                    if val is not None and val > 0:
                        activo = True
                        break
                except ValueError:
                    continue
        corte_activo[c] = activo

    conexion = conectar()
    cursor = conexion.cursor()
    nuevos = actualizados = 0
    exitosos, omitidos, errores = [], [], []

    try:
        for _, fila in df.iterrows():
            if pd.isna(fila["Código"]):
                continue

            codigo = str(fila["Código"]).strip().removesuffix(".0")
            if not codigo or codigo.lower().startswith("promedio"):
                continue

            nombre_est = str(fila["Estudiante"]).strip() if "Estudiante" in df.columns and not pd.isna(fila["Estudiante"]) else ""
            etiqueta = f"{codigo} · {nombre_est}" if nombre_est else codigo

            notas = {"P1": None, "P2": None, "Exa": None}
            error_nota = False

            for c in CORTES:
                if corte_activo[c]:
                    try:
                        val = _a_flotante(fila[c])
                        if val is not None:
                            val = round(val, 2)
                            if not (0.0 <= val <= 5.0):
                                errores.append(f"{etiqueta}: nota fuera de rango (0.0 a 5.0) en {c} ({val}).")
                                error_nota = True
                                break
                            notas[c] = val
                    except ValueError:
                        errores.append(f"{etiqueta}: formato de nota inválido en {c} ('{fila[c]}').")
                        error_nota = True
                        break

            if error_nota:
                continue

            cursor.execute("SELECT id_estudiante FROM estudiante WHERE cod_estudiante = %s", (codigo,))
            est_row = cursor.fetchone()
            if not est_row:
                omitidos.append(f"Estudiante no encontrado: {etiqueta}")
                continue

            id_estudiante = est_row[0]
            cursor.execute(
                "SELECT id_calificacion FROM calificacion WHERE id_estudiante = %s AND id_grupo = %s",
                (id_estudiante, id_grupo),
            )
            cal_row = cursor.fetchone()

            if cal_row:
                cursor.execute(
                    "UPDATE calificacion SET corte_1 = %s, corte_2 = %s, corte_3 = %s WHERE id_calificacion = %s",
                    (notas["P1"], notas["P2"], notas["Exa"], cal_row[0]),
                )
                actualizados += 1
            else:
                cursor.execute(
                    "INSERT INTO calificacion (id_estudiante, id_grupo, corte_1, corte_2, corte_3) VALUES (%s, %s, %s, %s, %s)",
                    (id_estudiante, id_grupo, notas["P1"], notas["P2"], notas["Exa"]),
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

            resumen_notas = ", ".join(f"{c}: {notas[c]:.2f}" for c in CORTES if notas[c] is not None) or "sin notas activas"
            exitosos.append(f"{etiqueta} ({resumen_notas})")

        conexion.commit()
        return {
            "cortes_activos": [c for c in CORTES if corte_activo[c]],
            "nuevos": nuevos,
            "actualizados": actualizados,
            "exitosos": exitosos,
            "omitidos": omitidos,
            "errores": errores,
        }
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()
