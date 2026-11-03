"""Conexión e inicialización de la tabla de cuentas."""

import mysql.connector
from .config import BASE_DATOS


def conectar():
    return mysql.connector.connect(**BASE_DATOS)


def asegurar_tabla_usuarios():
    conexion = conectar()
    try:
        cursor = conexion.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS usuario (
            id_usuario INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            correo VARCHAR(150) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            rol ENUM('profesor','director_programa','administrador') NOT NULL,
            id_programa INT NULL,
            CONSTRAINT usuario_ibfk_1 FOREIGN KEY (id_programa)
              REFERENCES programa(id_programa) ON DELETE SET NULL ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        conexion.commit()
        cursor.close()
    finally:
        conexion.close()


