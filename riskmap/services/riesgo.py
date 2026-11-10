
"""Cálculo sencillo de riesgo académico por materia y global."""


def clasificar_puntaje(puntos):
    """Limita el puntaje a 100 y devuelve el nivel y etiqueta del semáforo."""
    if puntos > 100:
        puntos = 100
    if puntos < 0:
        puntos = 0

    if puntos >= 60:
        return puntos, "prioritario", "Atención prioritaria"
    elif puntos >= 30:
        return puntos, "atencion", "Requiere atención"
    else:
        return puntos, "normal", "Bajo / Normal"


def evaluar_riesgo_materia(nota_1, nota_2, nota_3, inas_1, inas_2, inas_3):
    """Evalúa los puntos de riesgo de un estudiante en una materia tomando el último corte cargado."""
    # 1. Reunir las notas de los cortes cargados y tomar la última nota registrada
    notas = []
    for n in (nota_1, nota_2, nota_3):
        if n is not None:
            notas.append(float(n))

    if len(notas) > 0:
        ultima_nota = round(notas[-1], 2)
    else:
        ultima_nota = None

    # 2. Reunir las inasistencias de los cortes cargados y tomar el último corte registrado
    faltas = []
    for i in (inas_1, inas_2, inas_3):
        if i is not None:
            faltas.append(int(float(i)))

    if len(faltas) > 0:
        ultima_inasistencia = faltas[-1]
    else:
        ultima_inasistencia = None

    puntos = 0
    motivos = []

    # Regla 1: Puntos por calificación del último corte cargado
    if ultima_nota is not None:
        if ultima_nota < 3.0:
            puntos += 40
            motivos.append(f"Nota último corte: {ultima_nota:.2f} (+40 pts)")
        elif ultima_nota < 3.5:
            puntos += 20
            motivos.append(f"Nota último corte: {ultima_nota:.2f} (+20 pts)")
        elif ultima_nota < 4.0:
            puntos += 10
            motivos.append(f"Nota último corte: {ultima_nota:.2f} (+10 pts)")

    # Regla 2: Puntos por inasistencia del último corte cargado (3 a 5 media, 6 o más alta)
    if ultima_inasistencia is not None:
        if ultima_inasistencia >= 6:
            puntos += 30
            motivos.append(f"Inasistencia alta en último corte ({ultima_inasistencia} faltas) (+30 pts)")
        elif ultima_inasistencia >= 3:
            puntos += 15
            motivos.append(f"Inasistencia media en último corte ({ultima_inasistencia} faltas) (+15 pts)")

    # Regla 3: Puntos por tendencia descendente en el último corte cargado
    if len(notas) >= 2:
        if notas[-1] < notas[-2]:
            puntos += 20
            motivos.append("Tendencia descendente en último corte (+20 pts)")

    puntaje, nivel, etiqueta = clasificar_puntaje(puntos)
    if len(motivos) == 0:
        motivos.append("Sin alertas activas (0 pts)")

    return {
        "promedio": ultima_nota,
        "total_inasistencias": ultima_inasistencia,
        "puntaje": puntaje,
        "nivel": nivel,
        "etiqueta": etiqueta,
        "motivos": motivos,
    }


def evaluar_riesgo_global_estudiante(materias):
    """Calcula el riesgo global del estudiante sumando sus indicadores generales."""
    promedios = []
    inasistencia_global = 0
    rojas = 0
    amarillas = 0
    verdes = 0

    for m in materias:
        if m.get("promedio") is not None:
            promedios.append(m["promedio"])
        if m.get("total_inasistencias") is not None:
            inasistencia_global += m["total_inasistencias"]

        if m.get("nivel") == "prioritario":
            rojas += 1
        elif m.get("nivel") == "atencion":
            amarillas += 1
        else:
            verdes += 1

    if len(promedios) > 0:
        promedio_global = round(sum(promedios) / len(promedios), 2)
    else:
        promedio_global = None

    # Si solo cursa una materia, su puntaje y nivel global coinciden con esa materia
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
            motivos.append(f"Promedio general < 3.0 ({promedio_global:.2f}) (+40 pts)")
        elif promedio_global < 3.5:
            puntos += 20
            motivos.append(f"Promedio general 3.0 - 3.49 ({promedio_global:.2f}) (+20 pts)")
        elif promedio_global < 4.0:
            puntos += 10
            motivos.append(f"Promedio general 3.5 - 3.99 ({promedio_global:.2f}) (+10 pts)")

    if inasistencia_global >= 6:
        puntos += 30
        motivos.append(f"Inasistencia general alta ({inasistencia_global} faltas) (+30 pts)")
    elif inasistencia_global >= 3:
        puntos += 15
        motivos.append(f"Inasistencia general media ({inasistencia_global} faltas) (+15 pts)")

    if rojas > 0:
        puntos += rojas * 20
        motivos.append(f"{rojas} asignatura(s) en atención prioritaria (+{rojas * 20} pts)")

    if amarillas > 0:
        puntos += amarillas * 10
        motivos.append(f"{amarillas} asignatura(s) que requieren atención (+{amarillas * 10} pts)")

    puntaje, nivel, etiqueta = clasificar_puntaje(puntos)
    if len(motivos) == 0:
        motivos.append("Rendimiento global normal (0 pts)")

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
        "motivos": motivos,
    }


def resumen_conteos_riesgo(items):
    """Cuenta cuántos estudiantes están en Normal, Atención y Prioritario."""
    total = len(items)
    normal = 0
    atencion = 0
    prioritario = 0

    for x in items:
        if x.get("nivel") == "prioritario":
            prioritario += 1
        elif x.get("nivel") == "atencion":
            atencion += 1
        else:
            normal += 1

    if total > 0:
        pct_normal = round(normal * 100 / total, 1)
        pct_atencion = round(atencion * 100 / total, 1)
        pct_prioritario = round(max(0.0, 100.0 - pct_normal - pct_atencion), 1)
    else:
        pct_normal = 0.0
        pct_atencion = 0.0
        pct_prioritario = 0.0

    return {
        "total": total,
        "normal": normal,
        "atencion": atencion,
        "prioritario": prioritario,
        "pct_normal": pct_normal,
        "pct_atencion": pct_atencion,
        "pct_prioritario": pct_prioritario,
    }
