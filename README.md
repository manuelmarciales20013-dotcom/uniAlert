# riskMapUSB

Aplicación Flask con inicio de sesión para Profesor, Director de Programa y
Administrador. El logo y la paleta verde y blanca se basan en el archivo
`images/Logo.png` proporcionado para el proyecto.

## Ejecutar localmente

Desde la carpeta del proyecto:

```sh
python3 -m pip install -r requirements.txt
python3 app.py
```

Al ejecutar `python3 app.py`, se abre automáticamente el navegador en
<http://127.0.0.1:5001/login>. El puerto predeterminado es 5001 para
evitar el conflicto con el servicio de macOS que ocupa el 5000. Se puede cambiar
con `PORT=5002 python3 app.py`.

## Base de datos y primera cuenta

1. Iniciar MySQL o MariaDB y comprobar los parámetros de `BASE_DATOS` en
   `riskmap/config.py`: servidor `127.0.0.1`, puerto `3306`, usuario `root`, contraseña
   vacía y base `uni_alert`. Ajustarlos si la instalación local usa otros valores.
2. Solo en una base nueva, importar `uni_alert.sql` mediante phpMyAdmin o el
   cliente de MySQL. Si las tablas ya existen, conservarlas: no volver a importar
   el archivo sobre ellas. La aplicación crea la tabla `usuario` si falta.
3. Si todavía no existe una cuenta administradora, crearla desde la terminal:

   ```sh
   python3 -m flask --app app crear-admin
   ```

4. Iniciar sesión con ese correo y contraseña y pulsar **Abrir módulo
   Administrador**, o abrir <http://127.0.0.1:5001/admin>.

El administrador puede crear, consultar, editar y eliminar registros de las diez
tablas, incluidas las cuentas de usuario y sus roles. Los demás roles no tienen
acceso al CRUD. El rol se obtiene de la cuenta al iniciar sesión.

Si aparece el formulario con un error de conexión, verificar que MySQL esté
iniciado y que su puerto coincida con `riskmap/config.py`. El encabezado del volcado SQL
menciona el puerto 3307; la configuración actual de la aplicación usa 3306.


## Estructura del proyecto

```text
app.py                         # Entrada, puerto y apertura del navegador
riskmap/
├── __init__.py                # Factoría create_app y registro de módulos
├── config.py                  # Parámetros de conexión a MySQL
├── constants.py               # Tablas permitidas y roles
├── database.py                # Conexión y tabla de cuentas
├── auth.py                    # Decoradores de permisos
├── cli.py                     # Comando crear-admin
├── routes/                    # Rutas Flask por módulo
│   ├── auth.py                # Inicio y cierre de sesión
│   ├── main.py                # Inicio e importación
│   └── admin.py               # Administración y CRUD
├── services/
│   ├── importacion.py         # Importación de estudiantes desde Excel
│   └── schema.py              # Metadatos para formularios CRUD
├── templates/
│   ├── base.html              # Encabezado, logo, favicon y estructura común
│   ├── auth/login.html
│   ├── main/inicio.html
│   └── admin/                 # Panel y formulario/listado CRUD
└── static/
    ├── css/main.css           # Estilos y colores institucionales
    └── images/                # Logo servido por Flask y usado como favicon
images/Logo.png                # Imagen original conservada
uni_alert.sql                  # Esquema SQL original
extract.py                     # Compatibilidad con importaciones anteriores
tests/test_app.py              # Comprobaciones con base de datos simulada
```

El comando para crear el administrador y las direcciones de las páginas se
mantienen. `extract.py` reexporta los servicios para conservar compatibilidad;
la configuración de MySQL se modifica ahora en `riskmap/config.py`.

Para ejecutar las comprobaciones sin modificar la base de datos:

```sh
python3 -m unittest discover -s tests -v
```
