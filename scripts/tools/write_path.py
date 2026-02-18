import nuke
import os
import re


from ..config.config_loader import get_project_config

RENDER_PATH = get_project_config().get("server_render_path")
COMP_PATH = get_project_config().get("server_comp_path")

def update_write_path(node=None):
    if node is None:
        try:
            node = nuke.selectedNode()
        except:
            return

    if not node.Class() == 'Write':
        write = nuke.createNode('Write', inpanel=False)
        write.setInput(0, node)
    else:
        write = node

    # Get file format
    format = write['file_type'].value()
    if format not in ["exr", "mov"]:
        choice = nuke.choice("Write Format", "Select file format:", ["EXR", "MOV"])
        if choice == 0:
            format = "exr"
        elif choice == 1:
            format = "mov"
        else:
            return

    # Form file paths
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

    if precomp:
        base_path = f"{COMP_PATH}/{ep}/{sq}/{sh}/light_precomp/{format}"
        if format == 'exr':
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}_precomp.%04d.exr"
        elif format == 'mov':
            new_full_path = f"{base_path}/{ep}_{sq}_{sh}_precomp_{ver}.mov"
    else:
        new_base_path = f"{COMP_PATH}/{ep}/{sq}/{sh}/comp/{format}"
        if format == 'exr':
            new_filename = f"{ep}_{sq}_{sh}.%04d.exr"
        elif format == 'mov':
            new_filename = f"{ep}_{sq}_{sh}_{ver}.mov"
        new_full_path = os.path.join(new_base_path, new_filename).replace("\\","/")

    # Set values
    write.setName(format.upper())
    write['file'].setValue(new_full_path)
    write['file_type'].setValue(format)

    if format == 'exr':
        write['write_ACES_compliant_EXR'].setValue(True)
        write['colorspace'].setValue('scene_linear')
    elif format == 'mov':
        write['colorspace'].setValue('color_picking')
        write['in_colorspace'].setValue('scene_linear')
        write['out_colorspace'].setValue('scene_linear')
        write['mov64_codec'].setValue('h264')
        write['render_order'].setValue('2')
        # write['mov64_pixel_format'].setValue([0, 'yuv420p\\tYCbCr 4:2:0 8-bit'])

    # write['file'].setEnabled(False)
    write['create_directories'].setEnabled(False)
