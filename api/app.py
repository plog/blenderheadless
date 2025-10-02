import os
import subprocess
import logging
import base64
from datetime import datetime
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

from flask import Flask, request, render_template, send_from_directory, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename

from gdrive_manager import GDriveManager
import psutil

# --- configuration ---

class Config:
    WORKDIR = "/workspace"
    LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
    USERS = {
        "admin": "password",  # replace with env vars or hashed credentials in production
    }

app = Flask(__name__)
app.config.from_object(Config)
auth = HTTPBasicAuth()

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

@auth.verify_password
def verify_password(username, password):
    return username if Config.USERS.get(username) == password else None

# --- helpers ---

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

@app.route("/", methods=["GET"])
@auth.login_required
def index():
    return render_index()

@app.route("/", methods=["POST"])
@auth.login_required
def upload():
    upload_dir = os.path.join(app.config["WORKDIR"], "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    if "file" not in request.files:
        return render_index(error="No file part in request")

    f = request.files["file"]
    if f.filename == "":
        return render_index(error="No selected file")

    filename = secure_filename(f.filename)
    blend_path = os.path.join(upload_dir, filename)

    if is_locked(blend_path):
        return render_index(error="File is currently being rendered.")

    f.save(blend_path)
    logger.info(f"Saved uploaded file to {blend_path}")

    return render_index()

@app.route("/refresh_gdrive")
@auth.login_required
def refresh_gdrive():
    return render_index()

@app.route("/render_gdrive/<filename>")
@auth.login_required
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
                text=True
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
@auth.login_required
def download(filename):
    output_dir = os.path.join(app.config["WORKDIR"], "output")
    logger.info(f"Download requested: {filename}")
    return send_from_directory(output_dir, filename, as_attachment=True)

@app.route("/debug_log")
@auth.login_required
def debug_log():
    try:
        with open(app.config["LOG_PATH"], "r") as f:
            lines = f.readlines()
        return "".join(lines[-300:]), 200, {"Content-Type": "text/plain"}
    except Exception as e:
        return f"Error reading log: {e}", 500, {"Content-Type": "text/plain"}

@app.route("/blender_processes")
@auth.login_required
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
    app.run(host="0.0.0.0", port=80, debug=True)
