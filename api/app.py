import os
import subprocess
import logging
import base64
import secrets
import zipfile
from datetime import datetime
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

from flask import Flask, request, render_template, send_from_directory, redirect, url_for, abort, session
from flask_wtf.csrf import CSRFProtect, validate_csrf
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
from functools import wraps

from gdrive_manager import GDriveManager
import psutil

# --- configuration ---

class Config:
    WORKDIR = "/workspace"
    LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
    # Use environment variable or generate secure token for auth
    AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
    if not AUTH_TOKEN:
        AUTH_TOKEN = secrets.token_urlsafe(32)
        print("WARNING: No AUTH_TOKEN environment variable set. Generated random token for this session.")
        print(f"Generated AUTH_TOKEN: {AUTH_TOKEN}")
    # Secret key for sessions
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    
    # Security settings
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {'.blend'}

app = Flask(__name__)
app.config.from_object(Config)

# Enable CSRF protection
csrf = CSRFProtect(app)

# Ensure secret key is set for sessions
if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'change-this-secret-key-in-production':
    import secrets
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    print("WARNING: Using auto-generated SECRET_KEY. Set SECRET_KEY environment variable for production.")

# Debug: Print configuration on startup
print(f"AUTH_TOKEN configured: '{app.config['AUTH_TOKEN']}'")
print(f"Environment AUTH_TOKEN: '{os.environ.get('AUTH_TOKEN', 'NOT SET')}'")

# Session-based auth decorator
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in via session
        if 'authenticated' not in session:
            return redirect(url_for('login', next=request.url))
        
        return f(*args, **kwargs)
    return decorated_function

# --- logging setup ---

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

file_handler = RotatingFileHandler(app.config["LOG_PATH"], maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# --- auth ---
# Token-based authentication - see require_auth decorator above

# --- helpers ---

class UploadForm(FlaskForm):
    file = FileField('Blend File', validators=[DataRequired()])
    submit = SubmitField('Upload')

def validate_blend_file(file_path):
    """Valide la structure d'un fichier .blend"""
    try:
        # Vérifier la signature du fichier .blend
        with open(file_path, 'rb') as f:
            header = f.read(12)
            if not header.startswith(b'BLENDER'):
                return False, "Invalid .blend file signature"
        
        # Vérifier la taille du fichier
        file_size = os.path.getsize(file_path)
        if file_size > app.config.get('MAX_FILE_SIZE', 100 * 1024 * 1024):
            return False, f"File too large (max {app.config.get('MAX_FILE_SIZE', 100 * 1024 * 1024) // (1024*1024)}MB)"
        
        return True, "Valid"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def scan_blend_for_scripts(file_path):
    """Scanne un fichier .blend pour détecter des scripts Python suspects"""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
            # Rechercher des patterns suspects
            suspicious_patterns = [
                b'import os',
                b'subprocess',
                b'exec(',
                b'eval(',
                b'__import__',
                b'open(',
                b'file(',
                b'input(',
                b'raw_input',
                b'system(',
                b'popen('
            ]
            
            for pattern in suspicious_patterns:
                if pattern in content:
                    return True, f"Suspicious pattern found: {pattern.decode('utf-8', errors='ignore')}"
        
        return False, "No suspicious scripts detected"
    except Exception as e:
        return True, f"Error scanning file: {str(e)}"

def get_blend_files():
    try:
        return [f for f in GDriveManager().list_files() if f["name"].endswith(".blend")]
    except Exception as e:
        logger.error(f"Failed to fetch GDrive files: {e}")
        return []

def get_rendered_images():
    output_dir = os.path.join(app.config["WORKDIR"], "output")
    try:
        return sorted([f for f in os.listdir(output_dir) if f.endswith(".png")])
    except Exception:
        return []

def render_index(error=None, job=None, img_b64=None):
    return render_template(
        "index.html",
        error=error,
        job=job,
        img_b64=img_b64,
        gdrive_files=get_blend_files(),
        rendered_images=get_rendered_images(),
        logout_url=url_for("logout")
    )

def is_locked(path):
    return os.path.exists(path + ".lock")

def create_lock(path):
    with open(path + ".lock", "w") as f:
        f.write("locked")

def remove_lock(path):
    try:
        os.remove(path + ".lock")
    except FileNotFoundError:
        pass

@contextmanager
def render_lock(path):
    if is_locked(path):
        raise RuntimeError("File is currently being rendered.")
    create_lock(path)
    try:
        yield
    finally:
        remove_lock(path)

# --- routes ---

@app.route("/login", methods=["GET", "POST"])
def login():
    print(f"Login route called - Method: {request.method}")
    
    if request.method == "POST":
        token = request.form.get("token")
        expected_token = app.config["AUTH_TOKEN"]        
        print(f"Token received: '{token}'")
        print(f"Expected token: '{expected_token}'")
        print(f"Tokens match: {token == expected_token}")
        
        if token == expected_token:
            session["authenticated"] = True
            print("Login successful - session set")
            next_url = request.args.get("next") or url_for("index")
            print(f"Redirecting to: {next_url}")
            return redirect(next_url)
        else:
            print("Login failed - invalid token")
            return render_template("login.html", error="Invalid token")
    
    print("Showing login form")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))

# Route de debug supprimée pour des raisons de sécurité

@app.route("/", methods=["GET"])
@require_auth
def index():
    return render_index()

@app.route("/", methods=["POST"])
@require_auth
def upload():
    upload_dir = os.path.join(app.config["WORKDIR"], "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Valider le token CSRF
    try:
        validate_csrf(request.form.get('csrf_token'))
    except Exception:
        return render_index(error="CSRF token validation failed")

    if "file" not in request.files:
        return render_index(error="No file part in request")

    f = request.files["file"]
    if f.filename == "":
        return render_index(error="No selected file")

    # Validation de l'extension
    if not f.filename.lower().endswith('.blend'):
        return render_index(error="Only .blend files are allowed")

    filename = secure_filename(f.filename)
    blend_path = os.path.join(upload_dir, filename)

    if is_locked(blend_path):
        return render_index(error="File is currently being rendered.")

    f.save(blend_path)
    
    # Valider le fichier .blend
    is_valid, message = validate_blend_file(blend_path)
    if not is_valid:
        os.remove(blend_path)  # Supprimer le fichier invalide
        return render_index(error=f"Invalid file: {message}")
    
    # Scanner pour des scripts suspects
    has_scripts, script_message = scan_blend_for_scripts(blend_path)
    if has_scripts:
        os.remove(blend_path)  # Supprimer le fichier suspect
        logger.warning(f"Suspicious file uploaded: {filename} - {script_message}")
        return render_index(error=f"File rejected: {script_message}")
    
    logger.info(f"Saved and validated uploaded file: {blend_path}")
    return render_index()

@app.route("/refresh_gdrive")
@require_auth
def refresh_gdrive():
    return render_index()

@app.route("/render_gdrive/<filename>")
@require_auth
def render_gdrive(filename):
    upload_dir = os.path.join(app.config["WORKDIR"], "uploads")
    output_dir = os.path.join(app.config["WORKDIR"], "output")
    os.makedirs(output_dir, exist_ok=True)

    blend_path   = os.path.join(upload_dir, filename)
    base, _      = os.path.splitext(filename)
    output_base  = os.path.join(output_dir, base)
    output_image = f"{output_base}0001.png"

    if not os.path.isfile(blend_path):
        logger.error(f"File not found: {blend_path}")
        return render_index(error="File not found in uploads.")

    try:
        with render_lock(blend_path):
            logger.info(f"Rendering file: {blend_path}")
            result = subprocess.run(
                [
                    "blender", "-b", blend_path,
                    "--disable-autoexec",  # Désactive l'auto-exécution des scripts
                    "--python-expr",
                    (
                        "import bpy;"
                        "bpy.context.scene.render.engine='CYCLES';"
                        "bpy.context.scene.cycles.device='GPU';"
                        "prefs=bpy.context.preferences.addons['cycles'].preferences;"
                        "prefs.compute_device_type='CUDA';"
                        "prefs.get_devices();"
                        "[setattr(d, 'use', True) for d in prefs.devices];"
                    ),
                    "-o", output_base,
                    "-f", "1"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300  # Timeout de 5 minutes
            )

            logger.info(f"Blender output:\n{result.stdout}")

            if result.returncode != 0:
                errors = "\n".join([line for line in result.stdout.splitlines() if "Error:" in line]) or "Render failed. See logs for details."
                logger.error(errors)
                return render_index(error=errors)

            if os.path.isfile(output_image):
                logger.info(f"Render succeeded: {output_image}")
                return render_index(job=base)
            else:
                logger.error("Render succeeded but output image not found.")
                return render_index(error="Render succeeded but output image not found.")
    except RuntimeError as e:
        return render_index(error=str(e))

@app.route("/output/<filename>")
@require_auth
def download(filename):
    output_dir = os.path.join(app.config["WORKDIR"], "output")
    logger.info(f"Download requested: {filename}")
    return send_from_directory(output_dir, filename, as_attachment=True)

@app.route("/debug_log")
@require_auth
def debug_log():
    try:
        with open(app.config["LOG_PATH"], "r") as f:
            lines = f.readlines()
        return "".join(lines[-300:]), 200, {"Content-Type": "text/plain"}
    except Exception as e:
        return f"Error reading log: {e}", 500, {"Content-Type": "text/plain"}

@app.route("/blender_processes")
@require_auth
def blender_processes():
    try:
        output = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'cmdline', 'username']):
            try:
                # Check if process is blender (by name or command line)
                if 'blender' in (proc.info['name'] or '').lower() or \
                   any('blender' in (arg or '').lower() for arg in (proc.info.get('cmdline') or [])):
                    mem_mb = proc.info['memory_info'].rss // (1024 * 1024)
                    cmdline = proc.info.get('cmdline') or []
                    output.append(
                        f"PID: {proc.info['pid']}, User: {proc.info['username']}, "
                        f"CPU: {proc.info['cpu_percent']}%, Mem: {mem_mb} MiB, "
                        f"Cmd: {' '.join(cmdline)}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not output:
            output.append("No Blender processes found.")
        return "\n".join(output), 200, {"Content-Type": "text/plain"}
    except Exception as e:
        return f"Error listing Blender processes: {e}", 500, {"Content-Type": "text/plain"}

@app.template_filter("datetimeformat")
def datetimeformat(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value

def cleanup_locks():
    uploads_dir = os.path.join(app.config["WORKDIR"], "uploads")
    for f in os.listdir(uploads_dir):
        if f.endswith(".lock"):
            lock_path = os.path.join(uploads_dir, f)
            try:
                os.remove(lock_path)
                logger.info(f"Removed stale lock: {lock_path}")
            except Exception as e:
                logger.warning(f"Could not remove lock {lock_path}: {e}")

if __name__ == "__main__":
    cleanup_locks()
    logger.info("Starting Flask app...")
    app.run(host="0.0.0.0", port=80, debug=True)  # Debug désactivé pour la sécurité
