"""Comandos de mantenimiento de cuentas."""

import click
import mysql.connector
from werkzeug.security import generate_password_hash
from .database import conectar, asegurar_tabla_usuarios


@click.command("crear-admin")
def crear_admin():
    """Crea la primera cuenta administradora desde la terminal."""
    try:
        asegurar_tabla_usuarios()
        nombre = click.prompt("Nombre")
        correo = click.prompt("Correo")
        clave = click.prompt("Contraseña", hide_input=True, confirmation_prompt=True)
        conexion = conectar()
        try:
            cursor = conexion.cursor()
            cursor.execute("INSERT INTO usuario (nombre,correo,password_hash,rol) VALUES (%s,%s,%s,'administrador')",
                           (nombre, correo.strip().lower(), generate_password_hash(clave)))
            conexion.commit()
            cursor.close()
        finally:
            conexion.close()
        click.echo("Cuenta de administrador creada.")
    except mysql.connector.Error as error:
        raise click.ClickException(str(error)) from error


