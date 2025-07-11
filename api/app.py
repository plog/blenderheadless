import os
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, render_template, send_from_directory, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
from gdrive_manager import GDriveManager
from datetime import datetime

app = Flask(__name__)
auth = HTTPBasicAuth()

WORKDIR = "/workspace"

# Dummy user for example
users = {
    "admin": "password"
}

# Configure rotating file logger
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
file_handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
# Also log to stdout for Docker
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

@auth.verify_password
def verify_password(username, password):
    if username in users and users[username] == password:
        return username

def is_locked(filepath):
    return os.path.exists(filepath + ".lock")

def create_lock(filepath):
    with open(filepath + ".lock", "w") as f:
        f.write("locked")

def remove_lock(filepath):
    try:
        os.remove(filepath + ".lock")
    except FileNotFoundError:
        pass

def get_rendered_images():
    output_dir = os.path.join(WORKDIR, "output")
    try:
        return sorted([f for f in os.listdir(output_dir) if f.endswith(".png")])
    except Exception:
        return []

@app.route("/", methods=["GET"])
@auth.login_required
def index():
    try:
        gdm = GDriveManager()
        gdrive_files = [f for f in gdm.list_files() if f["name"].endswith(".blend")]
    except Exception:
        gdrive_files = []
    rendered_images = get_rendered_images()
    return render_template("index.html", gdrive_files=gdrive_files, rendered_images=rendered_images)

@app.route("/", methods=["POST"])
@auth.login_required
def upload():
    upload_dir = os.path.join(WORKDIR, "uploads")
    if "file" not in request.files:
        logger.warning("No file part in request")
        return render_template("index.html", error="No file part", gdrive_files=[], rendered_images=get_rendered_images())
    f = request.files["file"]
    if f.filename == "":
        logger.warning("No selected file")
        return render_template("index.html", error="No selected file", gdrive_files=[], rendered_images=get_rendered_images())
    filename   = secure_filename(f.filename)
    os.makedirs(upload_dir, exist_ok=True)
    blend_path  = os.path.join(upload_dir, filename)
    if is_locked(blend_path):
        logger.warning(f"File {blend_path} is currently being rendered.")
        return render_template("index.html", error="File is currently being rendered.", gdrive_files=[], rendered_images=get_rendered_images())
    f.save(blend_path)
    logger.info(f"Saved uploaded file to {blend_path}")
    try:
        gdm = GDriveManager()
        gdrive_files = [f for f in gdm.list_files() if f["name"].endswith(".blend")]
    except Exception:
        gdrive_files = []
    rendered_images = get_rendered_images()
    return render_template("index.html", gdrive_files=gdrive_files, rendered_images=rendered_images)

@app.route("/refresh_gdrive")
@auth.login_required
def refresh_gdrive():
    try:
        gdm = GDriveManager()
        gdrive_files = [f for f in gdm.list_files() if f["name"].endswith(".blend")]
    except Exception as e:
        logger.error(f"Failed to list GDrive files: {e}")
        gdrive_files = []
    rendered_images = get_rendered_images()
    return render_template("index.html", gdrive_files=gdrive_files, rendered_images=rendered_images)

@app.route("/render_gdrive/<filename>")
@auth.login_required
def render_gdrive(filename):
    upload_dir  = os.path.join(WORKDIR, "uploads")
    output_dir  = os.path.join(WORKDIR, "output")
    print("DEBUG: Files in uploads:", os.listdir(upload_dir))
    print("DEBUG: Requested filename:", filename)
    base, _     = os.path.splitext(filename)
    blend_path  = os.path.join(upload_dir, filename)
    output_base = os.path.join(output_dir, base)
    os.makedirs(output_dir, exist_ok=True)
    try:
        gdrive_files = [{"name": f} for f in os.listdir(upload_dir) if f.endswith(".blend")]
    except Exception:
        gdrive_files = []
    rendered_images = get_rendered_images()
    if not os.path.isfile(blend_path):
        logger.error(f"Requested file {blend_path} not found in uploads.")
        return render_template("index.html", error="File not found in uploads.", gdrive_files=gdrive_files, rendered_images=rendered_images)
    if is_locked(blend_path):
        logger.warning(f"File {blend_path} is currently being rendered.")
        return render_template("index.html", error="File is currently being rendered.", gdrive_files=gdrive_files, rendered_images=rendered_images)
    logger.info(f"Rendering GDrive-uploaded file {blend_path}")
    create_lock(blend_path)
    try:
        proc = subprocess.Popen(
            [
                "blender", "-b", blend_path,
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
                "-o", output_base, "-f", "1"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        out, _ = proc.communicate()
        logger.info(f"Blender output:\n{out}")
        output_image = f"{output_base}0001.png"
        if proc.returncode != 0 or "Error:" in out:
            error_lines = "\n".join([line for line in out.splitlines() if "Error:" in line])
            if not error_lines:
                error_lines = "Render failed. See logs for details."
            logger.error(f"Render failed: {error_lines}")
            return render_template("index.html", error=error_lines, gdrive_files=gdrive_files, rendered_images=rendered_images)
        if os.path.isfile(output_image):
            import base64
            with open(output_image, "rb") as imgf:
                img_b64 = base64.b64encode(imgf.read()).decode("utf-8")
            logger.info(f"Render succeeded, output image at {output_image}")
            rendered_images = get_rendered_images()
            return render_template("index.html", job=base, img_b64=img_b64, gdrive_files=gdrive_files, rendered_images=rendered_images)
        else:
            logger.error("Render succeeded but output image not found.")
            return render_template("index.html", error="Render succeeded but output image not found.", gdrive_files=gdrive_files, rendered_images=rendered_images)
    finally:
        remove_lock(blend_path)

@app.route("/output/<filename>")
@auth.login_required
def download(filename):
    output_dir = os.path.join(WORKDIR, "output")
    logger.info(f"Download requested for {filename}")
    return send_from_directory(output_dir, filename, as_attachment=True)

@app.route("/debug_log")
@auth.login_required
def debug_log():
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        last_lines = lines[-300:] if len(lines) > 300 else lines
        return "".join(last_lines), 200, {"Content-Type": "text/plain"}
    except Exception as e:
        return f"Error reading log: {e}", 500, {"Content-Type": "text/plain"}

@app.template_filter('datetimeformat')
def datetimeformat(value):
    try:
        # Google Drive returns RFC3339, e.g. "2024-07-04T12:34:56.789Z"
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value

if __name__ == "__main__":
    logger.info("Starting Flask app...")
    app.run(host="0.0.0.0", port=80, debug=True)