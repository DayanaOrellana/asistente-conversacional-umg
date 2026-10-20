from flask import Flask, render_template, request, session, redirect
import mysql.connector

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

conexion = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE")
)

print("Conexión con MySQL realizada correctamente")


def normalizar_texto(texto):
    import unicodedata
    import re

    texto = texto.lower().strip()

    # Eliminar acentos
    texto = unicodedata.normalize('NFD', texto)

    texto = ''.join(
        caracter for caracter in texto
        if unicodedata.category(caracter) != 'Mn'
    )

    # Eliminar signos de puntuación
    texto = re.sub(r'[^\w\s]', ' ', texto)

    equivalencias = {
        "papeles": "documentos",
        "papel": "documento",
        "documentacion": "documentos",
        "inscribirme": "inscripcion",
        "matricularme": "inscripcion",
        "cuota": "mensualidad",
        "cuotas": "mensualidad",
        "mensualidades": "mensualidad",
        "pagar": "pago",
        "pagos": "pago",
        "recupero": "olvide",
        "recuperar": "olvide",
        "recuperacion": "olvide",
        "cuenta": "contrasena",
        "clave": "contrasena",
        "password": "contrasena",
    }

    palabras = texto.split()

    palabras = [
        equivalencias.get(palabra, palabra)
        for palabra in palabras
    ]

    return " ".join(palabras)


def buscar_por_palabras_clave(pregunta, registros):
    pregunta = normalizar_texto(pregunta)

    grupos = {
        "inscripcion": [
            "inscripcion", "inscripción", "inscribirme",
            "inscribo", "inscribir", "matricula", "matrícula"
        ],

        "pagos": [
            "pago", "pagos", "pagar",
            "cuota", "mensualidad"
        ],

        "horarios": [
            "horario",
            "horarios",
            "hora tengo clases",
            "hora de clases",
            "dias tengo clases",
            "días tengo clases",
            "dias de clases",
            "días de clases",
            "que dias tengo clases",
            "qué días tengo clases",
            "cuando tengo clases",
            "cuándo tengo clases"
        ],

        "plataformas": [
            "plataforma", "plataformas"
        ]
    }

    for tema, palabras in grupos.items():

        if any(palabra in pregunta for palabra in palabras):

            for registro in registros:
                texto_registro = normalizar_texto(
                    registro["pregunta"]
                )

                if tema == "inscripcion" and (
                    "inscripción" in texto_registro
                    or "inscripcion" in texto_registro
                ):
                    return registro["respuesta"]

                if tema == "pagos" and (
                    "pago" in texto_registro
                    or "pagos" in texto_registro
                ):
                    return registro["respuesta"]

                if tema == "horarios":

                    if any(frase in pregunta for frase in [
                        "dias tengo clases",
                        "días tengo clases",
                        "dias de clases",
                        "días de clases",
                        "hora tengo clases",
                        "cuando tengo clases",
                        "cuándo tengo clases"
                    ]):

                        if "qué días y a qué hora" in texto_registro:
                            return registro["respuesta"]

                    elif "horario" in texto_registro:
                        return registro["respuesta"]

                if tema == "plataformas" and "plataforma" in texto_registro:
                    return registro["respuesta"]

    return None

def guardar_conversacion(pregunta, respuesta):
    cursor = conexion.cursor()

    # Crear una nueva conversación
    cursor.execute("""
        INSERT INTO conversaciones (id_usuario, titulo)
        VALUES (%s, %s)
    """, (session['id_usuario'], pregunta[:200]))

    id_conversacion = cursor.lastrowid

    # Guardar el mensaje del usuario
    cursor.execute("""
        INSERT INTO mensajes (id_conversacion, emisor, contenido)
        VALUES (%s, %s, %s)
    """, (id_conversacion, "usuario", pregunta))

    # Guardar la respuesta del asistente
    cursor.execute("""
        INSERT INTO mensajes (id_conversacion, emisor, contenido)
        VALUES (%s, %s, %s)
    """, (id_conversacion, "asistente", respuesta))

    conexion.commit()
    cursor.close()


def guardar_consulta_no_resuelta(consulta):
    cursor = conexion.cursor()

    try:
        # Comprobar si el estudiante ya tiene esta consulta pendiente
        cursor.execute("""
            SELECT id_consulta
            FROM consultas_no_resueltas
            WHERE id_usuario = %s
              AND LOWER(TRIM(consulta)) = LOWER(TRIM(%s))
              AND estado = 'pendiente'
            LIMIT 1
        """, (
            session['id_usuario'],
            consulta
        ))

        consulta_existente = cursor.fetchone()

        if consulta_existente:
            return

        # Guardar únicamente si no existe una consulta pendiente igual
        cursor.execute("""
            INSERT INTO consultas_no_resueltas
            (id_usuario, consulta, estado)
            VALUES (%s, %s, %s)
        """, (
            session['id_usuario'],
            consulta,
            'pendiente'
        ))

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()


@app.route('/')
def inicio():
    if 'id_usuario' not in session:
        return redirect('/login')

    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']

        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE correo = %s
        """, (correo,))

        usuario = cursor.fetchone()
        cursor.close()

        if usuario and check_password_hash(
            usuario['contrasena'], contrasena
        ):

            session['id_usuario'] = usuario['id_usuario']
            session['nombre'] = usuario['nombre']
            session['rol'] = usuario['rol']

            return render_template('index.html')
        else:
            return render_template(
                'login.html',
                error='Correo o contraseña incorrectos.'
            )
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/historial')
def historial():
    if 'id_usuario' not in session:
        return redirect('/login')

    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT id_conversacion, titulo, fecha_inicio
        FROM conversaciones
        WHERE id_usuario = %s
        ORDER BY fecha_inicio DESC
    """, (session['id_usuario'],))

    conversaciones = cursor.fetchall()
    cursor.close()

    return render_template(
        'historial.html',
        conversaciones=conversaciones
    )

@app.route('/conversacion/<int:id_conversacion>')
def ver_conversacion(id_conversacion):
    if 'id_usuario' not in session:
        return redirect('/login')

    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT id_usuario
        FROM conversaciones
        WHERE id_conversacion = %s
    """, (id_conversacion,))

    conversacion = cursor.fetchone()

    if conversacion is None:
        cursor.close()
        return "Conversación no encontrada", 404

    if conversacion['id_usuario'] != session['id_usuario']:
        cursor.close()
        return "Acceso denegado", 403


    cursor.execute("""
        SELECT m.emisor, m.contenido
        FROM mensajes m
        INNER JOIN conversaciones c
            ON m.id_conversacion = c.id_conversacion
        WHERE m.id_conversacion = %s
          AND c.id_usuario = %s
        ORDER BY m.id_mensaje ASC
    """, (id_conversacion, session['id_usuario']))

    mensajes = cursor.fetchall()
    cursor.close()

    return render_template(
        'conversacion.html',
        mensajes=mensajes
    )

@app.route('/consultas-no-resueltas')
def consultas_no_resueltas():
    if 'id_usuario' not in session:
        return redirect('/login')
    
    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo los administradores pueden ver esta página.", 403
    
    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT id_consulta, consulta, fecha_consulta, estado
        FROM consultas_no_resueltas
        WHERE estado = 'pendiente'
        ORDER BY fecha_consulta DESC
    """)

    consultas = cursor.fetchall()
    cursor.close()

    return render_template(
        'consultas_no_resueltas.html',
        consultas=consultas
    )

@app.route('/resolver-consulta', methods=['POST'])
def resolver_consulta():
    if 'id_usuario' not in session:
        return redirect('/login')

    if session.get('rol') != 'administrador':
        return "Acceso denegado.", 403

    id_consulta = request.form['id_consulta']
    respuesta = request.form['respuesta'].strip()
    id_categoria = request.form['id_categoria']
    
    if not respuesta:
        return "Debes escribir una respuesta.", 400

    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT id_consulta, consulta, estado
        FROM consultas_no_resueltas
        WHERE id_consulta = %s
    """, (id_consulta,))

    consulta_pendiente = cursor.fetchone()
    cursor.close()

    if not consulta_pendiente:
        return "La consulta no existe.", 404

    if consulta_pendiente['estado'] != 'pendiente':
        return "Esta consulta ya fue atendida.", 400

    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO preguntas_frecuentes
        (id_categoria, pregunta, respuesta)
        VALUES (%s, %s, %s)
    """, (
        id_categoria,
        consulta_pendiente['consulta'],
        respuesta
    ))

    cursor.execute("""
        UPDATE consultas_no_resueltas
        SET estado = 'revisada'
        WHERE id_consulta = %s
    """, (id_consulta,))

    conexion.commit()
    cursor.close()

    return redirect('/consultas-no-resueltas')


@app.route('/descartar-consulta', methods=['POST'])
def descartar_consulta():
    if 'id_usuario' not in session:
        return redirect('/login')

    if session.get('rol') != 'administrador':
        return "Acceso denegado.", 403

    id_consulta = request.form.get('id_consulta', type=int)

    if id_consulta is None:
        return "Consulta no válida.", 400

    cursor = conexion.cursor()

    try:
        cursor.execute("""
            UPDATE consultas_no_resueltas
            SET estado = 'descartada'
            WHERE id_consulta = %s
              AND estado = 'pendiente'
        """, (id_consulta,))

        if cursor.rowcount == 0:
            conexion.rollback()
            return "La consulta no existe o ya fue atendida.", 404

        conexion.commit()

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()

    return redirect('/consultas-no-resueltas')


@app.route('/preguntar', methods=['POST'])
def preguntar():
    if 'id_usuario' not in session:
        return redirect('/login')

    
    pregunta_usuario = request.form.get('pregunta', '').strip()

    if not pregunta_usuario:
        return render_template(
            'index.html',
            respuesta="Por favor, escribe una pregunta para continuar."
        )
    

    cursor = conexion.cursor(dictionary=True)

    cursor.execute("""
        SELECT pregunta, respuesta, palabras_clave
        FROM preguntas_frecuentes
        WHERE estado = 1
    """)

    registros = cursor.fetchall()
    cursor.close()

    if not registros:
        respuesta = (
            "Lo siento, por el momento no hay "
            "información disponible para responder consultas."
        )

        guardar_consulta_no_resuelta(pregunta_usuario)
        guardar_conversacion(pregunta_usuario, respuesta)

        return render_template(
            'index.html',
            pregunta=pregunta_usuario,
            respuesta=respuesta
        )

    # Primero verificar si la pregunta ya existe en la base de datos
    respuesta = None

    for registro in registros:
        if normalizar_texto(pregunta_usuario) == normalizar_texto(registro['pregunta']):
            respuesta = registro['respuesta']
            break

    # Si no hay coincidencia exacta, buscar por palabras clave
    #if respuesta is None:
    #    respuesta = buscar_por_palabras_clave(
    #        pregunta_usuario,
    #        registros
    #   )

    # Si no encuentra una intención clara,
    # utiliza similitud de texto como respaldo
    if respuesta is None:

        preguntas_bd = [
            normalizar_texto(
                registro['pregunta'] + " " +
                (registro['palabras_clave'] or "")
            )
         for registro in registros
    ]

        pregunta_normalizada = normalizar_texto(
            pregunta_usuario
        )

        textos = preguntas_bd + [pregunta_normalizada]

        vectorizador = TfidfVectorizer(
        lowercase=True,
        strip_accents='unicode',
        analyzer='word',
        ngram_range=(1, 2),
        stop_words=[
            'donde', 'puedo', 'mi', 'mis',
            'de', 'del', 'la', 'el', 'los',
            'las', 'en', 'un', 'una',
            'universidad', 'umg'
         ]
    )

        try:
            matriz = vectorizador.fit_transform(textos)

        except ValueError:
            respuesta = (
                "Lo siento, no encontré información "
                "relacionada con tu consulta."
            )

            guardar_consulta_no_resuelta(pregunta_usuario)
            guardar_conversacion(pregunta_usuario, respuesta)

            return render_template(
                'index.html',
                pregunta=pregunta_usuario,
                respuesta=respuesta
            )
    

        similitudes = cosine_similarity(
            matriz[-1],
            matriz[:-1]
        ).flatten()

        mejor_indice = similitudes.argmax()
        mejor_similitud = similitudes[mejor_indice]

        print("Pregunta seleccionada:", registros[mejor_indice]['pregunta'])

        if mejor_similitud >= 0.30:
            respuesta = registros[mejor_indice]['respuesta']
        else:
            respuesta = (
                "Lo siento, no encontré información "
                "relacionada con tu consulta."
            )

            guardar_consulta_no_resuelta(pregunta_usuario)

        print("Similitud:", mejor_similitud)

    print("Pregunta recibida:", pregunta_usuario)
    print("Respuesta:", respuesta)

    guardar_conversacion(pregunta_usuario, respuesta)

    return render_template(
        'index.html',
        pregunta=pregunta_usuario,
        respuesta=respuesta
    )


if __name__ == '__main__':
    app.run(debug=True)