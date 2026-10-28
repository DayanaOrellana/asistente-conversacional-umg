from flask import Flask, render_template, request, session, redirect
import mysql.connector

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

@app.before_request
def verificar_usuario_activo():

    

    # Rutas que se pueden visitar sin iniciar sesión
    rutas_publicas = {
        'login',
        'registro',
        'static'
    }

    # Permitir el acceso a las rutas públicas
    if request.endpoint in rutas_publicas:
        return None

    # Si no existe una sesión, dejar que la ruta
    # aplique sus propias validaciones de acceso.
    if 'id_usuario' not in session:
        return None

    cursor = conexion.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT estado, rol
            FROM usuarios
            WHERE id_usuario = %s
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

    finally:
        cursor.close()

    # Bloquear cuentas eliminadas o desactivadas
    if not usuario or usuario['estado'] != 'activo':

        session.clear()

        return render_template(
            'login.html',
            error='Tu cuenta está desactivada. Comunícate con el administrador.'
        ), 403

    # Actualizar el rol de la sesión según MySQL
    session['rol'] = usuario['rol']

    return None

# Configuración del correo electrónico
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

mail = Mail(app)

# Generador de enlaces seguros para recuperar contraseñas
serializer = URLSafeTimedSerializer(app.secret_key)

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
        "materias": "cursos",
        "materia": "cursos",
        "asignaturas": "cursos",
        "asignatura": "cursos",
        "aprendere": "cursos",
        "aprender": "cursos",
        "pensum": "cursos",
        "requisitos": "documentos",
        "requisito": "documentos",
        "documento": "documentos",
        "inscribirse": "inscripcion",
        "inscribir": "inscripcion",
        "inscribo": "inscripcion",
        "matricula": "inscripcion",
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
        correo = request.form['correo'].strip().lower()
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

            if usuario['estado'] != 'activo':
                return render_template(
                    'login.html',
                    error='Tu cuenta está desactivada. Comunícate con el administrador.'
                )

            session.clear()
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



@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        correo = request.form.get('correo', '').strip().lower()
        contrasena = request.form.get('contrasena', '')

        if not nombre or not apellido or not correo or not contrasena:
            return render_template(
                'registro.html',
                error='Todos los campos son obligatorios.'
            )

        if len(contrasena) < 8:
            return render_template(
                'registro.html',
                error='La contraseña debe tener al menos 8 caracteres.'
            )

        cursor = conexion.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT id_usuario FROM usuarios WHERE correo = %s",
                (correo,)
            )

            if cursor.fetchone():
                return render_template(
                    'registro.html',
                    error='Este correo ya está registrado.'
                )

            contrasena_segura = generate_password_hash(contrasena)

            cursor.execute("""
                INSERT INTO usuarios (nombre, apellido, correo, contrasena, rol)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre, apellido, correo, contrasena_segura, 'estudiante'))

            conexion.commit()

            return redirect('/login?registro=exitoso')

        except mysql.connector.Error as error:
            conexion.rollback()
            print("ERROR AL REGISTRAR ESTUDIANTE:", error)

        finally:
            cursor.close()

    return render_template('registro.html')




@app.route('/recuperar-contrasena', methods=['GET', 'POST'])
def recuperar_contrasena():
    mensaje = None

    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()

        mensaje = (
            'Si el correo está registrado, recibirás un enlace '
            'para recuperar tu contraseña.'
        )

        cursor = conexion.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT id_usuario, correo, contrasena FROM usuarios WHERE correo = %s",
                (correo,)
            )
            usuario = cursor.fetchone()

            if usuario:
                token = serializer.dumps(
                    [usuario['id_usuario'], usuario['contrasena']],
                    salt='recuperacion-contrasena'
                )

                enlace = url_for(
                    'restablecer_contrasena',
                    token=token,
                    _external=True
                )

                correo_mensaje = Message(
                    subject='Recuperación de contraseña - Asistente UMG',
                    recipients=[usuario['correo']]
                )

                correo_mensaje.body = f"""
Hola:

Recibimos una solicitud para recuperar tu contraseña
del Asistente Conversacional UMG.

Abre el siguiente enlace para crear una contraseña nueva:

{enlace}

Este enlace vencerá en 30 minutos.

Si no solicitaste este cambio, puedes ignorar este correo.

Asistente Conversacional UMG
"""

                mail.send(correo_mensaje)

        except Exception:
            app.logger.exception('Error al procesar recuperación de contraseña')
        finally:
            cursor.close()

    return render_template(
        'recuperar_contrasena.html',
        mensaje=mensaje
    )



@app.route('/restablecer-contrasena/<token>', methods=['GET', 'POST'])
def restablecer_contrasena(token):
    try:
        datos = serializer.loads(
            token,
            salt='recuperacion-contrasena',
            max_age=1800
        )
        id_usuario, contrasena_anterior = datos

    except (SignatureExpired, BadSignature, ValueError, TypeError):
        return "El enlace de recuperación no es válido o ha vencido.", 400

    cursor = conexion.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT contrasena FROM usuarios WHERE id_usuario = %s",
            (id_usuario,)
        )
        usuario = cursor.fetchone()

        if not usuario or usuario['contrasena'] != contrasena_anterior:
            return "Este enlace ya no es válido.", 400

        if request.method == 'POST':
            nueva_contrasena = request.form.get('contrasena', '')
            confirmar = request.form.get('confirmar_contrasena', '')

            if len(nueva_contrasena) < 8:
                return render_template(
                    'restablecer_contrasena.html',
                    error='La contraseña debe tener al menos 8 caracteres.'
                )

            if nueva_contrasena != confirmar:
                return render_template(
                    'restablecer_contrasena.html',
                    error='Las contraseñas no coinciden.'
                )

            contrasena_segura = generate_password_hash(nueva_contrasena)

            cursor.execute(
                "UPDATE usuarios SET contrasena = %s WHERE id_usuario = %s AND contrasena = %s",
                (contrasena_segura, id_usuario, contrasena_anterior)
            )

            if cursor.rowcount != 1:
                conexion.rollback()
                return "Este enlace ya no es válido.", 400

            conexion.commit()
            return redirect('/login?recuperacion=exitosa')

    finally:
        cursor.close()

    return render_template('restablecer_contrasena.html')



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



# Módulo administrativo de preguntas y respuestas
@app.route('/admin/preguntas')
def administrar_preguntas():

    # Verificar inicio de sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    # Permitir acceso solo a administradores
    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo administradores.", 403

    cursor = conexion.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                p.id_pregunta,
                p.pregunta,
                p.respuesta,
                p.palabras_clave,
                p.estado,
                p.fecha_registro,
                c.nombre AS categoria
            FROM preguntas_frecuentes p
            LEFT JOIN categorias c
                ON p.id_categoria = c.id_categoria
            ORDER BY p.id_pregunta DESC
        """)

        preguntas = cursor.fetchall()

    finally:
        cursor.close()

    return render_template(
        'admin_preguntas.html',
        preguntas=preguntas
    )



# Módulo administrativo de usuarios
@app.route('/admin/usuarios')
def administrar_usuarios():

    # Verificar inicio de sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    # Permitir acceso solo a administradores
    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo administradores.", 403

    cursor = conexion.cursor(dictionary=True)

    try:
        # Confirmar que el administrador sigue activo
        cursor.execute("""
            SELECT rol, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (session['id_usuario'],))

        administrador = cursor.fetchone()

        if not administrador or administrador['estado'] != 'activo' \
                or administrador['rol'] != 'administrador':
            session.clear()
            return redirect('/login')

        # Obtener todos los usuarios sin mostrar contraseñas
        cursor.execute("""
            SELECT
                id_usuario,
                nombre,
                apellido,
                correo,
                rol,
                estado,
                fecha_registro
            FROM usuarios
            ORDER BY id_usuario DESC
        """)

        usuarios = cursor.fetchall()

    finally:
        cursor.close()

    return render_template(
        'admin_usuarios.html',
        usuarios=usuarios
    )



# Registrar nuevos administradores
@app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
def registrar_administrador():

    # Verificar inicio de sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    cursor = conexion.cursor(dictionary=True)

    try:
        # Verificar que el usuario actual sea administrador activo
        cursor.execute("""
            SELECT rol, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (session['id_usuario'],))

        usuario_actual = cursor.fetchone()

        if not usuario_actual or usuario_actual['estado'] != 'activo':
            session.clear()
            return redirect('/login')

        if usuario_actual['rol'] != 'administrador':
            return "Acceso denegado. Solo administradores.", 403

        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            apellido = request.form.get('apellido', '').strip()
            correo = request.form.get('correo', '').strip().lower()
            contrasena = request.form.get('contrasena', '')

            if not nombre or not apellido or not correo or not contrasena:
                return render_template(
                    'admin_nuevo_usuario.html',
                    error='Todos los campos son obligatorios.'
                )

            if len(contrasena) < 8:
                return render_template(
                    'admin_nuevo_usuario.html',
                    error='La contraseña debe tener al menos 8 caracteres.'
                )

            cursor.execute("""
                SELECT id_usuario
                FROM usuarios
                WHERE correo = %s
            """, (correo,))

            if cursor.fetchone():
                return render_template(
                    'admin_nuevo_usuario.html',
                    error='Este correo ya está registrado.'
                )

            contrasena_segura = generate_password_hash(contrasena)

            cursor.execute("""
                INSERT INTO usuarios
                    (nombre, apellido, correo, contrasena, rol, estado)
                VALUES (%s, %s, %s, %s, 'administrador', 'activo')
            """, (
                nombre,
                apellido,
                correo,
                contrasena_segura
            ))

            conexion.commit()

            return redirect('/admin/usuarios')

    except mysql.connector.Error as error:
        conexion.rollback()
        print("ERROR AL REGISTRAR ADMINISTRADOR:", error)

        return render_template(
            'admin_nuevo_usuario.html',
            error='No se pudo registrar el administrador.'
        )

    finally:
        cursor.close()

    return render_template('admin_nuevo_usuario.html')


# Editar información básica de usuarios
@app.route('/admin/usuarios/editar/<int:id_usuario>', methods=['GET', 'POST'])
def editar_usuario(id_usuario):

    # Verificar inicio de sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    cursor = conexion.cursor(dictionary=True)

    try:
        # Verificar que quien edita sea administrador activo
        cursor.execute("""
            SELECT rol, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (session['id_usuario'],))

        administrador = cursor.fetchone()

        if not administrador or administrador['estado'] != 'activo':
            session.clear()
            return redirect('/login')

        if administrador['rol'] != 'administrador':
            return "Acceso denegado. Solo administradores.", 403

        # Obtener el usuario que se desea editar
        cursor.execute("""
            SELECT id_usuario, nombre, apellido, correo, rol, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (id_usuario,))

        usuario = cursor.fetchone()

        if not usuario:
            return "Usuario no encontrado.", 404

        if request.method == 'POST':

            nombre = request.form.get('nombre', '').strip()
            apellido = request.form.get('apellido', '').strip()
            correo = request.form.get('correo', '').strip().lower()

            if not nombre or not apellido or not correo:
                return render_template(
                    'admin_editar_usuario.html',
                    usuario=usuario,
                    error='Todos los campos son obligatorios.'
                )

            # Comprobar que el correo no pertenezca a otro usuario
            cursor.execute("""
                SELECT id_usuario
                FROM usuarios
                WHERE correo = %s AND id_usuario != %s
            """, (correo, id_usuario))

            if cursor.fetchone():
                return render_template(
                    'admin_editar_usuario.html',
                    usuario=usuario,
                    error='Este correo pertenece a otro usuario.'
                )

            # Actualizar únicamente información básica
            cursor.execute("""
                UPDATE usuarios
                SET nombre = %s,
                    apellido = %s,
                    correo = %s
                WHERE id_usuario = %s
            """, (nombre, apellido, correo, id_usuario))

            conexion.commit()

            # Actualizar el nombre en sesión si se editó a sí mismo
            if session['id_usuario'] == id_usuario:
                session['nombre'] = nombre

            return redirect('/admin/usuarios')

    except mysql.connector.Error as error:
        conexion.rollback()
        print("ERROR AL EDITAR USUARIO:", error)

        return render_template(
            'admin_editar_usuario.html',
            usuario=usuario if 'usuario' in locals() else None,
            error='No se pudieron guardar los cambios.'
        )

    finally:
        cursor.close()

    return render_template(
        'admin_editar_usuario.html',
        usuario=usuario
    )



# Activar y desactivar usuarios
@app.route('/admin/usuarios/cambiar-estado/<int:id_usuario>', methods=['POST'])
def cambiar_estado_usuario(id_usuario):

    # Verificar que exista una sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    cursor = conexion.cursor(dictionary=True)

    try:
        # Comprobar que el usuario actual sea administrador activo
        cursor.execute("""
            SELECT rol, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (session['id_usuario'],))

        administrador = cursor.fetchone()

        if not administrador or administrador['estado'] != 'activo':
            session.clear()
            return redirect('/login')

        if administrador['rol'] != 'administrador':
            return "Acceso denegado. Solo administradores.", 403

        # Impedir que un administrador cambie su propio estado
        if session['id_usuario'] == id_usuario:
            return "No puedes cambiar el estado de tu propia cuenta.", 403

        # Obtener el estado actual del usuario seleccionado
        cursor.execute("""
            SELECT id_usuario, estado
            FROM usuarios
            WHERE id_usuario = %s
        """, (id_usuario,))

        usuario = cursor.fetchone()

        if not usuario:
            return "Usuario no encontrado.", 404

        # Alternar entre activo e inactivo
        nuevo_estado = (
            'inactivo' if usuario['estado'] == 'activo'
            else 'activo'
        )

        cursor.execute("""
            UPDATE usuarios
            SET estado = %s
            WHERE id_usuario = %s
        """, (nuevo_estado, id_usuario))

        conexion.commit()

        return redirect('/admin/usuarios')

    except mysql.connector.Error as error:
        conexion.rollback()
        print("ERROR AL CAMBIAR ESTADO DEL USUARIO:", error)
        return "No se pudo cambiar el estado del usuario.", 500

    finally:
        cursor.close()

@app.route('/admin/preguntas/nueva', methods=['GET', 'POST'])
def nueva_pregunta():

    # Verificar inicio de sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    # Permitir acceso solo a administradores
    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo administradores.", 403

    cursor = conexion.cursor(dictionary=True)

    try:
        # Obtener las categorías disponibles
        cursor.execute("""
            SELECT id_categoria, nombre
            FROM categorias
            ORDER BY nombre
        """)
        categorias = cursor.fetchall()

        if request.method == 'POST':

            pregunta = request.form.get('pregunta', '').strip()
            respuesta = request.form.get('respuesta', '').strip()
            palabras_clave = request.form.get('palabras_clave', '').strip()
            id_categoria = request.form.get('id_categoria', '').strip()

            # Validar los campos obligatorios
            if not pregunta or not respuesta or not id_categoria:
                return render_template(
                    'admin_nueva_pregunta.html',
                    categorias=categorias,
                    error='Completa todos los campos obligatorios.'
                )

            if len(pregunta) > 500 or len(palabras_clave) > 500:
                return render_template(
                    'admin_nueva_pregunta.html',
                    categorias=categorias,
                    error='La pregunta y las palabras clave no pueden superar 500 caracteres.'
                )

            if not id_categoria.isdigit() or not any(
                str(c['id_categoria']) == id_categoria
                for c in categorias
            ):
                return render_template(
                    'admin_nueva_pregunta.html',
                    categorias=categorias,
                    error='Selecciona una categoría válida.'
                )

            # Registrar una nueva pregunta
            cursor.execute("""
                INSERT INTO preguntas_frecuentes
                    (id_categoria, pregunta, respuesta, palabras_clave, estado)
                VALUES (%s, %s, %s, %s, 1)
            """, (
                int(id_categoria),
                pregunta,
                respuesta,
                palabras_clave or None
            ))

            conexion.commit()

            return redirect('/admin/preguntas')

        return render_template(
            'admin_nueva_pregunta.html',
            categorias=categorias
        )

    except mysql.connector.Error as error:
        conexion.rollback()
        print("ERROR AL AGREGAR PREGUNTA:", error)
        return "No se pudo guardar la pregunta.", 500

    finally:
        cursor.close()



@app.route('/admin/preguntas/editar/<int:id_pregunta>', methods=['GET', 'POST'])
def editar_pregunta(id_pregunta):

    # Verificar que sea administrador
    if 'id_usuario' not in session:
        return redirect('/login')

    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo administradores.", 403

    cursor = conexion.cursor(dictionary=True)

    try:
        # Obtener la pregunta existente
        cursor.execute("""
            SELECT id_pregunta, id_categoria, pregunta,
                   respuesta, palabras_clave, estado
            FROM preguntas_frecuentes
            WHERE id_pregunta = %s
        """, (id_pregunta,))

        pregunta = cursor.fetchone()

        if not pregunta:
            return "Pregunta no encontrada.", 404

        # Obtener categorías
        cursor.execute("""
            SELECT id_categoria, nombre
            FROM categorias
            ORDER BY nombre
        """)
        
        categorias = cursor.fetchall()

        # Guardar modificaciones realizadas por el administrador
        if request.method == 'POST':
            nueva_pregunta = request.form.get('pregunta', '').strip()
            nueva_respuesta = request.form.get('respuesta', '').strip()
            palabras_clave = request.form.get('palabras_clave', '').strip()
            id_categoria = request.form.get('id_categoria', '').strip()

            if not nueva_pregunta or not nueva_respuesta or not id_categoria:
                return render_template(
                    'admin_editar_pregunta.html',
                    pregunta=pregunta,
                    categorias=categorias,
                    error='Completa todos los campos obligatorios.'
                )

            if len(nueva_pregunta) > 500 or len(palabras_clave) > 500:
                return render_template(
                    'admin_editar_pregunta.html',
                    pregunta=pregunta,
                    categorias=categorias,
                    error='La pregunta o las palabras clave superan 500 caracteres.'
                )

            if not id_categoria.isdigit() or not any(
                str(c['id_categoria']) == id_categoria
                for c in categorias
            ):
                return render_template(
                    'admin_editar_pregunta.html',
                    pregunta=pregunta,
                    categorias=categorias,
                    error='Selecciona una categoría válida.'
                )

            cursor.execute("""
                UPDATE preguntas_frecuentes
                SET pregunta = %s,
                    respuesta = %s,
                    palabras_clave = %s,
                    id_categoria = %s
                WHERE id_pregunta = %s
            """, (
                nueva_pregunta,
                nueva_respuesta,
                palabras_clave or None,
                int(id_categoria),
                id_pregunta
            ))

            conexion.commit()
            return redirect('/admin/preguntas')

        return render_template(
            'admin_editar_pregunta.html',
            pregunta=pregunta,
            categorias=categorias
        )


    finally:
        cursor.close()


@app.route('/admin/preguntas/cambiar-estado/<int:id_pregunta>', methods=['POST'])
def cambiar_estado_pregunta(id_pregunta):

    # Verificar que el usuario haya iniciado sesión
    if 'id_usuario' not in session:
        return redirect('/login')

    # Permitir únicamente administradores
    if session.get('rol') != 'administrador':
        return "Acceso denegado. Solo administradores.", 403

    cursor = conexion.cursor(dictionary=True)

    try:
        # Consultar el estado actual de la pregunta
        cursor.execute("""
            SELECT estado
            FROM preguntas_frecuentes
            WHERE id_pregunta = %s
        """, (id_pregunta,))

        pregunta = cursor.fetchone()

        if not pregunta:
            return "Pregunta no encontrada.", 404

        # Cambiar el estado: activa a inactiva o viceversa
        nuevo_estado = 0 if pregunta['estado'] == 1 else 1

        cursor.execute("""
            UPDATE preguntas_frecuentes
            SET estado = %s
            WHERE id_pregunta = %s
        """, (nuevo_estado, id_pregunta))

        conexion.commit()

        return redirect('/admin/preguntas')

    except Exception:
        conexion.rollback()
        raise

    finally:
        cursor.close()


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
            respuesta='Por favor, escribe una pregunta para continuar.'
        )

    cursor = conexion.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pregunta, respuesta, palabras_clave
            FROM preguntas_frecuentes
            WHERE estado = 1
        """)
        registros = cursor.fetchall()
    finally:
        cursor.close()

    respuesta = None
    pregunta_normalizada = normalizar_texto(pregunta_usuario)

    # 1. Priorizar preguntas idénticas registradas en MySQL.
    if registros:
        for registro in registros:
            if pregunta_normalizada == normalizar_texto(registro['pregunta']):
                respuesta = registro['respuesta']
                break

    # 2. Buscar coincidencias cuando no hay pregunta idéntica.
    if respuesta is None and registros:

        preguntas_bd = [
            normalizar_texto(
                registro['pregunta'] + ' ' +
                registro['pregunta'] + ' ' +
                (registro['palabras_clave'] or '')
            )
            for registro in registros
        ]

        textos = preguntas_bd + [pregunta_normalizada]

        vectorizador = TfidfVectorizer(
            lowercase=True,
            strip_accents='unicode',
            analyzer='word',
            ngram_range=(1, 2),
            stop_words=[
                'donde', 'puedo', 'mi', 'mis', 'de', 'del',
                'la', 'el', 'los', 'las', 'en', 'un', 'una',
                'universidad', 'umg'
            ]
        )

        try:
            matriz = vectorizador.fit_transform(textos)
            similitudes = cosine_similarity(
                matriz[-1:], matriz[:-1]
            ).flatten()
        except ValueError:
            similitudes = None

        if similitudes is not None:

            similitudes_ajustadas = similitudes.copy()

            # Detectar la intención de la pregunta.
            palabras_usuario = set(pregunta_normalizada.split())

            grupos_intencion = {
                'extranjero': {
                    'extranjero', 'extranjeros',
                    'extranjera', 'extranjeras'
                },
                'traslado': {
                    'traslado', 'trasladarme', 'transferencia'
                },
                'empleo': {
                    'trabajar', 'empleo', 'laboral', 'salidas'
                },
                'materias': {
                    'cursos', 'asignaturas',
                    'materias', 'materia'
                },
                'descripcion_carrera': {
                    'informacion', 'informarme', 'trata',
                    'consiste', 'estudia', 'estudiar', 'carrera'
                },
                'pensum': {
                    'malla', 'pensum', 'plan'
                }
            }

            intencion_usuario = next(
                (
                    nombre
                    for nombre, palabras in grupos_intencion.items()
                    if palabras_usuario.intersection(palabras)
                ),
                None
            )

            if intencion_usuario:
                for i, registro in enumerate(registros):
                    palabras_bd = set(
                        normalizar_texto(
                            registro['pregunta']
                        ).split()
                    )

                    if palabras_bd.intersection(
                        grupos_intencion[intencion_usuario]
                    ):
                        similitudes_ajustadas[i] += 0.15

            # 3. Reconocer ciclos académicos.
            import re

            equivalencias_ciclos = {
                'primero': 1,
                'primer': 1,
                'segundo': 2,
                'tercero': 3,
                'tercer': 3,
                'cuarto': 4,
                'quinto': 5,
                'sexto': 6,
                'septimo': 7,
                'setimo': 7,
                'octavo': 8,
                'noveno': 9,
                'decimo': 10,
                'undecimo': 11
            }

            def obtener_ciclo(texto):
                texto = normalizar_texto(texto)

                patron = (
                    r'\b(\d{1,2})(?:er|do|ro|to|vo|mo)?'
                    r'\s*(?:ciclo|semestre)\b'
                )

                encontrado = re.search(patron, texto)

                if encontrado:
                    return int(encontrado.group(1))

                for palabra, numero in equivalencias_ciclos.items():
                    if re.search(
                        r'\b' + palabra +
                        r'\s+(?:ciclo|semestre)\b',
                        texto
                    ):
                        return numero

                return None

            ciclo_solicitado = obtener_ciclo(pregunta_usuario)

            if ciclo_solicitado is not None:
                for i, registro in enumerate(registros):
                    ciclo_registrado = obtener_ciclo(
                        registro['pregunta']
                    )

                    if ciclo_registrado != ciclo_solicitado:
                        similitudes_ajustadas[i] = -1

            # 4. Evitar respuestas de una carrera diferente.
            carreras = {
                'ingenieria en sistemas': [
                    'ingenieria en sistemas',
                    'ingenieria de sistemas'
                ],
                'derecho': [
                    'derecho',
                    'ciencias juridicas'
                ],
                'administracion de empresas': [
                    'administracion de empresas'
                ],
                'psicologia': [
                    'psicologia'
                ],
                'trabajo social': [
                    'trabajo social'
                ]
            }

            carrera_solicitada = None

            for carrera, nombres in carreras.items():
                if any(
                    nombre in pregunta_normalizada
                    for nombre in nombres
                ):
                    carrera_solicitada = carrera
                    break

            if carrera_solicitada:
                for i, registro in enumerate(registros):
                    pregunta_bd = normalizar_texto(
                        registro['pregunta']
                    )

                    for carrera, nombres in carreras.items():
                        if carrera != carrera_solicitada:
                            if any(
                                nombre in pregunta_bd
                                for nombre in nombres
                            ):
                                similitudes_ajustadas[i] = -1
                                break

            # 5. Calcular la mejor coincidencia para TODAS
            # las preguntas, no solamente las de carreras.
            mejor_indice = int(
                similitudes_ajustadas.argmax()
            )

            mejor_similitud = float(
                similitudes_ajustadas[mejor_indice]
            )

            print(
                'Pregunta seleccionada:',
                registros[mejor_indice]['pregunta']
            )
            print('Similitud:', mejor_similitud)

            if mejor_similitud >= 0.35:
                respuesta = registros[mejor_indice]['respuesta']

    # 6. Guardar las preguntas que no se pudieron responder.
    if respuesta is None:
        respuesta = (
            'Lo siento, no encontré información '
            'relacionada con tu consulta.'
        )

        guardar_consulta_no_resuelta(pregunta_usuario)

    # 7. Guardar la conversación y mostrar la respuesta.
    guardar_conversacion(pregunta_usuario, respuesta)

    return render_template(
        'index.html',
        pregunta=pregunta_usuario,
        respuesta=respuesta
    )


if __name__ == '__main__':
    app.run(debug=False)