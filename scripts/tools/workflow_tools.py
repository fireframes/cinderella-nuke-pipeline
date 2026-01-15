# workflow_tools.py - Main module file v0.1
import nuke
from PySide2 import QtCore
from .write_path import update_write_path


def reload_read_nodes():
    nodes = nuke.allNodes()
    try:
        sel = nuke.selectedNode()
        if sel.Class() == "Read":
            sel.knob("reload").execute()
        else:
            for node in nodes:
                if node.Class() == "Read":
                    node.knob("reload").execute()
    except:
        for node in nodes:
            if node.Class() == "Read":
                node.knob("reload").execute()


def extract_lgt_passes():
    read_node = nuke.selectedNode()
    channels = read_node.channels()

    layers = list(set([c.split('.')[0] for c in channels]))
    light_passes = [lgt for lgt in layers if lgt.startswith('lgt_')]
    print(light_passes)

    start_x = read_node.xpos() + 200
    start_y = read_node.ypos() + 200
    spacing = 110

    for index, layer in enumerate(light_passes):
        shuffle = nuke.createNode("Shuffle", inpanel=False)
        shuffle["in"].setValue(layer)
        shuffle["postage_stamp"].setValue(True)
        shuffle.setName(layer)
        shuffle.setXpos(start_x + index * spacing)
        shuffle.setYpos(start_y)
        shuffle.setInput(0, read_node)


def delete_animation():
    nodes = nuke.selectedNodes()

    for node in nodes:
        for name, knob in node.knobs().items():
            try:
                if knob.isAnimated():
                    knob.clearAnimated()
            except AttributeError as error:
                nuke.tprint(f"Could not clear animation on {node.name()}.{name}: {error}")


def onScriptDrop(mimeType, text):
    if mimeType == 'text/plain' and text.strip().lower().endswith('.nk'):
        QtCore.QTimer.singleShot(0, process_last_paste)

    return None


def process_last_paste():
    for node in nuke.selectedNodes():
        if node.Class() == "Write":
            name = node.knob('name').value()
            if 'EXR' in name or 'MOV' in name:
                update_write_path(node)

