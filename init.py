import nuke
import os
import sys

nuke_root = os.path.dirname(__file__).replace('\\', '/')
plugins_path = f"{nuke_root}/plugins"

nuke.pluginAddPath(plugins_path)
nuke.pluginAddPath(f"{plugins_path}/NukeSurvivalToolkit/NukeSurvivalToolkit")

# Fix Aitor_Echeveste plugin paths
ae_base_path = f"{plugins_path}/Aitor_Echeveste"
nuke.pluginAddPath(ae_base_path)

# Add gizmo subdirectories directly to avoid nested paths
ae_gizmo_dirs = [
    'aeAnamorphic', 'aeBrokenEdges', 'aeBrokenShapes', 'aeDirtCG',
    'aeFiller', 'aeMotionBlur', 'aePowerPin', 'aePrefMaker',
    'aeRefracTHOR', 'aeRelight2D', 'aeShadows', 'aeTransform',
    'aeUVChart', 'iSTMap'
]

for gizmo_dir in ae_gizmo_dirs:
    gizmo_path = f"{ae_base_path}/{gizmo_dir}"
    if os.path.exists(gizmo_path):
        nuke.pluginAddPath(gizmo_path)

nuke.pluginAddPath(f"{plugins_path}/pxf")
nuke.pluginAddPath(f"{nuke_root}/gizmos")
nuke.pluginAddPath(f"{nuke_root}/toolsets")
nuke.pluginAddPath(f"{nuke_root}/icons")
nuke.pluginAddPath(f"{nuke_root}/bah_gizmos")

# Add cerebro to Python path
cerebro_path = f"{nuke_root}/cerebro"
if cerebro_path not in sys.path:
    sys.path.insert(0, cerebro_path)