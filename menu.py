import sys
import os
import nuke


# Adds scripts directory to Python path
scripts_path = os.path.join(os.path.dirname(__file__), "scripts")
if scripts_path not in sys.path:
    sys.path.append(scripts_path)

from scripts import shot_manager
from scripts import tools

# def register_panel():
toolbar = nuke.menu("Nodes")
nuke_menu = nuke.menu("Nuke")

m = toolbar.addMenu("Shot Manager")
m.addCommand("Open Shot Manager", "shot_manager.show_panel()")


# Add keyboard shortcut
nuke_menu.addCommand("Tools/Project Manager", "shot_manager.show_panel()", "F5")
nuke_menu.addCommand("Tools/Auto Write", "tools.auto_write.update_write_path()", "F3")
nuke_menu.addCommand("Tools/Reload Read Nodes", "tools.workflow_tools.reload_read_nodes()", "shift+D")
