import nuke
import os
import re
import nukescripts

from ..config.config_loader import get_project_config

PROD_PATH = get_project_config().get("server_prod_path")
RENDER_PATH = get_project_config().get("server_render_path")
COMP_PATH = get_project_config().get("server_comp_path")
CACHE_PATH_OLD = get_project_config().get("cache_path_old")
CACHE_PATH_NEW = get_project_config().get("cache_path_new")
COMP_TEMPLATE_PATH = get_project_config().get("tools", {}).get("comp_template_path")

def _get_shot_info():
    script_path = nuke.root().name()
    if not script_path:
        nuke.message("Please save the script first or provide a shot name.")
        return None

    script_name = os.path.basename(script_path)
    match = re.match(r"(ep\d+)_?(sq\d+)_?(sh\d+)(_light_precomp|_precomp)?(?:_(v\d+))?", script_name, re.IGNORECASE)
    if not match:
        nuke.message("Script name doesn't match expected pattern (ep##_sq##_sh##_v##).")
        return None

    ep = match.group(1) 
    sq = match.group(2)
    sh = match.group(3) 
    
    shot_name = f"{ep}_{sq}_{sh}"
    return ep, sq, sh, shot_name

def import_camera(shot_name=None):
    shot_info = _get_shot_info()
    if not shot_info:
        return None
    ep, sq, sh, shot_name = shot_info
    if not shot_name:
        nuke.message("Shot name is empty")
        return None

    camera_filename = "shot_camera.abc"
    camera_path = f"{CACHE_PATH_NEW}/{ep}/{sq}/{sh}/src/{camera_filename}"
    if not os.path.exists(camera_path):
        try:
            camera_path = f"{CACHE_PATH_OLD}/{ep}/{sq}/{sh}/src/{camera_filename}"
        except FileNotFoundError:
            nuke.message(f"Camera not found: {camera_path}")
            return None

    if not camera_path:
        nuke.message(f"No camera file found for {shot_name} in {camera_path}")
        return None

    cam = nuke.createNode("Camera2", inpanel=False)
    cam.knob("suppress_dialog").setValue(True)
    cam.knob("read_from_file").setValue(True)
    cam.knob("file").setValue(camera_path)

    return cam

def import_render_layers():
    shot_info = _get_shot_info()
    if not shot_info:
        return None
    ep, sq, sh, shot_name = shot_info

    shot_render_path = f"{RENDER_PATH}/{ep}/{sq}/{sh}/render"
    if not os.path.exists(shot_render_path):
        nuke.message(f"Shot render path not found: {shot_render_path}")
        return

    all_layer_dirs = [d for d in os.listdir(shot_render_path) if os.path.isdir(os.path.join(shot_render_path, d))]
    if not all_layer_dirs:
        nuke.message(f"No render layer directories found in {shot_render_path}")
        return

    layer_groups = {}
    for dir_name in sorted(all_layer_dirs):
        match = re.match(r'(.+)_v\d+$', dir_name)
        base_name = match.group(1) if match else dir_name

        if base_name not in layer_groups:
            layer_groups[base_name] = []
        layer_groups[base_name].append(dir_name)

    render_layers_to_import = [versions[-1] for versions in layer_groups.values()]

    nodes_created = []
    for layer in render_layers_to_import:
        layer_dir = os.path.join(shot_render_path, layer)
        sequences = nuke.getFileNameList(layer_dir)
        if not sequences:
            continue

        exr_sequences = [s for s in sequences if s.lower().split(' ')[0].endswith('.exr')]
        if not exr_sequences:
            continue

        target_sequence = exr_sequences[-1]
        full_path = os.path.join(layer_dir, target_sequence).replace("\\", "/")

        read_node = nuke.createNode("Read", inpanel=False)
        read_node['file'].fromUserText(full_path)
        nodes_created.append(read_node)

    try:
        cam = import_camera(shot_name)
        if cam:
            nodes_created.append(cam)
    except Exception as e:
        nuke.tprint(f"Camera import failed: {e}")

    if not nodes_created:
        nuke.message("No render layers or camera could be imported.")
        return

    for node in nodes_created:
        node.autoplace()
        node.setSelected(True)

    if len(nodes_created) > 1:
        backdrop = nukescripts.autobackdrop.autoBackdrop()
        backdrop['bdheight'].setValue(backdrop['bdheight'].value() + 60)
        backdrop['bdwidth'].setValue(backdrop['bdwidth'].value() + 20)

def import_template():
    if not COMP_TEMPLATE_PATH or not os.path.exists(COMP_TEMPLATE_PATH):
        nuke.message(f"Template not found at: {COMP_TEMPLATE_PATH}")
        return False
    nuke.nodePaste(COMP_TEMPLATE_PATH)
    return True

# Depricated!
def import_comp_exr():
    shot_info = _get_shot_info()
    if not shot_info:
        return None
    ep, sq, sh, shot_name = shot_info

    exr_dir = f"{COMP_PATH}/{ep}/{sq}/{sh}/comp/exr"
    if not os.path.exists(exr_dir):
        nuke.message(f"Render directory not found: {exr_dir}")
        return None

    file_list = nuke.getFileNameList(exr_dir)
    if not file_list:
        nuke.message(f"No sequences found in {exr_dir}")
        return None

    if not shot_name:
        nuke.message("Shot name is empty")
        return None

    matching_sequences = [seq for seq in file_list if shot_name in seq and '.exr' in seq]

    if not matching_sequences:
        nuke.message(f"No EXR sequences found for {shot_name}")
        return None

    read_node = nuke.createNode("Read", inpanel=False)
    read_node['file'].fromUserText(os.path.join(exr_dir, matching_sequences[0]))

    return read_node

def import_from_selected_write():
    try:
        write_node = nuke.selectedNode()
        if write_node.Class() != 'Write':
            nuke.message("Please select a Write node.")
            return None
    except ValueError:
        nuke.message("Please select a Write node.")
        return None

    file_path = write_node['file'].value()
    if not file_path:
        nuke.message(f"Write node '{write_node.name()}' has no file path set.")
        return None

    file_dir = os.path.dirname(file_path)
    if not os.path.exists(file_dir):
        nuke.message(f"Directory does not exist: {file_dir}")
        return None

    file_list = nuke.getFileNameList(file_dir)
    allowed_extensions = ('.exr', '.mov', '.png', '.jpg', '.jpeg')
    valid_media_paths = []

    for sequence_string in file_list:
        filename_part = sequence_string.split(' ')[0]

        if filename_part.lower().endswith(allowed_extensions):
            full_path = os.path.join(file_dir, sequence_string).replace('\\', '/')
            valid_media_paths.append(full_path)

    if not valid_media_paths:
        nuke.message(f"No valid media found in directory:\n{file_dir}")
        return None

    latest_version_path = valid_media_paths[-1]

    read_node = nuke.createNode("Read", inpanel=False)
    read_node['file'].fromUserText(latest_version_path)
    read_node.autoplace()

    return read_node
