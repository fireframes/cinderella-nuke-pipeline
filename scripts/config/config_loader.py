import os
import json
import nuke


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "cinderella_config.json")

with open(CONFIG_FILE, 'r') as f:
    CONFIG = json.load(f)

DEFAULTS = {
    "studio_name": CONFIG.get("studio_name"),
    "color_management": CONFIG.get("defaults.color_management"),
    "ocio_config": CONFIG.get("defaults.ocio_config"),
    "fps": CONFIG.get("defaults.fps"),
    "format": CONFIG.get("defaults.format"),
    "viewer_process": CONFIG.get("viewer_process.format")
}

def get_project_config(prj_name="cinderella"):
    prj_config = CONFIG["projects"][prj_name]
    return prj_config
    # merged = DEFAULTS.copy()
    # merged.update(prj_config)
    # return merged


def project_root_settings():
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
                v["viewerProcess"].setValue("RGB (ACES)")

    nuke.addOnScriptLoad(set_viewer_process)
    nuke.addOnCreate(set_viewer_process)
