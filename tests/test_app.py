"""Regresiones de navegación, sesiones, recursos, CRUD, cargas académicas y motor de riesgo sin tocar MySQL."""

import io
import unittest
from unittest.mock import patch

import mysql.connector
import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

from riskmap import create_app
from riskmap.constants import TABLAS
from riskmap.services.calificaciones import cargar_calificaciones_excel
from riskmap.services.inasistencias import (
    cargar_inasistencias_excel,
    comparar_grupo_excel,
    leer_titulo_excel,
)
from riskmap.services.pdf_inasistencia import escribir_excel
from riskmap.services.riesgo import (
    evaluar_riesgo_global_estudiante,
    evaluar_riesgo_materia,
)


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="pruebas")
        self.client = self.app.test_client()

    def login_as(self, role, correo="prueba@usb.test"):
        with self.client.session_transaction() as session:
            session["usuario"] = {
                "id_usuario": 1, "nombre": "Prueba", "correo": correo,
                "rol": role, "id_programa": None,
            }

    @patch("riskmap.routes.auth.asegurar_tabla_usuarios")
    def test_login_logo_and_static_files(self, ensure):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('rel="icon"', html)
        self.assertIn("Universidad Simón Bolívar", html)
        for path in ("/static/images/logo-universidad.png", "/static/css/main.css"):
            with self.client.get(path) as asset:
                self.assertEqual(asset.status_code, 200)
                self.assertGreater(len(asset.data), 100)

    @patch("riskmap.routes.auth.asegurar_tabla_usuarios", side_effect=mysql.connector.Error("Sin conexión"))
    def test_database_error_keeps_login_visible(self, ensure):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Iniciar sesión", response.get_data(as_text=True))

    @patch("riskmap.routes.auth.asegurar_tabla_usuarios")
    @patch("riskmap.routes.auth.conectar")
    def test_login_with_hashed_password_and_logout(self, connect, ensure):
        account = {
            "id_usuario": 1, "nombre": "Admin", "correo": "admin@usb.test",
            "rol": "administrador", "id_programa": None,
            "password_hash": generate_password_hash("clave-prueba"),
        }
        connect.return_value.cursor.return_value.fetchone.return_value = account
        invalid = self.client.post("/login", data={"correo": account["correo"], "clave": "incorrecta"})
        self.assertIn("Correo o contraseña incorrectos", invalid.get_data(as_text=True))
        response = self.client.post("/login", data={"correo": " ADMIN@USB.TEST ", "clave": "clave-prueba"})
        self.assertEqual(response.location, "/")
        with self.client.session_transaction() as session:
            self.assertEqual(session["usuario"]["rol"], "administrador")
            self.assertNotIn("password_hash", session["usuario"])
        self.assertEqual(self.client.get("/logout").location, "/login")
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_roles_and_admin_links(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        for role in ("profesor", "director_programa", "administrador"):
            self.login_as(role)
            if role == "administrador":
                response = self.client.get("/admin")
                self.assertEqual(response.status_code, 200)
                for table in TABLAS:
                    self.assertIn("/admin/" + table, response.get_data(as_text=True))
            else:
                self.assertEqual(self.client.get("/admin").status_code, 403)
                self.assertEqual(self.client.get("/admin/usuario").status_code, 403)
                self.assertEqual(self.client.post("/admin/usuario/guardar").status_code, 403)

    @patch("riskmap.routes.main.conectar")
    def test_home_for_all_roles(self, connect):
        connect.return_value.cursor.return_value.fetchall.return_value = [(1, "Ingeniería")]
        for role in ("profesor", "director_programa", "administrador"):
            self.login_as(role)
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Bienvenido", response.get_data(as_text=True))

    @patch("riskmap.routes.admin.obtener_campos")
    @patch("riskmap.routes.admin.conectar")
    def test_crud_form_and_parameterized_writes(self, connect, fields):
        self.login_as("administrador")
        connection = connect.return_value
        cursor = connection.cursor.return_value
        fields.return_value = ([
            {"name": "id_programa", "auto": True, "required": False, "input_type": "number", "options": None},
            {"name": "nombre", "auto": False, "required": True, "input_type": None, "options": None},
        ], "id_programa")
        cursor.fetchall.return_value = [{"id_programa": 1, "nombre": "Ingeniería"}]
        cursor.fetchone.return_value = cursor.fetchall.return_value[0]
        for path in ("/admin/programa", "/admin/programa?editar=1"):
            self.assertEqual(self.client.get(path).status_code, 200)
        for action in ("crear", "actualizar", "eliminar"):
            cursor.reset_mock()
            response = self.client.post("/admin/programa/guardar", data={
                "accion": action, "pk_value": "1", "nombre": "Programa de prueba",
            })
            self.assertEqual(response.location, "/admin/programa")
            sql, params = cursor.execute.call_args.args
            self.assertIn("%s", sql)
            self.assertNotIn("Programa de prueba", sql)
            self.assertTrue(params)
        self.assertEqual(self.client.get("/admin/no_permitida").status_code, 404)
        connection.commit.assert_called()

    @patch("riskmap.routes.admin.obtener_campos")
    @patch("riskmap.routes.admin.conectar")
    def test_user_password_is_hashed(self, connect, fields):
        self.login_as("administrador")
        fields.return_value = ([
            {"name": "clave", "auto": False, "required": False, "input_type": "password", "options": None},
        ], "id_usuario")
        self.client.post("/admin/usuario/guardar", data={"accion": "crear", "clave": "clave-prueba"})
        sql, params = connect.return_value.cursor.return_value.execute.call_args.args
        self.assertIn("password_hash", sql)
        self.assertNotEqual(params[0], "clave-prueba")
        self.assertTrue(check_password_hash(params[0], "clave-prueba"))

    def test_admin_cli_remains_registered(self):
        result = self.app.test_cli_runner().invoke(args=["crear-admin", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("administradora", result.output)

    @patch("riskmap.routes.main.obtener_detalle_grupo")
    @patch("riskmap.routes.main.obtener_grupo")
    def test_permisos_grupos_profesor_y_director(self, mock_grupo, mock_detalle):
        mock_grupo.return_value = {
            "id_grupo": 1,
            "cod_grupo": "G01",
            "nombre_grupo": "Grupo 1",
            "asignatura": "Cálculo Diferencial",
            "cod_asignatura": "MAT101",
            "semestre": 1,
            "programa": "Ingeniería de Sistemas",
            "periodo": "2026-2",
            "docente": "Prof. Titular",
            "correo_docente": "titular@usb.test",
        }
        mock_detalle.return_value = {
            "estudiantes": [],
            "cortes_inasistencia": {"P1": False, "P2": False, "Exa": False},
            "resumen_riesgo": {
                "total": 0, "normal": 0, "atencion": 0, "prioritario": 0,
                "pct_normal": 0, "pct_atencion": 0, "pct_prioritario": 0,
            },
            "prioritarios": [],
        }

        self.login_as("profesor", correo="titular@usb.test")
        res_propio = self.client.get("/grupos/1")
        self.assertEqual(res_propio.status_code, 200)
        html_propio = res_propio.get_data(as_text=True)
        self.assertIn("Cargar inasistencias (PDF)", html_propio)
        self.assertIn("Cargar calificaciones (PDF)", html_propio)

        self.login_as("profesor", correo="otro@usb.test")
        self.assertEqual(self.client.get("/grupos/1").status_code, 403)
        self.assertEqual(self.client.post("/grupos/1/inasistencias").status_code, 403)
        self.assertEqual(self.client.post("/grupos/1/calificaciones").status_code, 403)

        self.login_as("director_programa", correo="director@usb.test")
        res_dir = self.client.get("/grupos/1")
        self.assertEqual(res_dir.status_code, 200)
        self.assertIn("Modo de consulta", res_dir.get_data(as_text=True))
        self.assertNotIn("Procesar PDF de inasistencias", res_dir.get_data(as_text=True))
        self.assertEqual(self.client.post("/grupos/1/inasistencias").status_code, 403)
        self.assertEqual(self.client.post("/grupos/1/calificaciones").status_code, 403)

    @patch("riskmap.services.inasistencias.conectar")
    def test_flujo_excel_inasistencias_y_comparacion_grupo(self, mock_conectar):
        info = {"asignatura": "Cálculo Diferencial", "grupo": "01", "promedio": 0.12}
        columnas = [(1, "Lu", 100.0), (1, "Mi", 130.0)]
        estudiantes = [
            {"codigo": "20201001", "nombre": "Ana Pérez", "marcas": {0: 2, 1: 1}, "total_pdf": 3, "pct_pdf": 0.1},
            {"codigo": "99999999", "nombre": "No Registrado", "marcas": {0: 1}, "total_pdf": 1, "pct_pdf": 0.05},
        ]
        buffer_excel = io.BytesIO()
        escribir_excel(info, columnas, estudiantes, buffer_excel)

        encabezado = leer_titulo_excel(buffer_excel)
        self.assertEqual(encabezado["asignatura"], "Cálculo Diferencial")
        self.assertEqual(encabezado["grupo"], "01")

        grupo_coincidente = {
            "asignatura": "Cálculo Diferencial",
            "cod_asignatura": "MAT101",
            "cod_grupo": "G01",
            "nombre_grupo": "Grupo 1",
        }
        self.assertIsNone(comparar_grupo_excel(encabezado, grupo_coincidente))

        grupo_distinto = {
            "asignatura": "Física Mecánica",
            "cod_asignatura": "FIS101",
            "cod_grupo": "G03",
            "nombre_grupo": "Grupo 3",
        }
        self.assertIn("Inasistencia - Cálculo Diferencial - Grupo 01", comparar_grupo_excel(encabezado, grupo_distinto))

        cursor = mock_conectar.return_value.cursor.return_value
        cursor.fetchone.side_effect = [
            (10,),                 # id_estudiante de Ana Pérez
            (50, 1, None, None),   # registro en inasistencia: corte_1 = 1
            (1,),                  # ya está en grupo_estudiante
            None,                  # estudiante 99999999 no existe
        ]

        resumen = cargar_inasistencias_excel(buffer_excel, id_grupo=1, corte_actual="P2")
        self.assertEqual(resumen["actualizados"], 1)
        self.assertEqual(len(resumen["omitidos"]), 1)
        self.assertIn("99999999", resumen["omitidos"][0])

    @patch("riskmap.services.calificaciones.conectar")
    def test_carga_calificaciones_sin_corte_y_ceros_no_evaluados_a_null(self, mock_conectar):
        df = pd.DataFrame([
            {"Código": "20201001", "Estudiante": "Ana", "Correo": "ana@usb.test", "P1": 4.5, "P2": 0, "Exa": 0},
            {"Código": "20201002", "Estudiante": "Luis", "Correo": "luis@usb.test", "P1": 0.0, "P2": 0, "Exa": 0},
        ])
        excel_buf = io.BytesIO()
        df.to_excel(excel_buf, index=False)
        excel_buf.seek(0)

        cursor = mock_conectar.return_value.cursor.return_value
        cursor.fetchone.side_effect = [
            (10,),   # Estudiante Ana existe
            (100,),  # Calificación de Ana ya existe -> UPDATE
            (1,),    # grupo_estudiante de Ana
            (11,),   # Estudiante Luis existe
            None,    # Calificación de Luis no existe -> INSERT
            (2,),    # grupo_estudiante de Luis
        ]

        resumen = cargar_calificaciones_excel(excel_buf, id_grupo=1)
        self.assertEqual(resumen["cortes_activos"], ["P1"])
        self.assertEqual(resumen["actualizados"], 1)
        self.assertEqual(resumen["nuevos"], 1)

        llamadas_sql = [llamada.args for llamada in cursor.execute.call_args_list]
        updates = [params for sql, params in llamadas_sql if "UPDATE calificacion" in sql]
        inserts = [params for sql, params in llamadas_sql if "INSERT INTO calificacion" in sql]
        self.assertEqual(updates[0], (4.5, None, None, 100))
        self.assertEqual(inserts[0], (11, 1, 0.0, None, None))

    def test_motor_reglas_riesgo_y_vista_estudiante(self):
        # 1. Estudiante prioritario: última nota < 3.0 (+40), faltas último corte >= 6 (+30), tendencia descendente (+20) = 90
        r_prio = evaluar_riesgo_materia(2.8, 2.2, None, 2, 6, None)
        self.assertEqual(r_prio["puntaje"], 90)
        self.assertEqual(r_prio["nivel"], "prioritario")

        # 2. Estudiante en atención: última nota 3.6 (+10), tendencia descendente (+20) = 30
        r_aten = evaluar_riesgo_materia(4.0, 3.6, None, 5, 0, None)
        self.assertEqual(r_aten["puntaje"], 30)
        self.assertEqual(r_aten["nivel"], "atencion")

        # 3. Estudiante normal: promedio >= 4.0 (+0), pocas faltas (+0) = 0
        r_norm = evaluar_riesgo_materia(4.2, 4.5, None, 0, 1, None)
        self.assertEqual(r_norm["puntaje"], 0)
        self.assertEqual(r_norm["nivel"], "normal")

        # 4. Riesgo global combinando materias
        global_est = evaluar_riesgo_global_estudiante([r_prio, r_aten])
        self.assertEqual(global_est["rojas"], 1)
        self.assertEqual(global_est["amarillas"], 1)
        self.assertEqual(global_est["nivel"], "prioritario")


if __name__ == "__main__":
    unittest.main()
