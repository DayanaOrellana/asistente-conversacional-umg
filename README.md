
# Asistente Conversacional UMG

## Descripción

Sistema web de asistente conversacional basado en análisis de lenguaje natural, desarrollado para apoyar a los estudiantes de la Universidad Mariano Gálvez en la consulta de información académica e institucional.

Este sistema forma parte de un proyecto de graduación de Ingeniería en Sistemas.

## Objetivo

Facilitar el acceso a información de interés estudiantil mediante una interfaz web que permite realizar preguntas en lenguaje natural y obtener respuestas almacenadas en una base de datos.

## Tecnologías utilizadas

- Python
- Flask
- MySQL
- HTML y CSS
- Scikit-learn
- Git y GitHub

## Funcionalidades

- Inicio y cierre de sesión.
- Acceso mediante roles de estudiante y administrador.
- Consultas mediante lenguaje natural.
- Búsqueda de respuestas utilizando TF-IDF y similitud del coseno.
- Historial de conversaciones por usuario.
- Registro de consultas no resueltas.
- Revisión de consultas por el administrador.
- Incorporación de nuevas preguntas frecuentes.
- Descarte de consultas no relacionadas con el propósito del sistema.
- Protección de contraseñas mediante funciones hash.

## Estado del proyecto

Sistema en desarrollo y pruebas.

## Seguridad

Las credenciales de conexión a la base de datos se configuran mediante variables de entorno. El archivo `.env` no se incluye en el repositorio.

## Uso académico

Proyecto desarrollado con fines académicos para la Universidad Mariano Gálvez.



## Requisitos para ejecutar el sistema

- Python 3
- MySQL Server
- Una base de datos MySQL configurada
- Las dependencias de Python del proyecto

## Instalación y ejecución

1. Descargar o clonar el repositorio.
2. Abrir la carpeta del proyecto en Visual Studio Code.
3. Crear y activar un entorno virtual de Python.
4. Instalar las dependencias del proyecto.

    python -m pip install -r requirements.txt
    
5. Crear la base de datos y sus tablas en MySQL.
6. Configurar las variables de entorno en un archivo `.env`.
7. Ejecutar la aplicación con el comando:

   ```bash
   python app.py
   ```

8. Abrir el navegador y visitar:

   http://127.0.0.1:5000

## Configuración de variables de entorno

El archivo `.env` debe contener las siguientes variables:

- MYSQL_HOST
- MYSQL_USER
- MYSQL_PASSWORD
- MYSQL_DATABASE
- SECRET_KEY

Los valores deben configurarse de acuerdo con el entorno de instalación.

## Nota

Para utilizar todas las funcionalidades es necesario contar con la estructura de base de datos y los usuarios correspondientes.
