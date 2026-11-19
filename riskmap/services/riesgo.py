"""Cálculo de riesgo académico por materia y global."""


def clasificar_puntaje(puntos):
    """Limita el puntaje entre 0 y 100 y devuelve (puntaje, nivel, etiqueta)."""
    puntos = max(0, min(100, puntos))
    if puntos >= 60:
        return puntos, "prioritario", "Atención prioritaria"
    if puntos >= 30:
        return puntos, "atencion", "Requiere atención"
    return puntos, "normal", "Bajo / Normal"


def evaluar_riesgo_materia(nota_1, nota_2, nota_3, inas_1, inas_2, inas_3):
    """Evalúa los puntos de riesgo de un estudiante en una materia."""
    notas = [float(n) for n in (nota_1, nota_2, nota_3) if n is not None]
    promedio = round(sum(notas) / len(notas), 2) if notas else None

    faltas = [int(float(i)) for i in (inas_1, inas_2, inas_3) if i is not None]
    porcentaje_inas = sum(faltas) if faltas else None

    if inas_3 is not None:
        corte_inas = "Exa"
    elif inas_2 is not None:
        corte_inas = "P2"
    elif inas_1 is not None:
        corte_inas = "P1"
    else:
        corte_inas = None

    puntos = 0
    motivos = []

    # 1. Puntos Internos por calificación (promedio de los cortes cargados)
    if promedio is not None:
        if promedio < 3.0:
            puntos += 40
            motivos.append(f"Promedio actual: {promedio:.2f}")
        elif promedio < 3.5:
            puntos += 20
            motivos.append(f"Promedio actual: {promedio:.2f}")
        elif promedio < 4.0:
            puntos += 10
            motivos.append(f"Promedio actual: {promedio:.2f}")

    # 2. Puntos internos por % de inasistencia (P1: 5% / 8% · P2 y Exa: 10% / 15%)
    if porcentaje_inas is not None:
        umbral_atencion, umbral_prio = (5, 8) if corte_inas == "P1" else (10, 15)
        if porcentaje_inas >= umbral_prio:
            puntos += 60
            motivos.append(f"Inasistencia prioritaria en {corte_inas}: {porcentaje_inas}%")
        elif porcentaje_inas >= umbral_atencion:
            puntos += 30
            motivos.append(f"Inasistencia en atención en {corte_inas}: {porcentaje_inas}%")

    # 3. Puntos internos por tendencia descendente en el último corte cargado
    if len(notas) >= 2 and notas[-1] < notas[-2]:
        puntos += 20
        motivos.append("Tendencia descendente en último corte")

    puntaje, nivel, etiqueta = clasificar_puntaje(puntos)
    return {
        "promedio": promedio,
        "total_inasistencias": porcentaje_inas,
        "corte_inasistencia": corte_inas,
        "puntaje": puntaje,
        "nivel": nivel,
        "etiqueta": etiqueta,
        "motivos": motivos or ["Sin alertas activas"],
    }


def evaluar_riesgo_global_estudiante(materias):
    """Calcula el riesgo global del estudiante combinando sus materias."""
    promedios = [m["promedio"] for m in materias if m.get("promedio") is not None]
    promedio_global = round(sum(promedios) / len(promedios), 2) if promedios else None
    inasistencia_global = sum(m["total_inasistencias"] for m in materias if m.get("total_inasistencias") is not None)

    rojas = sum(1 for m in materias if m.get("nivel") == "prioritario")
    amarillas = sum(1 for m in materias if m.get("nivel") == "atencion")
    verdes = len(materias) - rojas - amarillas

    if len(materias) == 1:
        unica = materias[0]
        return {
            "promedio_global": promedio_global,
            "inasistencia_global": inasistencia_global,
            "rojas": rojas,
            "amarillas": amarillas,
            "verdes": verdes,
            "total_materias": 1,
            "puntaje": unica["puntaje"],
            "nivel": unica["nivel"],
            "etiqueta": unica["etiqueta"],
            "motivos": list(unica["motivos"]),
        }

    puntos = 0
    motivos = []

    if promedio_global is not None:
        if promedio_global < 3.0:
            puntos += 40
            motivos.append(f"Promedio general: {promedio_global:.2f}")
        elif promedio_global < 3.5:
            puntos += 20
            motivos.append(f"Promedio general: {promedio_global:.2f}")
        elif promedio_global < 4.0:
            puntos += 10
            motivos.append(f"Promedio general: {promedio_global:.2f}")

    if inasistencia_global >= 15:
        puntos += 60
        motivos.append(f"Inasistencia general prioritaria ({inasistencia_global}%)")
    elif inasistencia_global >= 10:
        puntos += 30
        motivos.append(f"Inasistencia general en atención ({inasistencia_global}%)")

    if rojas > 0:
        puntos += rojas * 20
        motivos.append(f"{rojas} asignatura(s) en atención prioritaria")
    if amarillas > 0:
        puntos += amarillas * 10
        motivos.append(f"{amarillas} asignatura(s) que requieren atención")

    puntaje, nivel, etiqueta = clasificar_puntaje(puntos)
    return {
        "promedio_global": promedio_global,
        "inasistencia_global": inasistencia_global,
        "rojas": rojas,
        "amarillas": amarillas,
        "verdes": verdes,
        "total_materias": len(materias),
        "puntaje": puntaje,
        "nivel": nivel,
        "etiqueta": etiqueta,
        "motivos": motivos or ["Rendimiento global normal"],
    }


def resumen_conteos_riesgo(items):
    """Cuenta cuántos estudiantes están en Normal, Atención y Prioritario."""
    total = len(items)
    prioritario = sum(1 for x in items if x.get("nivel") == "prioritario")
    atencion = sum(1 for x in items if x.get("nivel") == "atencion")
    normal = total - prioritario - atencion

    if total > 0:
        pct_normal = round(normal * 100 / total, 1)
        pct_atencion = round(atencion * 100 / total, 1)
        pct_prioritario = round(max(0.0, 100.0 - pct_normal - pct_atencion), 1)
    else:
        pct_normal = pct_atencion = pct_prioritario = 0.0

    return {
        "total": total,
        "normal": normal,
        "atencion": atencion,
        "prioritario": prioritario,
        "pct_normal": pct_normal,
        "pct_atencion": pct_atencion,
        "pct_prioritario": pct_prioritario,
    }
