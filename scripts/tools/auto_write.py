import nuke
import os
import re


def update_write_path():
    sel = nuke.selectedNode()

    # change to create node later
    if not sel.Class() == 'Write':
        nuke.message("Not a Write node selected")
        return
    else:
        write = sel

    # change to diff workaround later
    format = sel['file_type'].value()
    

    script_path = nuke.root().name()
    if not script_path:
        nuke.message("Please save the script first.")
        return

    script_name = os.path.basename(script_path)
    match = re.match(r"(ep\d+)_?(sq\d+)_?(sh\d+)", script_name, re.IGNORECASE)

    if not match:
        nuke.message("Script name doesn't match expected pattern (ep##_sq##_sh###).")
        return

    ep, sq, sh = match.groups()
    new_path_base = f"//192.168.99.202/prj/cinderella/render/{ep}/{sq}/{sh}/comp/{format}"

    if format == 'exr':
        new_filename = f"{ep}_{sq}_{sh}.%04d.exr"
    elif format == 'mov':
        new_filename = f"{ep}_{sq}_{sh}_preview.mov"
    # add prores later

    new_full_path = os.path.join(new_path_base, new_filename).replace("\\","/")

    write['file'].setValue(new_full_path)

