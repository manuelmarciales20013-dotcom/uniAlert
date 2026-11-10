TABLAS = (
    "asignatura", "calificacion", "docente", "estudiante", "grupo",
    "grupo_estudiante", "inasistencia", "periodo", "programa", "usuario",
)

ROLES = ("profesor", "director_programa", "administrador")

ETIQUETAS_ROL = {
    "profesor": "Profesor",
    "director_programa": "Director de Programa",
    "administrador": "Administrador",
}

# Configuración de cortes académicos y sus columnas en la base de datos
CORTES = {
    "P1": {
        "columna": "corte_1",
        "etiqueta": "Primer corte (P1)",
        "anteriores": [],
    },
    "P2": {
        "columna": "corte_2",
        "etiqueta": "Segundo corte (P2)",
        "anteriores": ["corte_1"],
    },
    "Exa": {
        "columna": "corte_3",
        "etiqueta": "Examen final (Exa)",
        "anteriores": ["corte_1", "corte_2"],
    },
}

# Umbrales configurables para el motor de reglas de alerta temprana
UMBRALES_RIESGO = {
    "inasistencia_media": 3,   # Entre 3 y 5 inasistencias -> +15 puntos
    "inasistencia_alta": 6,    # 6 o más inasistencias -> +30 puntos
    "tope_puntaje": 100,       # Puntaje máximo permitido
}
