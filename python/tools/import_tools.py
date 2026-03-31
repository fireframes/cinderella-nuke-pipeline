import nuke
import os
import re
import nukescripts

from ..shot_manager.pipeline_client import PipelineClient, PipelineError

_client = PipelineClient()


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


def import_camera(shot_detail=None):
    if shot_detail is None:
        shot_info = _get_shot_info()
        if not shot_info:
            return None
        ep, sq, sh, shot_name = shot_info
        shot_id = f"{ep}_{sq}_{sh}"
        try:
            shot_detail = _client.get_shot(shot_id)
        except PipelineError as exc:
            nuke.message(f"Could not fetch shot info:\n{exc}")
            return None

    camera_path = shot_detail.get("cam_path")
    if not camera_path or not os.path.exists(camera_path):
        nuke.message(f"Camera file not found: {camera_path}")
        return None

    cam = nuke.createNode("Camera2", inpanel=False)
    cam.knob("suppress_dialog").setValue(True)
    cam.knob("read_from_file").setValue(True)
    cam.knob("file").setValue(camera_path)
    return cam


def import_render_layers(shot_detail=None):
    if shot_detail is None:
        shot_info = _get_shot_info()
        if not shot_info:
            return None
        ep, sq, sh, shot_name = shot_info
        shot_id = f"{ep}_{sq}_{sh}"
        try:
            shot_detail = _client.get_shot(shot_id)
        except PipelineError as exc:
            nuke.message(f"Could not fetch shot info:\n{exc}")
            return None

    render_layers = shot_detail.get("render_layers", [])
    if not render_layers:
        nuke.message("No render layers found for this shot.")
        return

    nodes_created = []
    for layer in render_layers:
        layer_dir = layer["path"]
        sequences = nuke.getFileNameList(layer_dir)
        if not sequences:
            continue
        exr_sequences = [s for s in sequences if s.lower().split(' ')[0].endswith('.exr')]
        if not exr_sequences:
            continue
        full_path = os.path.join(layer_dir, exr_sequences[-1]).replace("\\", "/")
        read_node = nuke.createNode("Read", inpanel=False)
        read_node['file'].fromUserText(full_path)
        nodes_created.append(read_node)

    try:
        cam = import_camera(shot_detail)
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

    read_node = nuke.createNode("Read", inpanel=False)
    read_node['file'].fromUserText(valid_media_paths[-1])
    read_node.autoplace()
    return read_node


def import_template():
    # Template path is managed by the backend config; fetch it via health/config
    # or keep a local fallback. For now, attempt a best-effort local lookup.
    try:
        detail = _client.health()
    except PipelineError:
        detail = {}

    # The backend does not expose TEMPLATE_COMP_PATH directly over the API.
    # The panel's "Import Template" button pastes into the current script —
    # this is handled by the backend when creating a comp script.
    # If called standalone (e.g. from a menu), notify the artist.
    nuke.message(
        "Use 'Create Comp' to create a new comp script from the template.\n"
        "Template import from an existing open script is not supported in v2."
    )
