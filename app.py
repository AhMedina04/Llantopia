import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import cloudinary
import cloudinary.uploader
import cloudinary.api

app = Flask(__name__)
app.secret_key = 'clave_secreta_libreria_pro_v2'

# Configuración de Cloudinary (para almacenamiento persistente en la nube)
cloudinary.config(
  cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
  api_key = os.getenv('CLOUDINARY_API_KEY'),
  api_secret = os.getenv('CLOUDINARY_API_SECRET'),
  secure = True
)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configuración dinámica de la base de datos (Compatible con Render y Localhost)
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'postgresql+psycopg2://postgres:N-bk&!0LhmvS~G~(DkTmDWq>M1+#?:@localhost:5432/LibreriaVirtual2'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

CORREOS_AUTORIZADOS = [
    "anhuarmedrod@gmail.com", 
    "perlaaguirre890@gmail.com"
]

# ==========================================
# MODELOS DE BASE DE DATOS
# ==========================================
class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    contrasena = db.Column(db.String(255), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

class Libro(db.Model):
    __tablename__ = 'libros'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    autor = db.Column(db.String(100), nullable=False)
    sinopsis = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(50), nullable=False) 
    categoria = db.Column(db.String(200), nullable=False)
    archivo = db.Column(db.String(500), nullable=False)  # Ampliado para soportar URLs largas de Cloudinary
    interacciones = db.Column(db.Integer, default=0) 
    ultima_interaccion = db.Column(db.DateTime, nullable=True) 
    fecha_subida = db.Column(db.DateTime, default=datetime.now)

class Favorito(db.Model):
    __tablename__ = 'favoritos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    libro_id = db.Column(db.Integer, db.ForeignKey('libros.id'), nullable=False)

class Resena(db.Model):
    __tablename__ = 'resenas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    libro_id = db.Column(db.Integer, db.ForeignKey('libros.id'), nullable=False)
    calificacion = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text, nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    usuario = db.relationship('Usuario', backref='resenas')

class MetaLectura(db.Model):
    __tablename__ = 'metas_lectura'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, unique=True)
    meta_anual = db.Column(db.Integer, default=12)

class HistorialUsuario(db.Model):
    __tablename__ = 'historial_usuario'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    libro_id = db.Column(db.Integer, db.ForeignKey('libros.id'), nullable=False)
    ultima_interaccion = db.Column(db.DateTime, default=datetime.now)
    oculto = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# ==========================================
# FUNCIÓN AUXILIAR PARA CALIFICACIONES
# ==========================================
def enriquecer_libros(lista_libros):
    for l in lista_libros:
        resenas = Resena.query.filter_by(libro_id=l.id).all()
        if resenas:
            promedio = sum(r.calificacion for r in resenas) / len(resenas)
            l.promedio_calificacion = round(promedio, 1)
            l.total_resenas = len(resenas)
        else:
            l.promedio_calificacion = 0.0
            l.total_resenas = 0
    return lista_libros

# ==========================================
# RUTAS DE LA APLICACIÓN
# ==========================================

@app.route('/')
def bienvenida():
    return render_template('bienvenida.html')

@app.route('/invitado')
def invitado():
    session.clear()
    session['nombre_usuario'] = "Invitado"
    return redirect(url_for('pagina_principal'))

@app.route('/main')
def pagina_principal():
    es_invitado = session.get('nombre_usuario') == "Invitado" or 'usuario_id' not in session
    
    continuar = []
    if not es_invitado:
        usuario_id = session['usuario_id']
        libros_ocultos_ids = [h.libro_id for h in HistorialUsuario.query.filter_by(usuario_id=usuario_id, oculto=True).all()]
        
        continuar = Libro.query.filter(
            Libro.ultima_interaccion != None,
            ~Libro.id.in_(libros_ocultos_ids) if libros_ocultos_ids else True
        ).order_by(Libro.ultima_interaccion.desc()).limit(6).all()
        enriquecer_libros(continuar)
    
    page = request.args.get('page', 1, type=int)
    libros_pagination = Libro.query.filter(Libro.tipo.notilike('%audiolibro%')).order_by(Libro.fecha_subida.desc()).paginate(page=page, per_page=8, error_out=False)
    enriquecer_libros(libros_pagination.items)
    
    audiolibros = Libro.query.filter(Libro.tipo.ilike('%audiolibro%')).all()
    enriquecer_libros(audiolibros)

    populares = Libro.query.order_by(Libro.interacciones.desc()).limit(6).all()
    enriquecer_libros(populares)

    estudio = Libro.query.filter(Libro.categoria.ilike('%estudio%')).all()
    enriquecer_libros(estudio)

    libros_favoritos_ids = []
    if 'usuario_id' in session:
        favs = Favorito.query.filter_by(usuario_id=session['usuario_id']).all()
        libros_favoritos_ids = [f.libro_id for f in favs]

    return render_template('main.html', 
                           continuar=continuar, 
                           libros=libros_pagination.items,
                           pagination=libros_pagination,
                           audiolibros=audiolibros, 
                           populares=populares, 
                           estudio=estudio,
                           libros_favoritos_ids=libros_favoritos_ids)

# API PARA BÚSQUEDA EN TIEMPO REAL (LIVE SEARCH)
@app.route('/api/buscar_live')
def buscar_live():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])

    resultados = Libro.query.filter(
        (Libro.titulo.ilike(f'%{query}%')) | 
        (Libro.autor.ilike(f'%{query}%'))
    ).limit(5).all()

    enriquecer_libros(resultados)

    data = [{
        'id': l.id,
        'titulo': l.titulo,
        'autor': l.autor,
        'tipo': l.tipo,
        'promedio': l.promedio_calificacion,
        'es_audio': 'audiolibro' in l.tipo.lower(),
        'archivo': l.archivo if l.archivo.startswith('http') else url_for('static', filename='uploads/' + l.archivo)
    } for l in resultados]

    return jsonify(data)

# RUTA PARA FILTRAR POR MÚLTIPLES CATEGORÍAS
@app.route('/filtrar', methods=['GET'])
def filtrar_multicategoria():
    page = request.args.get('page', 1, type=int)
    orden = request.args.get('orden', 'reciente')
    categorias_seleccionadas = request.args.getlist('cat')
    
    query = Libro.query

    for cat in categorias_seleccionadas:
        if cat:
            query = query.filter(Libro.categoria.ilike(f'%{cat}%'))

    if orden == 'popular':
        query = query.order_by(Libro.interacciones.desc())
    elif orden == 'alfabetico':
        query = query.order_by(Libro.titulo.asc())
    else:
        query = query.order_by(Libro.fecha_subida.desc())

    libros_pagination = query.paginate(page=page, per_page=8, error_out=False)
    enriquecer_libros(libros_pagination.items)

    libros_favoritos_ids = []
    if 'usuario_id' in session:
        favs = Favorito.query.filter_by(usuario_id=session['usuario_id']).all()
        libros_favoritos_ids = [f.libro_id for f in favs]

    titulo_seccion = "Filtro: " + ", ".join(categorias_seleccionadas) if categorias_seleccionadas else "Todas las categorías"

    return render_template('categoria_detalles.html', 
                           categoria=titulo_seccion, 
                           libros=libros_pagination.items,
                           pagination=libros_pagination,
                           orden_actual=orden,
                           categorias_activas=categorias_seleccionadas,
                           libros_favoritos_ids=libros_favoritos_ids)

@app.route('/agregar_resena/<int:libro_id>', methods=['POST'])
def agregar_resena(libro_id):
    if 'usuario_id' not in session or session.get('nombre_usuario') == 'Invitado':
        return jsonify({'error': 'Debes iniciar sesión para calificar.'}), 401
    
    data = request.get_json()
    calificacion = data.get('calificacion')
    comentario = data.get('comentario', '').strip()

    if not calificacion or not (1 <= int(calificacion) <= 5):
        return jsonify({'error': 'Calificación inválida.'}), 400

    usuario_id = session['usuario_id']
    resena_existente = Resena.query.filter_by(usuario_id=usuario_id, libro_id=libro_id).first()
    
    if resena_existente:
        resena_existente.calificacion = int(calificacion)
        resena_existente.comentario = comentario
        resena_existente.fecha = datetime.now()
    else:
        nueva_resena = Resena(usuario_id=usuario_id, libro_id=libro_id, calificacion=int(calificacion), comentario=comentario)
        db.session.add(nueva_resena)

    db.session.commit()
    return jsonify({'status': 'success', 'mensaje': 'Reseña guardada con éxito'})

@app.route('/obtener_resenas/<int:libro_id>')
def obtener_resenas(libro_id):
    resenas = Resena.query.filter_by(libro_id=libro_id).order_by(Resena.fecha.desc()).all()
    promedio = 0
    if resenas:
        promedio = round(sum(r.calificacion for r in resenas) / len(resenas), 1)

    usuario_actual_id = session.get('usuario_id')
    es_admin = session.get('correo_usuario') in CORREOS_AUTORIZADOS

    lista_resenas = [{
        'id': r.id,
        'usuario_id': r.usuario_id,
        'usuario': r.usuario.nombre,
        'calificacion': r.calificacion,
        'comentario': r.comentario,
        'fecha': r.fecha.strftime('%d/%m/%Y'),
        'puede_eliminar': (r.usuario_id == usuario_actual_id) or es_admin
    } for r in resenas]

    return jsonify({'promedio': promedio, 'total': len(resenas), 'resenas': lista_resenas})

@app.route('/eliminar_resena/<int:resena_id>', methods=['DELETE'])
def eliminar_resena(resena_id):
    if 'usuario_id' not in session or session.get('nombre_usuario') == 'Invitado':
        return jsonify({'error': 'No autorizado'}), 401
    
    resena = Resena.query.get_or_404(resena_id)
    usuario_id = session['usuario_id']
    es_admin = session.get('correo_usuario') in CORREOS_AUTORIZADOS
    
    if resena.usuario_id == usuario_id or es_admin:
        db.session.delete(resena)
        db.session.commit()
        return jsonify({'status': 'success', 'mensaje': 'Reseña eliminada con éxito.'})
    else:
        return jsonify({'error': 'No tienes permisos para eliminar esta reseña.'}), 403

@app.route('/ocultar_historial/<int:libro_id>', methods=['POST'])
def ocultar_historial(libro_id):
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    usuario_id = session['usuario_id']
    registro = HistorialUsuario.query.filter_by(usuario_id=usuario_id, libro_id=libro_id).first()
    if registro:
        registro.oculto = True
    else:
        nuevo_reg = HistorialUsuario(usuario_id=usuario_id, libro_id=libro_id, oculto=True)
        db.session.add(nuevo_reg)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/explorar')
def explorar():
    page = request.args.get('page', 1, type=int)
    orden = request.args.get('orden', 'reciente')
    
    query = Libro.query
        
    if orden == 'popular':
        query = query.order_by(Libro.interacciones.desc())
    elif orden == 'alfabetico':
        query = query.order_by(Libro.titulo.asc())
    else:
        query = query.order_by(Libro.fecha_subida.desc())

    libros_pagination = query.paginate(page=page, per_page=8, error_out=False)
    enriquecer_libros(libros_pagination.items)
        
    libros_favoritos_ids = []
    if 'usuario_id' in session:
        favs = Favorito.query.filter_by(usuario_id=session['usuario_id']).all()
        libros_favoritos_ids = [f.libro_id for f in favs]

    return render_template('categoria_detalles.html', 
                           categoria="Explorar", 
                           libros=libros_pagination.items,
                           pagination=libros_pagination,
                           orden_actual=orden,
                           libros_favoritos_ids=libros_favoritos_ids)

@app.route('/categoria/<nombre_categoria>')
def ver_categoria(nombre_categoria):
    page = request.args.get('page', 1, type=int)
    orden = request.args.get('orden', 'reciente')
    
    query = Libro.query
    cat_lower = nombre_categoria.lower()
    
    if cat_lower == 'libros':
        query = query.filter(Libro.tipo.notilike('%audiolibro%'))
    elif cat_lower == 'audiolibros':
        query = query.filter(Libro.tipo.ilike('%audiolibro%'))
    elif cat_lower == 'populares':
        query = query.filter(Libro.interacciones > 0)
    elif cat_lower == 'estudio':
        query = query.filter(Libro.categoria.ilike('%estudio%'))
    elif cat_lower == 'continuar':
        es_invitado = session.get('nombre_usuario') == "Invitado" or 'usuario_id' not in session
        if es_invitado:
            query = query.filter(False)
        else:
            usuario_id = session['usuario_id']
            libros_ocultos_ids = [h.libro_id for h in HistorialUsuario.query.filter_by(usuario_id=usuario_id, oculto=True).all()]
            query = query.filter(
                Libro.ultima_interaccion != None,
                ~Libro.id.in_(libros_ocultos_ids) if libros_ocultos_ids else True
            )
    else:
        query = query.filter(Libro.categoria.ilike(f'%{nombre_categoria}%'))
        
    if orden == 'popular':
        query = query.order_by(Libro.interacciones.desc())
    elif orden == 'alfabetico':
        query = query.order_by(Libro.titulo.asc())
    else:
        query = query.order_by(Libro.fecha_subida.desc())

    libros_pagination = query.paginate(page=page, per_page=8, error_out=False)
    enriquecer_libros(libros_pagination.items)
        
    libros_favoritos_ids = []
    if 'usuario_id' in session:
        favs = Favorito.query.filter_by(usuario_id=session['usuario_id']).all()
        libros_favoritos_ids = [f.libro_id for f in favs]

    return render_template('categoria_detalles.html', 
                           categoria=nombre_categoria.capitalize(), 
                           libros=libros_pagination.items,
                           pagination=libros_pagination,
                           orden_actual=orden,
                           libros_favoritos_ids=libros_favoritos_ids)

@app.route('/abrir/<int:libro_id>')
def abrir_libro(libro_id):
    if 'usuario_id' not in session and session.get('nombre_usuario') != 'Invitado':
        flash('Inicia sesión para ver o escuchar el material.', 'danger')
        return redirect(url_for('iniciarSesion'))

    libro = Libro.query.get_or_404(libro_id)
    es_invitado = session.get('nombre_usuario') == "Invitado" or 'usuario_id' not in session
    if not es_invitado:
        libro.interacciones += 1
        libro.ultima_interaccion = datetime.now()
        usuario_id = session['usuario_id']
        hist_reg = HistorialUsuario.query.filter_by(usuario_id=usuario_id, libro_id=libro_id).first()
        if hist_reg:
            hist_reg.oculto = False
            hist_reg.ultima_interaccion = datetime.now()
        else:
            nuevo_hist = HistorialUsuario(usuario_id=usuario_id, libro_id=libro_id, oculto=False)
            db.session.add(nuevo_hist)
        db.session.commit()

    if 'audiolibro' in libro.tipo.lower():
        return render_template('reproductor_audio.html', libro=libro)
    else:
        return render_template('visor.html', libro=libro)

@app.route('/toggle_favorito/<int:libro_id>', methods=['POST'])
def toggle_favorito(libro_id):
    if 'usuario_id' not in session:
        return jsonify({'error': 'No autorizado'}), 401
    
    usuario_id = session['usuario_id']
    favorito = Favorito.query.filter_by(usuario_id=usuario_id, libro_id=libro_id).first()
    if favorito:
        db.session.delete(favorito)
        db.session.commit()
        estado = 'removido'
    else:
        nuevo_fav = Favorito(usuario_id=usuario_id, libro_id=libro_id)
        db.session.add(nuevo_fav)
        db.session.commit()
        estado = 'agregado'
    return jsonify({'status': 'success', 'estado': estado})

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'usuario_id' not in session or session.get('nombre_usuario') == 'Invitado':
        flash('Debes iniciar sesión con una cuenta para ver tu perfil.', 'danger')
        return redirect(url_for('iniciarSesion'))
    
    usuario_id = session['usuario_id']
    usuario = Usuario.query.get_or_404(usuario_id)
    meta_obj = MetaLectura.query.filter_by(usuario_id=usuario_id).first()
    
    if request.method == 'POST':
        if 'password_actual' in request.form:
            pass_actual = request.form.get('password_actual')
            pass_nueva = request.form.get('password_nueva')
            if check_password_hash(usuario.contrasena, pass_actual):
                usuario.contrasena = generate_password_hash(pass_nueva)
                db.session.commit()
                flash('¡Contraseña actualizada con éxito!', 'success')
            else:
                flash('La contraseña actual es incorrecta.', 'danger')
        elif 'meta_anual' in request.form:
            nueva_meta = int(request.form.get('meta_anual', 12))
            if meta_obj:
                meta_obj.meta_anual = nueva_meta
            else:
                meta_obj = MetaLectura(usuario_id=usuario_id, meta_anual=nueva_meta)
                db.session.add(meta_obj)
            db.session.commit()
            flash('¡Meta de lectura actualizada!', 'success')
        return redirect(url_for('perfil'))

    favoritos = db.session.query(Libro).join(Favorito).filter(Favorito.usuario_id == usuario_id).all()
    enriquecer_libros(favoritos)
    
    historial_general = Libro.query.filter(Libro.ultima_interaccion != None).order_by(Libro.ultima_interaccion.desc()).all()
    enriquecer_libros(historial_general)
    
    libros_leidos_historial = [l for l in historial_general if 'audiolibro' not in l.tipo.lower()]
    audiolibros_escuchados_historial = [l for l in historial_general if 'audiolibro' in l.tipo.lower()]
    
    libros_leidos_count = len(libros_leidos_historial)
    audiolibros_escuchados_count = len(audiolibros_escuchados_historial)
    
    meta_valor = meta_obj.meta_anual if meta_obj else 12
    porcentaje_meta = min(int((libros_leidos_count / meta_valor) * 100), 100) if meta_valor > 0 else 0

    total_usuarios = Usuario.query.count()
    total_libros = Libro.query.filter(Libro.tipo.notilike('%audiolibro%')).count()
    total_audiolibros = Libro.query.filter(Libro.tipo.ilike('%audiolibro%')).count()
    libro_mas_popular = Libro.query.order_by(Libro.interacciones.desc()).first()
    
    busqueda_admin = request.args.get('q_admin', '').strip()
    categoria_admin = request.args.get('cat_admin', '')
    
    libros_query = Libro.query
    if busqueda_admin:
        libros_query = libros_query.filter(
            (Libro.titulo.ilike(f'%{busqueda_admin}%')) | 
            (Libro.autor.ilike(f'%{busqueda_admin}%'))
        )
    if categoria_admin:
        libros_query = libros_query.filter(Libro.categoria.ilike(f'%{categoria_admin}%'))
        
    lista_libros_admin = libros_query.all() if usuario.correo in CORREOS_AUTORIZADOS else []
    enriquecer_libros(lista_libros_admin)
    lista_usuarios = Usuario.query.all() if usuario.correo in CORREOS_AUTORIZADOS else []

    return render_template('perfil.html', 
                           usuario=usuario, 
                           favoritos=favoritos, 
                           historial=libros_leidos_historial[:5], 
                           audiolibros_historial=audiolibros_escuchados_historial[:5],
                           libros_leidos_count=libros_leidos_count,
                           audiolibros_escuchados_count=audiolibros_escuchados_count,
                           meta_anual=meta_valor,
                           porcentaje_meta=porcentaje_meta,
                           total_usuarios=total_usuarios,
                           total_libros=total_libros,
                           total_audiolibros=total_audiolibros,
                           libro_mas_popular=libro_mas_popular,
                           lista_usuarios=lista_usuarios,
                           lista_libros_admin=lista_libros_admin,
                           busqueda_admin=busqueda_admin,
                           categoria_admin=categoria_admin,
                           es_admin=(usuario.correo in CORREOS_AUTORIZADOS))

@app.route('/admin/eliminar-usuario/<int:usuario_id>')
def eliminar_usuario(usuario_id):
    if session.get('correo_usuario') not in CORREOS_AUTORIZADOS:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('pagina_principal'))
    usuario_a_borrar = Usuario.query.get_or_404(usuario_id)
    if usuario_a_borrar.correo in CORREOS_AUTORIZADOS:
        flash('No puedes eliminar a un administrador autorizado.', 'danger')
    else:
        db.session.delete(usuario_a_borrar)
        db.session.commit()
        flash('Usuario eliminado del sistema con éxito.', 'success')
    return redirect(url_for('perfil'))

@app.route('/admin/eliminar-libro/<int:libro_id>')
def eliminar_libro(libro_id):
    if session.get('correo_usuario') not in CORREOS_AUTORIZADOS:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('pagina_principal'))
    libro_a_borrar = Libro.query.get_or_404(libro_id)
    
    # Intenta eliminar archivo local si existiera
    try:
        if not libro_a_borrar.archivo.startswith('http'):
            archivo_path = os.path.join(app.config['UPLOAD_FOLDER'], libro_a_borrar.archivo)
            if os.path.exists(archivo_path):
                os.remove(archivo_path)
    except Exception as e:
        print(f"Error al eliminar archivo físico local: {e}")

    Favorito.query.filter_by(libro_id=libro_id).delete()
    Resena.query.filter_by(libro_id=libro_id).delete()
    HistorialUsuario.query.filter_by(libro_id=libro_id).delete()

    db.session.delete(libro_a_borrar)
    db.session.commit()
    flash('Libro eliminado del sistema con éxito.', 'success')
    return redirect(url_for('perfil'))

@app.route('/buscar')
def buscar():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    if query:
        resultados_pagination = Libro.query.filter(
            (Libro.titulo.ilike(f'%{query}%')) | 
            (Libro.autor.ilike(f'%{query}%'))
        ).paginate(page=page, per_page=8, error_out=False)
        enriquecer_libros(resultados_pagination.items)
    else:
        resultados_pagination = None

    libros_favoritos_ids = []
    if 'usuario_id' in session:
        favs = Favorito.query.filter_by(usuario_id=session['usuario_id']).all()
        libros_favoritos_ids = [f.libro_id for f in favs]

    return render_template('categoria_detalles.html', 
                           categoria=f'Resultados para: "{query}"', 
                           libros=resultados_pagination.items if resultados_pagination else [],
                           pagination=resultados_pagination,
                           orden_actual='reciente',
                           libros_favoritos_ids=libros_favoritos_ids)

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre_form = request.form['nombre']
        correo_form = request.form['correo']
        contrasena_form = request.form['contrasena']
        
        if Usuario.query.filter_by(correo=correo_form).first():
            flash('Este correo ya está registrado.', 'danger')
            return redirect(url_for('registro'))
            
        contrasena_hash = generate_password_hash(contrasena_form)
        
        nuevo_usuario = Usuario(nombre=nombre_form, correo=correo_form, contrasena=contrasena_hash)
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        session['usuario_id'] = nuevo_usuario.id
        session['nombre_usuario'] = nuevo_usuario.nombre
        session['correo_usuario'] = nuevo_usuario.correo
        flash('¡Registro exitoso!', 'success')
        return redirect(url_for('pagina_principal'))
    return render_template('registro.html')

@app.route('/iniciarSesion', methods=['GET', 'POST'])
def iniciarSesion():
    if request.method == 'POST':
        correo_form = request.form['correo']
        contrasena_form = request.form['contrasena']
        
        usuario = Usuario.query.filter_by(correo=correo_form).first()
        
        if usuario and check_password_hash(usuario.contrasena, contrasena_form):
            session['usuario_id'] = usuario.id
            session['nombre_usuario'] = usuario.nombre
            session['correo_usuario'] = usuario.correo
            flash(f'¡Bienvenido de nuevo, {usuario.nombre}!', 'success')
            return redirect(url_for('pagina_principal'))
        else:
            flash('Correo o contraseña incorrectos.', 'danger')
            return redirect(url_for('iniciarSesion'))
    return render_template('iniciarSesion.html')

@app.route('/cerrar-sesion')
def cerrar_sesion():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('bienvenida'))

@app.route('/agregar-libro', methods=['GET', 'POST'])
def agregar_libro():
    if session.get('correo_usuario') not in CORREOS_AUTORIZADOS:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('pagina_principal'))

    if request.method == 'POST':
        archivo = request.files.get('archivo')
        if archivo and archivo.filename != '':
            # Sube el archivo (PDF, MP3, etc.) directamente a Cloudinary
            try:
                # resource_type="auto" permite que Cloudinary detecte si es imagen, video o audio/archivo raw
                upload_result = cloudinary.uploader.upload(archivo, resource_type="auto")
                url_archivo = upload_result.get('secure_url')
            except Exception as e:
                flash(f'Error al subir el archivo a Cloudinary: {e}', 'danger')
                return redirect(url_for('agregar_libro'))
            
            categorias_lista = request.form.getlist('categorias')
            string_categorias = ", ".join(categorias_lista) if categorias_lista else "General"

            nuevo_libro = Libro(
                titulo=request.form['titulo'], 
                autor=request.form['autor'], 
                sinopsis=request.form['sinopsis'], 
                tipo=request.form['tipo'], 
                categoria=string_categorias, 
                archivo=url_archivo
            )
            db.session.add(nuevo_libro)
            db.session.commit()
            flash('¡Elemento agregado exitosamente a la nube!', 'success')
            return redirect(url_for('pagina_principal'))
    return render_template('agregar_libro.html')

@app.route('/guardados')
def ver_guardados():
    if 'usuario_id' not in session:
        flash('Debes iniciar sesión para ver tus libros guardados.', 'danger')
        return redirect(url_for('iniciarSesion'))
    usuario_id = session['usuario_id']
    favoritos = db.session.query(Libro).join(Favorito).filter(Favorito.usuario_id == usuario_id).all()
    enriquecer_libros(favoritos)
    return render_template('guardados.html', favoritos=favoritos)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)