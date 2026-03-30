import nuke
import os
import re

from ..shot_manager.pipeline_client import PipelineClient, PipelineError

_client = PipelineClient()


def update_write_path(node=None):
    if node is None:
        try:
            node = nuke.selectedNode()
        except Exception:
            return

    if not node.Class() == 'Write':
        write = nuke.createNode('Write', inpanel=False)
        write.setInput(0, node)
    else:
        write = node

    # Get file format
    fmt = write['file_type'].value()
    if fmt not in ["exr", "mov"]:
        choice = nuke.choice("Write Format", "Select file format:", ["EXR", "MOV"])
        if choice == 0:
            fmt = "exr"
        elif choice == 1:
            fmt = "mov"
        else:
            return

    # Parse shot context from script name
    script_path = nuke.root().name()
    if not script_path:
        nuke.message("Please save the script first.")
        return

    script_name = os.path.basename(script_path)
    if script_name.endswith('.nk'):
        script_name = script_name[:-3]

    match = re.match(r"(ep\d+)_?(sq\d+)_?(sh\d+)(_light_precomp|_precomp)?(?:_(v\d+))?", script_name, re.IGNORECASE)
    if not match:
        nuke.message("Script name doesn't match expected pattern (ep##_sq##_sh###).")
        return

    ep, sq, sh, precomp, ver = match.groups()
    shot_id = f"{ep}_{sq}_{sh}"

    # Fetch comp/precomp path from backend
    try:
        detail = _client.get_shot(shot_id)
    except PipelineError as exc:
        nuke.message(f"Could not fetch shot info from pipeline server:\n{exc}")
        return

    if precomp:
        base_path = detail["precomp_path"] + f"/{fmt}"
        if fmt == 'exr':
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}_precomp.%04d.exr"
        else:
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}_precomp_{ver}.mov"
    else:
        base_path = detail["comp_path"] + f"/{fmt}"
        if fmt == 'exr':
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}.%04d.exr"
        else:
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}_{ver}.mov"

    new_full_path = new_full_path.replace("\\", "/")

    # Apply to Write node
    write.setName(fmt.upper())
    write['file'].setValue(new_full_path)
    write['file_type'].setValue(fmt)

    if fmt == 'exr':
        write['write_ACES_compliant_EXR'].setValue(True)
        write['colorspace'].setValue('scene_linear')
    elif fmt == 'mov':
        write['colorspace'].setValue('color_picking')
        write['in_colorspace'].setValue('scene_linear')
        write['out_colorspace'].setValue('scene_linear')
        write['mov64_codec'].setValue('h264')
        write['render_order'].setValue('2')

    write['create_directories'].setEnabled(False)
