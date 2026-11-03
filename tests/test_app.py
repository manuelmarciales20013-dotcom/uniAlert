"""Regresiones de navegación, sesiones, recursos y CRUD sin tocar MySQL."""

import unittest
from unittest.mock import MagicMock, patch

import mysql.connector
from werkzeug.security import check_password_hash, generate_password_hash

from riskmap import create_app
from riskmap.constants import TABLAS


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="pruebas")
        self.client = self.app.test_client()

    def login_as(self, role):
        with self.client.session_transaction() as session:
            session["usuario"] = {
                "id_usuario": 1, "nombre": "Prueba", "correo": "prueba@usb.test",
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


if __name__ == "__main__":
    unittest.main()
