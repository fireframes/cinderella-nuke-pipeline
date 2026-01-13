import os
import json

try:
    import nuke
    NUKE_AVAILABLE = True
except ImportError:
    NUKE_AVAILABLE = False

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "cinderella_config.json")
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

def get_project_config(prj_name="cinderella"):
    prj_config = CONFIG["projects"][prj_name]
    return prj_config

def project_root_settings():
    if not NUKE_AVAILABLE:
        raise RuntimeError("This function requires Nuke environment")

    config = get_project_config()

    # FORMAT
    format_string = config["format"]
    format_name = format_string.split()[-1]

    if not any(fmt.name() == format_name for fmt in nuke.formats()):
        nuke.addFormat(format_string)

    root = nuke.root()
    root["format"].setValue(format_name)
    root["fps"].setValue(config.get("fps"))

    # OCIO
    root["colorManagement"].setValue(config.get("color_management") or "OCIO")
    root["OCIO_config"].setValue(config.get("ocio_config") or "aces_1.2")

    for knob, val in config.get("ocio_settings", {}).items():
        if knob in root.knobs():
            root[knob].setValue(val)

    def set_viewer_process():
        for v in nuke.allNodes("Viewer"):
            if "viewerProcess" in v.knobs():
                v["viewerProcess"].setValue("sRGB (ACES)")

    nuke.addOnScriptLoad(set_viewer_process)
    nuke.addOnCreate(set_viewer_process)
