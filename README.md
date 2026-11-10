# riskMapUSB (UniAlert)

Aplicación Flask con inicio de sesión y sistema de alertas tempranas académicas para **Profesor**, **Director de Programa** y **Administrador**. El logo y la paleta institucional verde y blanca se basan en el archivo `images/Logo.png`.

## Ejecutar localmente

Desde la carpeta del proyecto:

```sh
python -m pip install -r requirements.txt
python app.py
```

Al ejecutar `python app.py`, se abre automáticamente el navegador en <http://127.0.0.1:5001/login>. El puerto predeterminado es `5001` (configurable con `PORT=5002 python app.py`).

## Base de datos y primera cuenta

1. Iniciar MySQL o MariaDB y comprobar los parámetros de `BASE_DATOS` en `riskmap/config.py`: servidor `127.0.0.1`, puerto `3306`, usuario `root`, contraseña vacía y base `uni_alert`.
2. Solo en una base nueva, importar `uni_alert.sql` mediante phpMyAdmin o el cliente de MySQL.
3. Si todavía no existe una cuenta administradora, crearla desde la terminal:

   ```sh
   python -m flask --app app crear-admin
   ```

---

## Sistema de Reglas de Alerta y Semáforo de Colores

El motor de riesgo (`riskmap/services/riesgo.py`) aplica un sistema de reglas explicable y configurable (umbrales definidos en `UMBRALES_RIESGO` dentro de `riskmap/constants.py`).

### 1. Puntaje de riesgo por materia (0 a 100 puntos)

Para cada estudiante dentro de una asignatura se evalúan tres indicadores sobre los cortes disponibles (`P1`, `P2`, `Exa`):

| Indicador | Condición | Puntos |
|---|---|---|
| **Calificación** (promedio disponible) | `>= 4.0` | `0` |
| **Calificación** (promedio disponible) | `3.5 – 3.99` | `+10` |
| **Calificación** (promedio disponible) | `3.0 – 3.49` | `+20` |
| **Calificación** (promedio disponible) | `< 3.0` | `+40` |
| **Inasistencia** (acumulado en la materia) | Nivel medio (`3 a 5` faltas) | `+15` |
| **Inasistencia** (acumulado en la materia) | Nivel alto (`>= 6` faltas) | `+30` |
| **Tendencia** | Notas descendentes entre cortes consecutivos disponibles (ej. `P2 < P1` o `Exa < P2`) | `+20` |

> Si la suma supera `100`, el puntaje se limita automáticamente a **`100`**.

### 2. Clasificación y colores del semáforo

| Rango de puntaje | Clasificación | Color en plataforma |
|---|---|---|
| **`0 – 29` puntos** | **Bajo / Normal** | Verde |
| **`30 – 59` puntos** | **Requiere atención** | Amarillo |
| **`60 – 100` puntos** | **Atención prioritaria** | Rojo |

### 3. Fórmula del Riesgo Global del Estudiante

En la ficha individual del estudiante (`/estudiantes/<id_estudiante>`) y en los tableros generales se calcula el **Riesgo Global** combinando cuatro factores explicables:

$$\text{Puntaje Global} = \min\Big(100,\; P_{\text{promedio general}} + P_{\text{inasistencia general}} + 20 \times N_{\text{materias rojas}} + 10 \times N_{\text{materias amarillas}}\Big)$$

Donde:
- $P_{\text{promedio general}}$: puntos según el promedio disponible de todas sus materias (`0`, `10`, `20` o `40` pts).
- $P_{\text{inasistencia general}}$: puntos según la suma total de inasistencias en el semestre (`0`, `15` o `30` pts).
- $N_{\text{materias rojas}}$: cantidad de asignaturas en **Atención prioritaria** (`+20` pts por cada una).
- $N_{\text{materias amarillas}}$: cantidad de asignaturas en **Requiere atención** (`+10` pts por cada una).

Cada punto otorgado se lista textualmente en la interfaz para que cualquier resultado pueda explicarse de inmediato.

---

## Vistas y Dashboards por Rol

- **Dashboard del Profesor (`/`)**:
  - Tarjetas superiores con el conteo de estudiantes en **Normal**, **Atención** y **Prioritario**.
  - **Gráfico de mapa de riesgo por curso**: barras horizontales apiladas (verde, amarillo y rojo) por cada grupo asignado al profesor (`usuario.correo = docente.correo`).
  - Panel lateral de **Estudiantes prioritarios** con acceso directo a la ficha de cada alumno.
- **Dashboard del Director de Programa (`/`)**:
  - Tarjetas superiores con el resumen global de estudiantes (**Estudiantes**, **Normal**, **Atención**, **Prioritario**).
  - **Mapa de riesgo por semestre (`1°`, `2°`, `3°`...)**: barras apiladas con la proporción de riesgo en cada semestre y conteo de casos prioritarios.
  - Panel lateral de **Estudiantes prioritarios** en modo de consulta institucional.
- **Vista por Materia / Grupo (`/grupos/<id_grupo>`)**:
  - KPIs y barra de distribución de riesgo exclusiva del curso.
  - Formularios de carga de reportes en **PDF** (convertidos internamente a Excel en memoria) para **Inasistencias** y **Calificaciones** (exclusivo para el profesor titular).
  - Tabla detallada con notas, faltas, puntaje de riesgo (`0–100`), etiqueta de color y lista de motivos explicables por estudiante.
- **Vista Individual por Estudiante (`/estudiantes/<id_estudiante>`)**:
  - Resumen del **Riesgo Global** del estudiante, explicación paso a paso de su puntaje y tabla desglosada con el semáforo y motivos en cada una de sus materias.

## Estructura del proyecto

```text
app.py                              # Entrada, puerto y apertura del navegador
riskmap/
├── __init__.py                     # Factoría create_app y registro de módulos
├── config.py                       # Parámetros de conexión a MySQL
├── constants.py                    # Tablas, roles, cortes y umbrales de riesgo (UMBRALES_RIESGO)
├── database.py                     # Conexión y tabla de cuentas
├── auth.py                         # Decoradores de permisos
├── cli.py                          # Comando crear-admin
├── routes/                         # Rutas Flask por módulo
│   ├── auth.py                     # Inicio y cierre de sesión
│   ├── main.py                     # Dashboards, vista por materia, vista por estudiante y cargas PDF
│   └── admin.py                    # Administración y CRUD
├── services/                       # Lógica de negocio
│   ├── riesgo.py                   # Motor de reglas de alerta por materia y riesgo global
│   ├── grupos.py                   # Consultas de grupos, dashboards y perfil de estudiante
│   ├── pdf_inasistencia.py         # Conversión de reportes PDF a libros Excel (.xlsx) en memoria
│   ├── inasistencias.py            # Lectura del Excel de inasistencias y registro por corte
│   ├── calificaciones.py           # Lectura del Excel de calificaciones y actualización de cortes
│   ├── importacion.py              # Importación de estudiantes desde el Excel en memoria
│   └── schema.py                   # Metadatos para formularios CRUD
├── templates/
│   ├── base.html                   # Encabezado, logo, favicon y estructura común
│   ├── auth/login.html
│   ├── main/
│   │   ├── inicio.html             # Dashboard de Profesor / Director de Programa
│   │   ├── grupo.html              # Dashboard y consolidado de una materia/grupo
│   │   └── estudiante.html         # Ficha individual de riesgo del estudiante
│   └── admin/                      # Panel y formulario/listado CRUD
└── static/
    ├── css/main.css                # Estilos institucionales, tarjetas KPI, barras de riesgo y semáforo
    └── images/                     # Logo servido por Flask y usado como favicon
images/Logo.png                     # Imagen original conservada
uni_alert.sql                       # Esquema SQL original
tests/test_app.py                   # Comprobaciones con base de datos simulada
```

Para ejecutar las comprobaciones sin modificar la base de datos:

```sh
python -m unittest discover -s tests -v
```
