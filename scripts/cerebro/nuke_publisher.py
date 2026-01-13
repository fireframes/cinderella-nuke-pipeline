# SPDX‑License‑Identifier: Apache‑2.0
# nuke_publisher.py – Nuke to Cerebro publishing module
# Copyright © 2025 Maxim Maximov. All rights reserved.

import os
import subprocess
import sys
import json
import re
import threading
import nuke
from pathlib import Path

try:
    project_root = Path(__file__).parents[1]
    sys.path.insert(0, str(project_root))
    from config import config_loader

    config = config_loader.get_project_config()
    comp_path = config.get("server_comp_path", "")
    tools_path = config.get("tools_path", "")
    maya_py_path = f"{tools_path}/maya/python"

    if tools_path:
        sys.path.insert(1, r"C:/Program Files/Cerebro/py-site-packages")
        sys.path.insert(2, os.path.normpath(maya_py_path))

except ImportError:
    nuke.tprint("Warning: Could not import config, using fallback paths")
    config = {}

try:
    import am_basepref

    pref = am_basepref.Project_Pref_Class()
    cerebro_server_address = pref.cerebro_server_address
    STATUSES = {
        'pause': 3059206,
        'ready_fo': pref.cerebro_status_ready_fw,
        'to_fix': pref.cerebro_status_revision,
        'in_progress': pref.cerebro_status_progress,
        'approval': pref.cerebro_status_approval,
        'complete': pref.cerebro_status_complete,
        'error': pref.cerebro_status_error,
        'pending': 155708447
    }
except ImportError:
    nuke.warning("Warning: am_basepref module not available")

try:
    from pycerebro import database, dbtypes, cargador
    cerebro_module_enable = True
except ImportError:
    cerebro_module_enable = False
    nuke.tprint("pycerebro module not available")

user_path = os.path.expanduser("~").replace("\\", "/")
cerebro_user_creds_path = f"{user_path}/.nuke/cerebro/cerebro_account_info.json"


def get_current_shot_context():
    shot_context = None

    try:
        script_path = nuke.root().name()
        if script_path and script_path != "Root":
            script_name = os.path.basename(script_path)
            match = re.search(r'(ep\d+_sq\d+_sh\d+)', script_name)
            if match:
                shot_context = match.group(1)
                nuke.tprint(f"Shot context from script name: {shot_context}")
                return shot_context
    except:
        pass

    try:
        project_dir = nuke.root()['project_directory'].getValue()
        if project_dir:
            match = re.search(r'ep(\d+)[/\\]sq(\d+)[/\\]sh(\d+)', project_dir)
            if match:
                ep, sq, sh = match.groups()
                shot_context = f"ep{ep}_sq{sq}_sh{sh}"
                nuke.tprint(f"Shot context from project directory: {shot_context}")
                return shot_context
    except:
        pass

    nuke.tprint("Could not determine shot context")
    return None


def get_shot_paths(shot_name):
    match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', shot_name)
    if not match:
        return None

    ep, sq, sh = match.groups()

    shot_comp_path = f"{comp_path}/ep{ep}/sq{sq}/sh{sh}/comp"
    shot_precomp_path = f"{comp_path}/ep{ep}/sq{sq}/sh{sh}/light_precomp"

    return {
        "ep": ep,
        "sq": sq,
        "sh": sh,
        "comp_dir": shot_comp_path,
        "precomp_dir": shot_precomp_path,
        "nk_dir": f"{shot_comp_path}/nk",
        "exr_dir": f"{shot_comp_path}/exr",
        "mov_dir": f"{shot_comp_path}/mov",
        "thumb_dir": f"{shot_comp_path}/.thumb"
    }


def find_latest_mov(shot_name):
    paths = get_shot_paths(shot_name)
    if not paths:
        return None

    mov_dir = paths["mov_dir"]
    if not os.path.exists(mov_dir):
        print(f"Movie directory not found: {mov_dir}")
        return None

    try:
        mov_files = [f for f in os.listdir(mov_dir) if f.lower().endswith('.mov')]
        if not mov_files:
            print(f"No .mov files found in {mov_dir}")
            return None

        # Extract version numbers and sort by highest version
        versioned_movs = []
        for mov_file in mov_files:
            if mov_file.endswith('_preview.mov'):
                nuke.warning("Old non-versioned '_preview' movs are not supported for publish")
            version_match = re.search(r'_v(\d+)\.mov', mov_file, re.IGNORECASE)
            if version_match:
                version = int(version_match.group(1))
                versioned_movs.append((version, mov_file))

        versioned_movs.sort(key=lambda x: x[0], reverse=True)
        if not versioned_movs:
            nuke.tprint(f"No versioned .mov files found in {mov_dir}")
            return None

        latest_mov = f"{mov_dir}/{versioned_movs[0][1]}"
        print(latest_mov)
        return latest_mov

    except Exception as e:
        nuke.error(f"Error finding movie files: {e}")
        return None


def construct_cerebro_task_url(shot_name):
    match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', shot_name)
    if not match:
        nuke.tprint(f"Invalid shot name format: {shot_name}")
        return None

    ep, sq, sh = match.groups()

    ep_num = int(ep)
    sq_num = int(sq)
    sh_num = int(sh)

    task_url = f"/Cinderella/Prod/ep{ep_num:02d}/sq{sq_num:02d}/sh{sh_num:03d}/compos"
    nuke.tprint(f"Constructed Cerebro task URL: {task_url}")

    return task_url


def cerebro_database_connect():
    if not cerebro_module_enable:
        nuke.tprint("pycerebro module not available")
        return None

    if not os.path.exists(cerebro_user_creds_path):
        nuke.tprint(f"Credentials file not found: {cerebro_user_creds_path}")
        nuke.tprint("Please ensure Cerebro credentials are saved in ~/.nuke/cerebro/cerebro_account_info.json")
        return None

    try:
        with open(cerebro_user_creds_path, 'r') as f:
            creds = json.load(f)
        if 'name' not in creds or 'pass' not in creds:
            nuke.tprint("Invalid credentials format. Expected 'name' and 'pass' fields.")
            return None

    except Exception as e:
        nuke.tprint(f"Error reading credentials: {e}")
        return None

    try:
        db = database.Database()
        connect_result = db.connect(creds['name'], creds['pass'], cerebro_server_address)
        if connect_result is None:
            db.verify_ssl = True
            nuke.tprint("Connected to Cerebro database")
            return db
        else:
            nuke.tprint(f"Cerebro connection failed: {connect_result}")
            return None
    except Exception as e:
        nuke.tprint(f"Cerebro connection error: {e}")
        return None


def make_thumbnails(filepath):
    nuke.tprint(f"Source filepath: {filepath} - exists: {os.path.exists(filepath)}")
    if not os.path.exists(filepath):
        nuke.tprint("Source file does not exist")
        return []

    filename = os.path.splitext(os.path.basename(filepath))[0]
    thumb_dir = f"{os.path.dirname(filepath)}/.thumb"
    thumb_path = f"{thumb_dir}/{filename}_thumb.jpg"

    if os.path.exists(thumb_path):
        nuke.tprint(f"Thumbnail already exists: {thumb_path}")
        return [thumb_path]
    if not os.path.exists(thumb_dir):
        os.makedirs(thumb_dir)
        nuke.tprint(f"Created thumbnail directory: {thumb_dir}")

    nuke.tprint(f"Thumbnail will be saved to: {thumb_path}")

    try:
        ffmpeg_result = subprocess.run(['ffmpeg', '-version'],
                                       capture_output=True, text=True)
        if ffmpeg_result.returncode != 0:
            nuke.tprint("ffmpeg not found in PATH")
            return []

        duration_cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        if duration_result.returncode != 0:
            nuke.tprint("Could not get video duration, using 50% seek")
            seek_time = "50%"
        else:
            try:
                duration = float(duration_result.stdout.strip())
                middle_time = duration / 2
                seek_time = str(middle_time)
                nuke.tprint(f"Video duration: {duration}s, seeking to middle: {middle_time}s")
            except (ValueError, TypeError):
                nuke.tprint("Could not parse duration, using 50% seek")
                seek_time = "50%"

        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', filepath,
            '-vf', 'scale=1024:429:force_original_aspect_ratio=decrease',
            '-ss', seek_time,
            '-vframes', '1',
            '-y',
            thumb_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        nuke.tprint(f"ffmpeg exit code: {result.returncode}")
        if result.stderr:
            nuke.tprint(f"ffmpeg stderr: {result.stderr}")
        if result.stdout:
            nuke.tprint(f"ffmpeg stdout: {result.stdout}")

        if os.path.exists(thumb_path):
            nuke.tprint(f"Thumbnail created successfully: {thumb_path}")
            return [thumb_path]
        else:
            nuke.tprint("Thumbnail file was not created")
            return []

    except FileNotFoundError:
        nuke.tprint("ffmpeg/ffprobe not found. Please ensure ffmpeg is installed and in PATH.")
        return []
    except Exception as e:
        nuke.tprint(f"Error running ffmpeg: {e}")
        return []


def _background_publish(shot_name, description, comment, work_time):
    """Performs all blocking I/O in a background thread."""
    try:
        db = cerebro_database_connect()
        if not db:
            raise ConnectionError("Failed to connect to Cerebro database")

        carga = cargador.Cargador(
            pref.cerebro_cargador_address,
            pref.cerebro_cargador_native_port,
            pref.cerebro_cargador_http_port
        )
        task_url = construct_cerebro_task_url(shot_name)
        task = db.task_by_url(task_url)
        if not task or len(task) == 0 or task[0] is None:
            raise ValueError(f"Task not found in Cerebro: {task_url}")

        task_id = task[0]
        mov_path = find_latest_mov(shot_name)
        if not mov_path:
            raise FileNotFoundError("No movie file found to publish")

        nuke.tprint("Generating thumbnails...")
        thumbnails = make_thumbnails(mov_path)

        # For further functionality expansion this can be a list of people to choose from in Nuke in modal dialogue
        ## users = config.get('cerebro').get('users')
        ## picked_user = users[0]
        message_comment = f"{comment}" if comment else ""
        message_body = message_comment
        ## picked_user['messageTag'] + message_comment

        nuke.tprint("Creating review in Cerebro...")
        new_message_id = db.add_report(task_id, None, message_body, work_time)
        ## db.execute("select \"notifyEventUsers_forced\"(?::integer[],'Nm',?::bigint,?::bigint)",
                   ## [picked_user['user_id']],
                   ## task_id, new_message_id)

        nuke.tprint("Attaching movie file...")
        db.add_attachment(new_message_id, carga, mov_path, thumbnails, description, False)

        nuke.tprint("Updating task status...")
        status_result = db.task_set_status(task_id, STATUSES['pending'])

        nuke.executeInMainThread(nuke.message, args=(f"Successfully published {shot_name} to Cerebro",))
        nuke.tprint(f"Successfully published {shot_name} to Cerebro")

    except Exception as e:
        error_message = f"Error during Cerebro publish:\n{e}"
        nuke.executeInMainThread(nuke.error, args=(error_message,))


def publish_shot_to_cerebro(shot_name=None, description="Published from Nuke Shot Manager"):
    """Launches the publish process in a background thread to keep UI responsive."""
    comment = nuke.getInput("Add comment:")
    if comment is None:  # User pressed Cancel
        nuke.tprint("Publish cancelled by user.")
        return


    work_time = choose_work_time()
    if work_time is None:
        nuke.tprint("Publish cancelled by user.")
        return


    if shot_name is None:
        shot_name = get_current_shot_context()
        if not shot_name:
            nuke.error("Could not determine shot context.")
            return

    nuke.tprint(f"Starting publish for {shot_name} in the background...")
    thread = threading.Thread(
        target=_background_publish,
        args=(shot_name, description, comment, work_time)
    )
    thread.daemon = True
    thread.start()


def choose_work_time():
    WORK_TIME_OPTIONS = [
        ('0 h', 0),
        ('15 mins', 15),
        ('30 mins', 30),
        ('1 h', 60),
        ('1 h 30 mins', 90),
        ('2 h', 120),
        ('2 h 30 mins', 150),
        ('3 h', 180),
        ('3 h 30 mins', 210)
    ]
    
    WORK_TIME_VALUES = [label for label, _ in WORK_TIME_OPTIONS]
    choice = nuke.choice("Work Time", "Select time spent on task:", WORK_TIME_VALUES)
    if choice is None:
        work_time = None
    else:
        work_time = WORK_TIME_OPTIONS[choice][1]

    return work_time
