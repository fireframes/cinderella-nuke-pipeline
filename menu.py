import sys
import os
import nuke
import nukescripts

import dDot

try:
    from plugins.pxf.menu import register_pixelfudger_menu
except ImportError:
    nuke.tprint("Could not import Pixelfudger menu")

# Adds scripts directory to Python path
scripts_path = os.path.join(os.path.dirname(__file__), "scripts")
if scripts_path not in sys.path:
    sys.path.append(scripts_path)

from scripts import shot_manager
from scripts import tools
from scripts import cerebro


# Set up paths
nuke_root = os.path.dirname(__file__)
gizmos_path = os.path.join(nuke_root, "gizmos")
toolsets_path = os.path.join(nuke_root, "toolsets")

gizmos_path = gizmos_path.replace("\\","/")
toolsets_path = toolsets_path.replace("\\","/")

# Access menus and toolbar items
toolbar = nuke.menu("Nodes")
nukeMenu = nuke.menu("Nuke")

# Core Menu
coreMenu = nukeMenu.addMenu('Core Tools')
coreToolbar = toolbar.addMenu('Core Tools', icon="core-value-color.png")

# Register ShotMangerWidget as Panel
panel_id = "com.fireframes.shotmanager"
panel_name = "Shot Manager"
nukescripts.registerWidgetAsPanel(
    'shot_manager.shot_manager_panel.create_shot_manager_panel',
    panel_name,
    panel_id
)
nuke.menu('Pane').addCommand(panel_name, f"nukescripts.panels.restorePanel('{panel_id}')")

# Utilities entries and keyboard shortcuts
studioTools = nukeMenu.addMenu("Utilities")
studioTools.addCommand("Shot Manager", "shot_manager.shot_manager_panel.show_floating_panel()", "alt+S")
studioTools.addCommand("Import Render", "tools.import_tools.import_render_layers()", "shift+R")
studioTools.addCommand("Import Camera", "tools.import_tools.import_camera()", "shift+C")
studioTools.addCommand("Update Write Path", "tools.write_path.update_write_path()", "shift+W")
studioTools.addCommand("Import Template", "tools.import_tools.import_template()", "shift+T")
studioTools.addCommand("Import From Write", "tools.import_tools.import_from_selected_write()", "alt+R")
studioTools.addCommand("Delete Animation", "tools.workflow_tools.delete_animation()", "alt+A")
studioTools.addCommand("Reload Read Nodes", "tools.workflow_tools.reload_read_nodes()", "alt+D")
studioTools.addCommand("Update Old Server Path", "tools.utils.update_old_paths()", "alt+E")
#
# # Update read paths from old server location to new
nuke.addOnScriptLoad(tools.update_old_paths)

# Core Tools entries and keyboard shortcuts
# AITOR ECHEVESTE TOOLS
aeTools = [
    ("aeBrokenEdges", "BrokenEdges_icon.png"),
    ("aeAnamorphic", "aeAnamorphic_icon.png"),
    ("aeFiller", "aeFiller_icon.png"),
    ("aeBrokenShapes", "BrokenShapes_icon.png"),
    ("aePowerPin", "aePowerPin_icon.png"),
    ("aeTransform", "aeTransform_icon.png"),
    ("aeRelight2D", "aeReLight2D_icon.png"),
    ("aeRefracTHOR", "aeRefracTHOR_icon.png"),
    ("aeMotionBlur", "aeMotionBlur_icon.png"),
    ("aePrefMaker", "aePrefMaker_icon.png"),
    ("aeUVChart", "aeUVChart_icon.png"),
    ("aeDirtCG", "aeDirtCG_icon.png"),
    ("aeShadows", "aeShadows_icon.png")
]

aeMenu = coreMenu.addMenu("aeTools")
aeToolbar = coreToolbar.addMenu("aeTools")

for node_name, icon in aeTools:
    aeMenu.addCommand(node_name, f'nuke.createNode("{node_name}")', icon=icon)
    aeToolbar.addCommand(node_name, f'nuke.createNode("{node_name}")', icon=icon)


# Register dDot Tools
dDot.register_menu_items(coreMenu, coreToolbar)


# Register Pixelfudger menu
pxf_menu = coreMenu.addMenu("Pixelfudger3")
pxf_toolbar = coreToolbar.addMenu("Pixelfudger3")
try:
    register_pixelfudger_menu(pxf_menu, pxf_toolbar)
except Exception as e: # Catch any other errors during registration
    nuke.tprint(f"Error registering Pixelfudger menu: {e}")


# Gizmos
gizmosMenu = coreMenu.addMenu("Gizmos")
gizmosToolbar = coreToolbar.addMenu("Gizmos")

for filename in os.listdir(gizmos_path):
    if filename.endswith('.gizmo'):
        name = os.path.splitext(filename)[0]
        gizmosMenu.addCommand(name, f"nuke.createNode('{name}', inpanel=False)")
        gizmosToolbar.addCommand(name,f"nuke.createNode('{name}', inpanel=False)")


# Toolsets
toolsetsMenu = coreMenu.addMenu("Toolsets")
toolsetsToolbar = coreToolbar.addMenu("Toolsets")

for filename in os.listdir(toolsets_path):
    if filename.endswith('.nk'):
        name = os.path.splitext(filename)[0]
        fullpath = os.path.join(toolsets_path, filename).replace('\\', '/')
        # Add each as a menu item
        toolsetsMenu.addCommand(name, f'nuke.loadToolset(r"{fullpath}")')
        toolsetsToolbar.addCommand(name,f'nuke.loadToolset(r"{fullpath}")')

# Shuffle label
nuke.addOnCreate(lambda: nuke.knobDefault("Shuffle2.label", "[ value in1 ]"))


# Mix label
nuke.addOnCreate(lambda: nuke.knobDefault("Merge2.label", "Mix: [ value mix ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("Grade.label", "Mix: [ value mix ]"))

# Filter nodes labels
nuke.addOnCreate(lambda: nuke.knobDefault("Blur.label", "Size: [ value size ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("Defocus.label", "Size: [ value defocus ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("ZDefocus2.label", "Size: [ value size ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("Erode.label", "Size: [ value size ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("FilterErode.label", "Size: [ value size ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("Dilate.label", "Size: [ value size ]"))
nuke.addOnCreate(lambda: nuke.knobDefault("Multiply.label", "Value: [ value value ]"))


# Update plugin menu on
# nukescripts.update_plugin_menu("All plugins")

# Register onScriptDrop callback: updates Write nodes paths for EXR and MOV
nukescripts.addDropDataCallback(tools.workflow_tools.onScriptDrop)
