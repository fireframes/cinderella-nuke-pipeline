# SPDX‑License‑Identifier: Apache‑2.0
# shot_manager.py – Main module file v0.1
# Copyright © 2025 Maxim Maximov. All rights reserved.

import os
import sys
import re
import json
import nuke
import nukescripts
import subprocess
from ..config import get_project_config
from ..config import project_root_settings
from datetime import datetime


_active_panel = None


def validate_panel_and_call(method_name):
    global _active_panel

    if _active_panel:
        if hasattr(_active_panel, method_name):
            method = getattr(_active_panel, method_name)
            return method()
        else:
            nuke.tprint(f"Method '{method_name}' not found on Shot Manager panel")
    else:
        nuke.tprint("No active Shot Manager panel found")

def reload_shots():
    validate_panel_and_call('scan_shot_dirs')

def create_script():
    validate_panel_and_call('create_script')

def create_light_precomp():
    validate_panel_and_call('create_light_precomp')

def open_script():
    validate_panel_and_call('open_script')

def open_comp_dir():
    validate_panel_and_call('open_comp_dir')

def open_precomp_dir():
    validate_panel_and_call('open_precomp_dir')

def import_render_layers():
    validate_panel_and_call('import_render_layers')

def create_light_precomp():
    validate_panel_and_call('create_light_precomp')


class ShotManagerPanel(nukescripts.PythonPanel):

    def __init__(self):
        nukescripts.PythonPanel.__init__(self, "Shot Manager")

        global _active_panel
        _active_panel = self

        self.setMinimumSize(500, 120)

        self.config = get_project_config()
        self.selected_script = ""

        # Base paths
        self.render_path = self.config.get("server_render_path")
        self.prj_comp_path = self.config.get("server_comp_path")
        self.prj_cache_path_old = self.config.get("cache_path_old")
        self.prj_cache_path_new = self.config.get("cache_path_new")
        self.comp_template_path = self.config.get("tools", {}).get("comp_template_path")
        self.precomp_template_path = self.config.get("tools", {}).get("precomp_template_path")

        # Cache
        self.cache_file = os.path.join(os.path.expanduser("~"), ".nuke", "shot_manager_cache.json")
        self.all_shots = []
        self.shot_data = {}

        # Define knobs for the panel
        self.shots_text_knob = nuke.Text_Knob("Shots")
        self.episode_knob = nuke.Enumeration_Knob("episode", "ep", ["Select Episode"])
        self.sequence_knob = nuke.Enumeration_Knob("sequence", "sq", ["Select Sequence"])
        self.sequence_knob.clearFlag(nuke.STARTLINE)
        self.shot_knob = nuke.Enumeration_Knob("shot", "sh", ["Select Shot"])
        self.shot_knob.clearFlag(nuke.STARTLINE)
        self.reload_btn = nuke.PyScript_Knob("reload", "Reload Shots")
        self.reload_btn.clearFlag(nuke.STARTLINE)

        self.comp_text_knob = nuke.Text_Knob("Compositing")
        self.create_btn = nuke.PyScript_Knob("create_script", "Create Script")
        self.create_btn.setFlag(nuke.STARTLINE)
        self.open_btn = nuke.PyScript_Knob("open_script", "Open Script")
        self.open_comp_dir_btn = nuke.PyScript_Knob("open_comp_dir", "Open Comp Dir")
        self.import_render_layers_btn = nuke.PyScript_Knob("import_render_layers", "Import Render")
        self.light_text_knob = nuke.Text_Knob("Lighting")
        self.create_light_precomp_btn = nuke.PyScript_Knob("create_light_precomp", "Create Light Precomp")
        self.open_precomp_dir_btn = nuke.PyScript_Knob("open_precomp_dir", "Open Precomp Directory")


        # Add Knobs to Panel
        # Shots knobs
        self.addKnob(self.shots_text_knob)
        self.addKnob(self.episode_knob)
        self.addKnob(self.sequence_knob)
        self.addKnob(self.shot_knob)
        self.addKnob(self.reload_btn)
        # Div line
        # divider1 = nuke.Text_Knob("divider1", "", "")
        # self.addKnob(divider1)
        # Comp buttons
        self.addKnob(self.comp_text_knob)
        self.addKnob(self.create_btn)
        self.addKnob(self.open_btn)
        self.addKnob(self.open_comp_dir_btn)
        self.addKnob(self.import_render_layers_btn)
        # Div line
#         divider2 = nuke.Text_Knob("divider2", "", "")
#         self.addKnob(divider2)
        # Light buttons
        self.addKnob(self.light_text_knob)
        self.addKnob(self.create_light_precomp_btn)
        self.addKnob(self.open_precomp_dir_btn)
        self.open_precomp_dir_btn.clearFlag(nuke.STARTLINE)
        # Div line
        divider3 = nuke.Text_Knob("")
        self.addKnob(divider3)
        divider3.setFlag(nuke.STARTLINE)


        # Connect callbacks
        self.create_btn.setCommand("shot_manager.create_script()")
        self.open_btn.setCommand("shot_manager.open_script()")
        self.reload_btn.setCommand("shot_manager.reload_shots()")
        self.open_comp_dir_btn.setCommand("shot_manager.open_comp_dir()")
        self.import_render_layers_btn.setCommand("shot_manager.import_render_layers()")
        self.create_light_precomp_btn.setCommand("shot_manager.create_light_precomp()")
        self.open_precomp_dir_btn.setCommand("shot_manager.open_precomp_dir()")

        # Initialize data
        self.initialize_data()

    def initialize_data(self):
        """Load data on startup - try cache first, scan if needed"""
        if not self.load_from_cache():
            self.scan_shot_dirs()

    def knobChanged(self, knob):
        if knob == self.episode_knob:
            self.update_sequences()
            self.update_shots()
        elif knob == self.sequence_knob:
            self.update_shots()

    def update_sequences(self):
        """Update sequence dropdown based on selected episode"""
        selected_ep = self.episode_knob.value()

        if selected_ep == "Select Episode" or selected_ep not in self.shot_data:
            self.sequence_knob.setValues(["Select Sequence"])
            return

        sequences = sorted(self.shot_data[selected_ep].keys())
        self.sequence_knob.setValues(sequences)
        if sequences:
            self.sequence_knob.setValue(sequences[0])

    def update_shots(self):
        """Update shot dropdown based on selected episode and sequence"""
        selected_ep = self.episode_knob.value()
        selected_sq = self.sequence_knob.value()

        if (selected_ep == "Select Episode" or
                selected_sq == "Select Sequence" or
                selected_ep not in self.shot_data or
                selected_sq not in self.shot_data[selected_ep]):
            self.shot_knob.setValues(["Select Shot"])
            return

        shots = sorted(self.shot_data[selected_ep][selected_sq])
        self.shot_knob.setValues(shots)
        if shots:
            self.shot_knob.setValue(shots[0])

    def get_current_shot(self):
        """Get currently selected shot in ep##_sq##_sh## format"""
        ep = self.episode_knob.value()
        sq = self.sequence_knob.value()
        sh = self.shot_knob.value()

        if ep == "Select Episode" or sq == "Select Sequence" or sh == "Select Shot":
            return None

        return f"ep{ep}_sq{sq}_sh{sh}"

    def build_shot_hierarchy(self):
        """Build hierarchical shot data structure from flat shot list"""
        self.shot_data = {}

        for shot in self.all_shots:
            match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', shot)
            if not match:
                continue

            ep, sq, sh = match.groups()
            ep_str = ep
            sq_str = sq
            sh_str = sh

            if ep_str not in self.shot_data:
                self.shot_data[ep_str] = {}
            if sq_str not in self.shot_data[ep_str]:
                self.shot_data[ep_str][sq_str] = []

            self.shot_data[ep_str][sq_str].append(sh_str)

    def update_episode_dropdown(self):
        """Update episode dropdown with available episodes"""
        if not self.shot_data:
            self.episode_knob.setValues(["No episodes found"])
            return

        episodes = sorted(self.shot_data.keys())
        self.episode_knob.setValues(episodes)
        if episodes:
            self.episode_knob.setValue(episodes[0])

    def load_from_cache(self):
        """Load shots from cache if recent enough"""
        if not os.path.exists(self.cache_file):
#             self.cache_status.setValue("No cache found")
            return False

        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            cache_time = datetime.strptime(cache_data.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()

            if (current_time - cache_time).total_seconds() < 86400:
                self.all_shots = cache_data.get('shots', [])
                self.build_shot_hierarchy()
                self.update_episode_dropdown()
                self.update_sequences()
                self.update_shots()

#                 self.cache_status.setValue(f"Cache loaded: {cache_data.get('timestamp')}")
                return True
            else:
#                 self.cache_status.setValue("Cache expired")
                return False

        except Exception as e:
            print(f"Error loading cache: {e}")
#             self.cache_status.setValue(f"Cache error: {str(e)}")
            return False

    def save_to_cache(self, shots):
        """Save shots to cache file"""
        try:
            cache_dir = os.path.dirname(self.cache_file)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            cache_data = {
                'shots': shots,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

#             self.cache_status.setValue(f"Cache updated: {cache_data['timestamp']}")
        except Exception as e:
            print(f"Error saving cache: {e}")
#             self.cache_status.setValue(f"Cache save error: {str(e)}")

    def scan_shot_dirs(self):
        """Scan render directory for shots with actual renders"""
        if not os.path.exists(self.render_path):
            nuke.message(f"Render path not found: {self.render_path}")
            return

#         self.cache_status.setValue("Scanning...")
        available_shots = []

        task = nuke.ProgressTask("Scanning for rendered shots")

        try:
            for root, dirs, files in os.walk(self.render_path):
                if task.isCancelled():
                    break

                if not root.endswith('/render') and not root.endswith('\\render'):
                    continue

                match = re.search(r'ep(\d+)[/\\]sq(\d+)[/\\]sh(\d+)[/\\]render', root)
                if not match:
                    continue

                ep, sq, sh = match.groups()

                # Check for actual renders
                has_renders = False
                if dirs:
                    for render_dir in dirs:
                        render_path = os.path.join(root, render_dir)
                        if os.path.exists(render_path):
                            try:
                                render_files = os.listdir(render_path)
                                exr_files = [f for f in render_files if f.lower().endswith('.exr')]
                                if exr_files:
                                    has_renders = True
                                    break
                            except OSError:
                                continue

                if has_renders:
                    shot_name = f"ep{ep}_sq{sq}_sh{sh}"
                    available_shots.append(shot_name)

            available_shots.sort()
            self.all_shots = available_shots

            # Build hierarchy and update UI
            self.build_shot_hierarchy()
            self.update_episode_dropdown()
            self.update_sequences()
            self.update_shots()

            self.save_to_cache(available_shots)

            task.setProgress(100)
            print(f"Found {len(available_shots)} shots with renders")

        except Exception as e:
            print(f"Error during scan: {e}")
#             self.cache_status.setValue(f"Scan error: {str(e)}")
        finally:
            task.setProgress(100)

    def import_template(self, template_path=None):
        """Import a template script into the current script"""
        if not os.path.exists(template_path):
            nuke.message(f"Template not found at: {template_path}")
            return False

        nuke.nodePaste(template_path)
        return True

    def get_shot_paths(self, selected_shot=None):
        """Parse shot name and return path dictionary"""
        match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', selected_shot)
        if not match:
            return None

        ep, sq, sh = match.groups()
        shot_comp_path = f"{self.prj_comp_path}/ep{ep}/sq{sq}/sh{sh}/comp"
        shot_precomp_path = f"{self.prj_comp_path}/ep{ep}/sq{sq}/sh{sh}/light_precomp"
        shot_cam_path = f"{self.prj_cache_path_new}/ep{ep}/sq{sq}/sh{sh}/src/shot_camera.abc"

        if not os.path.exists(shot_cam_path):
            shot_cam_path = f"{self.prj_cache_path_old}/ep{ep}/sq{sq}/sh{sh}/src/shot_camera.abc"

        return {
            "ep": ep,
            "sq": sq,
            "sh": sh,
            "comp_dir": shot_comp_path,
            "precomp_dir": shot_precomp_path,
            "cam_dir": shot_cam_path,
            "nk_dir": os.path.join(shot_comp_path, "nk"),
            "exr_dir": os.path.join(shot_comp_path, "exr"),
            "mov_dir": os.path.join(shot_comp_path, "mov"),
        }

    def import_camera(self, selected_shot=None):
        if selected_shot is None:
            selected_shot = self.available_shots_knob.value()

        shot_cam_path = self.get_shot_paths(selected_shot)["cam_dir"]
        if not os.path.exists(shot_cam_path):
            nuke.message(f"Shot camera path not found: {shot_cam_path}")
            return False

        nuke.tprint(f"Shot camera path: {shot_cam_path}")

        cam = nuke.createNode("Camera2", inpanel=False)
        cam.knob("suppress_dialog").setValue(True)
        cam.knob("read_from_file").setValue(True)
        cam.knob("file").setValue(shot_cam_path)

        return cam

    def import_render_layers(self):
        """Import render layers as Read nodes"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        shot_paths = self.get_shot_paths(selected_shot)
        if not shot_paths:
            nuke.message("Invalid shot format")
            return

        ep, sq, sh = shot_paths["ep"], shot_paths["sq"], shot_paths["sh"]
        shot_render_path = f"{self.render_path}/ep{ep}/sq{sq}/sh{sh}/render"

        if not os.path.exists(shot_render_path):
            nuke.message(f"Shot render path not found: {shot_render_path}")
            return

        render_layers = os.listdir(shot_render_path)
        if not render_layers:
            nuke.message("No render layers found")
            return

        nodes_created = []

        for layer in render_layers:
            layer_dir = os.path.join(shot_render_path, layer)

            if not os.path.isdir(layer_dir):
                continue

            this_sequence = nuke.getFileNameList(layer_dir)
            if not this_sequence:
                continue

            this_layer_path = os.path.join(layer_dir, this_sequence[0])
            nuke.tprint(f"Imported layer: {this_layer_path}")

            render_read = nuke.createNode("Read", inpanel=False)
            render_read.knob("file").fromUserText(this_layer_path)
            render_read.autoplace()
            nodes_created.append(render_read)

        # Import camera
        try:
            cam = self.import_camera(selected_shot)
            if cam:
                cam.autoplace()
                nodes_created.append(cam)
        except:
            nuke.tprint("Camera import failed")

        # Select all created nodes
        for node in nodes_created:
            node.setSelected(True)

        # Create backdrop
        if nodes_created:
            nukescripts.autobackdrop.autoBackdrop()

    def open_comp_dir(self):
        """Open shot's comp directory in file explorer"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        shot_paths = self.get_shot_paths(selected_shot)
        if not shot_paths:
            nuke.message("Invalid shot format")
            return

        shot_comp_dir = shot_paths["comp_dir"]

        if sys.platform == 'win32':
            path = os.path.normpath(shot_comp_dir)
            try:
                subprocess.run(['explorer', path], check=True)
            except subprocess.CalledProcessError as e:
                nuke.tprint(f"Failed to open folder: {e}")
        else:
            print(f"Unsupported OS: {sys.platform}")

    def open_precomp_dir(self):
        """Open shot's precomp directory in file explorer"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        shot_paths = self.get_shot_paths(selected_shot)
        if not shot_paths:
            nuke.message("Invalid shot format")
            return

        shot_precomp_dir = shot_paths["precomp_dir"]

        if sys.platform == 'win32':
            path = os.path.normpath(shot_precomp_dir)
            try:
                subprocess.run(['explorer', path], check=True)
            except subprocess.CalledProcessError as e:
                nuke.tprint(f"Failed to open folder: {e}")
        else:
            print(f"Unsupported OS: {sys.platform}")


    def create_script(self):
        """Create new script for selected shot"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        paths = self.get_shot_paths(selected_shot)
        if not paths:
            nuke.message("Invalid shot format")
            return

        # Create directories
        for directory in [paths["nk_dir"], paths["exr_dir"], paths["mov_dir"]]:
            if not os.path.exists(directory):
                os.makedirs(directory)

        script_name = f"{selected_shot}_v01.nk"
        script_path = os.path.join(paths["nk_dir"], script_name)

        if os.path.exists(script_path):
            if not nuke.ask(f"Script '{script_name}' exists. Overwrite?"):
                return

#         if self.new_instance_check.value():
#             subprocess.Popen([nuke.EXE_PATH, script_path])
#         else:
        nuke.scriptClear()
        project_root_settings()
        nuke.root()['project_directory'].setValue(paths["comp_dir"])
        if self.comp_template_path:
            self.import_template(self.comp_template_path)
        nuke.scriptSaveAs(script_path)
        nuke.tprint(f"Created script: {script_path}")


    def open_script(self):
        """Open most recent script for selected shot"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        paths = self.get_shot_paths(selected_shot)
        if not paths:
            nuke.message("Invalid shot format")
            return

        nk_dir = paths["nk_dir"]
        try:
            nk_files = [f for f in os.listdir(nk_dir) if f.endswith('.nk')]
        except FileNotFoundError:
            nuke.message("No Nuke scripts found")
            return

        if not nk_files:
            nuke.message("No Nuke scripts found")
            return

        # Find highest version
        max_ver = 0
        recent_script = ""
        for nk in nk_files:
            match = re.search(r'_v(\d+)', nk)
            if match:
                ver = int(match.group(1))
                if ver >= max_ver:
                    max_ver = ver
                    recent_script = nk

        if not recent_script:
            recent_script = nk_files[0]

        recent_script_path = os.path.join(nk_dir, recent_script)
        try:
            nuke.scriptOpen(recent_script_path)
        except RuntimeError as e:
            nuke.tprint(f"Error opening script: {e}")

    def create_light_precomp(self):
        """Create light precomp script with render layers"""
        selected_shot = self.get_current_shot()
        if not selected_shot:
            nuke.message("No shot selected")
            return

        paths = self.get_shot_paths(selected_shot)
        if not paths:
            nuke.message("Invalid shot format")
            return

        # Create light_precomp directories
        ep, sq, sh = paths["ep"], paths["sq"], paths["sh"]
        precomp_base = f"{self.prj_comp_path}/ep{ep}/sq{sq}/sh{sh}/light_precomp"
        precomp_dirs = {
            "base": precomp_base,
            "nk": f"{precomp_base}/nk",
            "mov": f"{precomp_base}/mov"
        }

        # Create directories - os.makedirs handles forward slashes fine
        for directory in precomp_dirs.values():
            if not os.path.exists(directory):
                os.makedirs(directory)

        # Script setup
        script_name = f"{selected_shot}_light_precomp.nk"
        script_path = f"{precomp_dirs['nk']}/{script_name}"

        if os.path.exists(script_path):
            if not nuke.ask(f"Script '{script_name}' exists. Overwrite?"):
                nuke.scriptOpen(script_path)
                return

        nuke.scriptClear()
        project_root_settings()
        nuke.root()['project_directory'].setValue(precomp_dirs["base"])

        # Import template if exists
        if self.precomp_template_path and os.path.exists(self.precomp_template_path):
            self.import_template(self.precomp_template_path)

        # Find render layers
        shot_render_path = f"{self.render_path}/ep{ep}/sq{sq}/sh{sh}/render"
        if not os.path.exists(shot_render_path):
            nuke.message(f"No renders found at: {shot_render_path}")
            nuke.scriptSaveAs(script_path)
            return

        render_layers = [d for d in os.listdir(shot_render_path) if
                         os.path.isdir(os.path.join(shot_render_path, d))]

        # Update existing Read nodes
        for node in nuke.allNodes('Read'):
            file_path = node.knob('file').getValue()

            # Match render layer from existing path
            for layer in render_layers:
                if layer in file_path:
                    layer_dir = os.path.join(shot_render_path, layer)
                    sequence = nuke.getFileNameList(layer_dir)
                    if sequence:
                        new_path = os.path.join(layer_dir, sequence[0])
                        node.knob('file').fromUserText(new_path)
                        nuke.tprint(f"Updated Read node for: {layer}")
                    break

        # Update Write node
        for node in nuke.allNodes('Write'):
            write_path = f"{precomp_dirs['mov']}/{selected_shot}_light_precomp.mov"
            node.knob('file').setValue(write_path)
            nuke.tprint(f"Updated Write node path: {write_path}")

        nuke.scriptSaveAs(script_path)
        nuke.tprint(f"Created light precomp script: {script_path}")

_panel_instance = None

def show_panel():
    global _panel_instance
    if _panel_instance is None:
        _panel_instance = ShotManagerPanel()
    _panel_instance.showModalDialog()