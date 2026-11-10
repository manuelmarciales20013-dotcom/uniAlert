"""Conversión de reportes PDF a formato Excel (.xlsx) en memoria."""

import io
import re
from statistics import median

import pdfplumber
from openpyxl import Workbook

DIAS = {"Lu", "Ma", "Mi", "Ju", "Vi", "Sa", "Do"}

MAPA_COLUMNAS = {
    "codigo": "Código", "código": "Código", "cod": "Código",
    "estudiante": "Estudiante", "nombre": "Estudiante", "nombres": "Estudiante",
    "correo": "Correo", "email": "Correo",
    "p1": "P1", "corte 1": "P1", "corte_1": "P1",
    "p2": "P2", "corte 2": "P2", "corte_2": "P2",
    "exa": "Exa", "examen": "Exa", "corte 3": "Exa", "corte_3": "Exa", "final": "Exa",
}


def centro(w):
    return (w["x0"] + w["x1"]) / 2


def misma_fila(w, words, tol=3):
    return [v for v in words if abs(v["top"] - w["top"]) < tol]


def texto_tras(words, etiqueta, max_gap=25):
    """Extrae el texto que sigue a una etiqueta en la misma línea (ej. 'GRUPO:')."""
    for w in words:
        if w["text"].startswith(etiqueta):
            partes = [w["text"][len(etiqueta):]]
            fila = sorted(
                (v for v in misma_fila(w, words, 2) if v["x0"] >= w["x1"] - 0.5),
                key=lambda v: v["x0"],
            )
            anterior = w["x1"]
            for v in fila:
                if v["x0"] - anterior > max_gap:
                    break
                partes.append(v["text"])
                anterior = v["x1"]
            return " ".join(p for p in partes if p)
    return ""


def leer_encabezado(words):
    """Devuelve las columnas de día del reporte: [(semana, dia, x_centro), ...]."""
    codigo = next((w for w in words if w["text"] == "CODIGO"), None)
    semana = next((w for w in words if w["text"] == "SEMANA"), None)
    if not codigo or not semana:
        return None

    dias = sorted(
        (w for w in words if w["text"] in DIAS and abs(w["top"] - codigo["top"]) < 4),
        key=lambda w: w["x0"],
    )
    semanas = [
        w for w in words
        if re.fullmatch(r"\d{1,2}", w["text"])
        and abs(w["top"] - semana["top"]) < 4
        and w["x0"] > semana["x1"]
    ]
    if not dias or not semanas:
        return None

    return [
        (int(min(semanas, key=lambda s: abs(centro(s) - centro(d)))["text"]), d["text"], centro(d))
        for d in dias
    ]


def leer_pagina(words, columnas):
    nombre_hdr = next(w for w in words if w["text"] == "NOMBRE")
    xs = [c[2] for c in columnas]
    ancho = median(b - a for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 26
    x_ultimo = xs[-1]

    codigos = [
        w for w in words
        if re.fullmatch(r"\d{9,12}", w["text"]) and w["x1"] < nombre_hdr["x0"]
    ]
    filas = []
    for cod in sorted(codigos, key=lambda w: w["top"]):
        fila = misma_fila(cod, words)
        nombre = " ".join(
            w["text"]
            for w in sorted(fila, key=lambda w: w["x0"])
            if w["x0"] > cod["x1"] and not re.fullmatch(r"\d+", w["text"]) and not w["text"].endswith("%")
        )

        marcas = {}
        total = None
        pct = None
        for w in fila:
            t = w["text"]
            if t.endswith("%"):
                pct = float(t[:-1].replace(",", ".")) / 100
            elif re.fullmatch(r"\d+", t) and w is not cod:
                if centro(w) > x_ultimo + ancho * 0.7:
                    total = int(t)
                elif centro(w) > xs[0] - ancho * 0.7:
                    i = min(range(len(xs)), key=lambda k: abs(xs[k] - centro(w)))
                    marcas[i] = marcas.get(i, 0) + int(t)

        filas.append({
            "codigo": cod["text"],
            "nombre": nombre,
            "marcas": marcas,
            "total_pdf": total,
            "pct_pdf": pct,
        })
    return filas


def _abrir_stream_pdf(origen_pdf):
    if hasattr(origen_pdf, "read"):
        datos = origen_pdf.read()
        if hasattr(origen_pdf, "seek"):
            origen_pdf.seek(0)
        return io.BytesIO(datos)
    return origen_pdf


def leer_pdf(origen_pdf):
    """Lee el PDF de diagnóstico de asistencia y extrae metadatos, columnas y estudiantes."""
    info = {"asignatura": "", "grupo": "", "promedio": None}
    columnas = None
    estudiantes = []

    with pdfplumber.open(_abrir_stream_pdf(origen_pdf)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not info["asignatura"]:
                info["asignatura"] = texto_tras(words, "ASIGNATURA:")
                info["grupo"] = texto_tras(words, "GRUPO:")

            col_pagina = leer_encabezado(words)
            if col_pagina:
                if columnas is None:
                    columnas = col_pagina
                estudiantes += leer_pagina(words, col_pagina)

    if columnas is None:
        raise ValueError("No se encontró la tabla de asistencia en el archivo PDF.")
    return info, columnas, estudiantes


def escribir_excel(info, columnas, estudiantes, salida):
    """Escribe la estructura del Excel de inasistencia en el destino indicado."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Inasistencia"

    ws["A1"] = f"Inasistencia - {info['asignatura']} - Grupo {info['grupo']}"

    c0 = 3
    n = len(columnas)
    c_tot, c_pct = c0 + n, c0 + n + 1

    # Fila 3 y 4: encabezados que lee pandas (header=2 corresponde a la fila 3)
    ws.cell(3, 1, "Código")
    ws.cell(3, 2, "Nombre")
    for k, (semana, dia, _) in enumerate(columnas):
        ws.cell(3, c0 + k, f"Semana {semana}")
        ws.cell(4, c0 + k, dia)
    ws.cell(3, c_tot, "Total")
    ws.cell(3, c_pct, "%")

    # Filas de estudiantes a partir de la fila 5
    for k, est in enumerate(estudiantes, start=5):
        ws.cell(k, 1, est["codigo"])
        ws.cell(k, 2, est["nombre"])
        for idx, horas in est["marcas"].items():
            ws.cell(k, c0 + idx, horas)

        suma = sum(est["marcas"].values())
        total_valor = suma if est["marcas"] else (est["total_pdf"] or 0)
        ws.cell(k, c_tot, total_valor)
        ws.cell(k, c_pct, est["pct_pdf"])

    wb.save(salida)


def convertir_pdf_a_excel_bytes(archivo_pdf):
    """Convierte un PDF de inasistencia en un archivo Excel (.xlsx) en memoria."""
    info, columnas, estudiantes = leer_pdf(archivo_pdf)
    buffer_excel = io.BytesIO()
    escribir_excel(info, columnas, estudiantes, buffer_excel)
    buffer_excel.seek(0)
    return buffer_excel


def _normalizar_columna(celda):
    if celda is None:
        return ""
    limpio = re.sub(r"\s+", " ", str(celda)).strip()
    return MAPA_COLUMNAS.get(limpio.lower(), limpio)


def convertir_pdf_tabla_a_excel_bytes(origen_pdf):
    """Extrae tablas de un PDF (calificaciones o estudiantes) y devuelve un .xlsx en memoria."""
    encabezados = None
    filas = []

    with pdfplumber.open(_abrir_stream_pdf(origen_pdf)) as pdf:
        for page in pdf.pages:
            for tabla in page.extract_tables() or []:
                for fila in tabla:
                    if not fila or not any(c and str(c).strip() for c in fila):
                        continue
                    norm = [_normalizar_columna(c) for c in fila]
                    if encabezados is None and "Código" in norm:
                        encabezados = norm
                    elif encabezados is not None and norm != encabezados:
                        filas.append([str(c).strip() if c is not None else "" for c in fila])

            if encabezados is None:
                lineas = []
                for w in sorted(page.extract_words(), key=lambda x: (x["top"], x["x0"])):
                    if not lineas or abs(w["top"] - lineas[-1][0]["top"]) > 3:
                        lineas.append([w])
                    else:
                        lineas[-1].append(w)

                xs_cols = None
                for linea in lineas:
                    textos = [_normalizar_columna(w["text"]) for w in linea]
                    if "Código" in textos:
                        encabezados = textos
                        xs_cols = [centro(w) for w in linea]
                    elif xs_cols is not None:
                        celdas = [""] * len(xs_cols)
                        for w in sorted(linea, key=lambda x: x["x0"]):
                            idx = min(range(len(xs_cols)), key=lambda k: abs(xs_cols[k] - centro(w)))
                            celdas[idx] = f"{celdas[idx]} {w['text']}".strip()
                        if any(celdas):
                            filas.append(celdas)

    if not encabezados or not filas:
        raise ValueError("No se encontró una tabla válida con la columna 'Código' en el PDF.")

    wb = Workbook()
    ws = wb.active
    ws.append(encabezados)
    for fila in filas:
        ws.append(fila)

    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    return salida
