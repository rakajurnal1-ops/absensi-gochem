from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
import os
import base64
from datetime import datetime
from geopy.geocoders import Nominatim
from werkzeug.utils import secure_filename
from fpdf import FPDF

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gochem_globalindo_2026_pro_secure'

# =========================================================================
# PERBAIKAN PATH UNTUK PYTHONANYWHERE (ABSOLUTE PATH)
# =========================================================================
basedir = os.path.abspath(os.path.dirname(__file__))

# Database disimpan di dalam folder 'instance' dengan alamat absolut
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'gochem_attendance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Folder untuk Upload Absensi dan Foto Profil dengan alamat absolut
UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
PROFILE_FOLDER = os.path.join(basedir, 'static', 'profiles')

# Pastikan semua folder dibuat otomatis oleh server jika belum ada
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)
# =========================================================================

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

geolocator = Nominatim(user_agent="gochem_attendance_app_2026")

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='karyawan')
    
    nama_lengkap = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    nik = db.Column(db.String(20))
    jabatan = db.Column(db.String(50))
    foto_profil = db.Column(db.String(200), default='default.jpg')
    
    attendances = db.relationship('Attendance', backref='karyawan', lazy=True, cascade="all, delete-orphan")

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))
    location_name = db.Column(db.String(255))
    image_path = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='@GoChem04', role='admin', nama_lengkap='Administrator', jabatan='System Owner')
        db.session.add(admin)
        db.session.commit()

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login Gagal! Username atau password salah.')
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    today = datetime.now().strftime('%Y-%m-%d')
    logs = Attendance.query.filter(Attendance.user_id == current_user.id, Attendance.timestamp.contains(today)).order_by(Attendance.id.desc()).all()
    return render_template('index.html', logs=logs)

@app.route('/update_profile_photo', methods=['POST'])
@login_required
def update_profile_photo():
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            filename = secure_filename(f"user_{current_user.id}_{int(datetime.now().timestamp())}.{ext}")
            
            # Hapus foto lama jika bukan default
            if current_user.foto_profil and current_user.foto_profil != 'default.jpg':
                old_path = os.path.join(PROFILE_FOLDER, current_user.foto_profil)
                if os.path.exists(old_path):
                    os.remove(old_path)

            file.save(os.path.join(PROFILE_FOLDER, filename))
            current_user.foto_profil = filename
            db.session.commit()
    return redirect(url_for('index'))

@app.route('/admin_dashboard')
@login_required
@admin_required
def admin_dashboard():
    selected_date = request.args.get('date')
    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')
        
    logs = Attendance.query.filter(Attendance.timestamp.contains(selected_date)).order_by(Attendance.id.desc()).all()
    return render_template('admin_dashboard.html', logs=logs, selected_date=selected_date)

@app.route('/delete_absen/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_absen(id):
    log_to_delete = Attendance.query.get_or_404(id)
    
    if log_to_delete.image_path:
        filepath = os.path.join(UPLOAD_FOLDER, log_to_delete.image_path)
        if os.path.exists(filepath):
            os.remove(filepath)
            
    db.session.delete(log_to_delete)
    db.session.commit()
    flash('Data absensi berhasil dihapus!')
    
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/export_pdf')
@login_required
@admin_required
def export_pdf():
    selected_date = request.args.get('date')
    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')
        
    logs = Attendance.query.filter(Attendance.timestamp.contains(selected_date)).order_by(Attendance.id.desc()).all()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    pdf.cell(190, 10, f"Laporan Absensi Harian - PT. Gochem Globalindo", 0, 1, 'C')
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(190, 10, f"Tanggal: {selected_date}", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(50, 10, 'Nama Karyawan', 1, 0, 'C')
    pdf.cell(40, 10, 'Waktu', 1, 0, 'C')
    pdf.cell(100, 10, 'Lokasi', 1, 1, 'C')
    
    pdf.set_font("Arial", '', 9)
    for log in logs:
        nama = log.karyawan.nama_lengkap or log.karyawan.username
        waktu = log.timestamp.split(' ')[1] if ' ' in log.timestamp else log.timestamp
        lokasi = log.location_name
        
        if len(lokasi) > 60:
            lokasi = lokasi[:57] + "..."
            
        pdf.cell(50, 10, str(nama), 1, 0, 'L')
        pdf.cell(40, 10, str(waktu), 1, 0, 'C')
        pdf.cell(100, 10, str(lokasi).encode('latin-1', 'replace').decode('latin-1'), 1, 1, 'L')
        
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Data_Absensi_{selected_date}.pdf'
    return response

@app.route('/absen', methods=['POST'])
@login_required
def absen():
    data = request.json
    try:
        lat, lon = data.get('latitude'), data.get('longitude')
        try:
            # Catatan: Akun gratis PythonAnywhere membatasi akses API luar.
            # Jika geolocator gagal/lambat, try-except ini akan mengamankan agar tidak crash.
            location = geolocator.reverse(f"{lat}, {lon}", language='id')
            alamat = location.address if location else "Lokasi tidak terdeteksi"
        except:
            alamat = "Lokasi tidak terdeteksi"
        
        image_data = data['image'].split(",")[1]
        filename = f"{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as fh: 
            fh.write(base64.b64decode(image_data))
        
        new_attendance = Attendance(user_id=current_user.id, timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), latitude=str(lat), longitude=str(lon), location_name=alamat, image_path=filename)
        db.session.add(new_attendance)
        db.session.commit()
        return jsonify({"message": f"Absensi Berhasil: {alamat[:40]}..."})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500

@app.route('/user')
@login_required
@admin_required
def user():
    return render_template('user.html', users=User.query.all())

@app.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    foto_filename = 'default.jpg'
    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename != '':
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            foto_filename = secure_filename(f"profile_{request.form.get('username')}_{int(datetime.now().timestamp())}.{ext}")
            file.save(os.path.join(PROFILE_FOLDER, foto_filename))

    new_user = User(
        username=request.form.get('username'),
        password=request.form.get('password'),
        role=request.form.get('role'),
        nama_lengkap=request.form.get('nama_lengkap'),
        nik=request.form.get('nik'),
        gender=request.form.get('gender'),
        jabatan=request.form.get('jabatan'),
        foto_profil=foto_filename
    )
    db.session.add(new_user)
    db.session.commit()
    flash('Karyawan berhasil ditambahkan!')
    return redirect(url_for('user'))

@app.route('/delete_user/<int:id>')
@login_required
@admin_required
def delete_user(id):
    user_to_delete = User.query.get_or_404(id)
    if user_to_delete.id != current_user.id:
        if user_to_delete.foto_profil and user_to_delete.foto_profil != 'default.jpg':
            old_path = os.path.join(PROFILE_FOLDER, user_to_delete.foto_profil)
            if os.path.exists(old_path):
                os.remove(old_path)
                
        db.session.delete(user_to_delete)
        db.session.commit()
        flash('Data karyawan berhasil dihapus!')
    return redirect(url_for('user'))

@app.route('/update_profile_data', methods=['POST'])
@login_required
def update_profile_data():
    current_user.nama_lengkap = request.form.get('nama_lengkap')
    current_user.nik = request.form.get('nik')
    current_user.jabatan = request.form.get('jabatan')
    current_user.gender = request.form.get('gender')
    db.session.commit()
    flash('Profil berhasil diperbarui!')
    return redirect(url_for('index'))

@app.route('/edit_user/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if 'foto' in request.files:
        file = request.files['foto']
        if file and file.filename != '':
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
            filename = secure_filename(f"profile_{request.form.get('username')}_{int(datetime.now().timestamp())}.{ext}")
            
            if user.foto_profil and user.foto_profil != 'default.jpg':
                old_path = os.path.join(PROFILE_FOLDER, user.foto_profil)
                if os.path.exists(old_path):
                    os.remove(old_path)
                    
            file.save(os.path.join(PROFILE_FOLDER, filename))
            user.foto_profil = filename

    new_password = request.form.get('password')
    if new_password and new_password.strip() != '':
        user.password = new_password

    user.username = request.form.get('username')
    user.role = request.form.get('role')
    user.nama_lengkap = request.form.get('nama_lengkap')
    user.nik = request.form.get('nik')
    user.jabatan = request.form.get('jabatan')
    user.gender = request.form.get('gender')
    
    db.session.commit()
    flash(f'Data karyawan {user.nama_lengkap} berhasil diperbarui!')
    return redirect(url_for('user'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# PythonAnywhere akan mengabaikan blok ini karena mereka menggunakan file WSGI eksternal.
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)