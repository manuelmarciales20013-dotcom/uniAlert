"""Importa estudiantes desde un archivo Excel a la base uni_alert."""

import pandas as pd

from ..database import conectar


def importar_estudiantes(archivo, id_programa=1):
    """Lee un Excel y registra los estudiantes nuevos en el programa indicado."""
    df = pd.read_excel(archivo)
    columnas = ("Código", "Estudiante", "Correo")
    faltantes = [col for col in columnas if col not in df.columns]
    if faltantes:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(faltantes))
    if df.empty:
        raise ValueError("El archivo no contiene estudiantes.")

    conexion = conectar()
    cursor = None
    nuevos = 0
    existentes = 0
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT id_programa FROM programa WHERE id_programa = %s", (id_programa,))
        if cursor.fetchone() is None:
            raise ValueError(f"No existe el programa con ID {id_programa}.")

        for numero_fila, fila in df.iterrows():
            if any(pd.isna(fila[col]) for col in columnas):
                raise ValueError(f"Hay datos vacíos en la fila {numero_fila + 2}.")

            codigo = str(fila["Código"]).strip().removesuffix(".0")
            nombre = str(fila["Estudiante"]).strip()
            correo = str(fila["Correo"]).strip()
            if not codigo or not nombre or not correo:
                raise ValueError(f"Hay datos incompletos en la fila {numero_fila + 2}.")

            cursor.execute("SELECT id_estudiante FROM estudiante WHERE cod_estudiante = %s", (codigo,))
            if cursor.fetchone():
                existentes += 1
                continue

            cursor.execute(
                "INSERT INTO estudiante (cod_estudiante, id_programa, nombre, correo) VALUES (%s, %s, %s, %s)",
                (codigo, id_programa, nombre, correo),
            )
            nuevos += 1

        conexion.commit()
        return {"procesados": len(df), "nuevos": nuevos, "existentes": existentes}
    except Exception:
        conexion.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conexion.close()
