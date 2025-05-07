# SPDX‑License‑Identifier: Apache‑2.0
# shot_manager.py – Main module file v0.1
# Copyright © 2025 AAStudio LLC. All rights reserved.

import os
import sys
import re
import json
import nuke
import nukescripts
from ..config import get_project_config
from ..config import project_root_settings
from datetime import datetime


_active_panel = None

def reload_shots():
    """Global function to call reload shots on the active panel"""
    global _active_panel
    print("RELOADING SHOTS")
    print("Active panel:", _active_panel)
    if _active_panel:
        _active_panel.scan_shot_dirs()
    else:
        print("No active Shot Manager panel found")

def create_script():
    """Global function to call create script on the active panel"""
    if _active_panel:
        _active_panel.create_script()
    else:
        print("No active Shot Manager panel found")

def open_script():
    """Global function to call open script on the active panel"""
    if _active_panel:
        _active_panel.open_script()
    else:
        print("No active Shot Manager panel found")


class ShotManagerPanel(nukescripts.PythonPanel):
    def __init__(self):
        nukescripts.PythonPanel.__init__(self, "Shot Manager")

        global _active_panel
        _active_panel = self

        # Base project path
        self.render_path = os.getenv("RENDER_PATH")
        # Default to local or elsewhere -- unfinished logic!
        if not self.render_path:
            self.render_path = get_project_config().get("projects.cinderella.local_render_path")
            if not os.path.exists(self.render_path):
                os.makedirs(self.render_path)

        self.cache_file = os.path.join(os.path.expanduser("~"), ".nuke", "shot_manager_cache.json")
        self.selected_script = ""

        # Define knobs for the panel
        self.episode_knob = nuke.String_Knob("episode", "Episode Filter")
        # self.sequence_knob = nuke.String_Knob("sequence", "Sequence Filter")
        self.shot_dropdown = nuke.Enumeration_Knob("shot", "Available Shots", [])
        self.create_btn = nuke.PyScript_Knob("create_script", "Create Script")
        self.open_btn = nuke.PyScript_Knob("open_script", "Open Script")
        self.reload_btn = nuke.PyScript_Knob("reload", "Reload Shots")
        self.new_instance_check = nuke.Boolean_Knob("new_instance", "Open in New Instance")
        self.cache_status = nuke.Text_Knob("cache_status", "Cache Status", "")

        # Add knobs to panel
        self.addKnob(self.episode_knob)
        # self.addKnob(self.sequence_knob)
        self.addKnob(self.reload_btn)
        self.addKnob(self.shot_dropdown)
        self.addKnob(self.create_btn)
        self.addKnob(self.open_btn)
        self.addKnob(self.new_instance_check)
        self.addKnob(self.cache_status)

        # Set default values
        self.new_instance_check.setValue(False)

        # Connect callbacks
        self.create_btn.setCommand("shot_manager.create_script()")
        self.open_btn.setCommand("shot_manager.open_script()")
        self.reload_btn.setCommand("shot_manager.reload_shots()")

        # Load from cache initially
        self.load_from_cache()

    def load_from_cache(self):
        """Load available shots from cache file if it exists and is recent"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)

                # Check if cache is recent (less than 1 day old)
                cache_time = datetime.strptime(cache_data.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
                current_time = datetime.now()

                if (current_time - cache_time).days < 1:
                    self.shot_dropdown.setValues(cache_data.get('shots', []))
                    self.cache_status.setValue(f"Using cached data from {cache_data.get('timestamp')}")
                    return True
            except Exception as e:
                print(f"Error loading cache: {e}")

        self.cache_status.setValue("No recent cache found. Use 'Reload Shots' to scan.")
        return False

    def save_to_cache(self, shots):
        """Save available shots to cache file"""
        try:
            cache_dir = os.path.dirname(self.cache_file)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            cache_data = {
                'shots': shots,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)

            self.cache_status.setValue(f"Cache updated: {cache_data['timestamp']}")
        except Exception as e:
            print(f"Error saving cache: {e}")
            self.cache_status.setValue(f"Cache error: {str(e)}")


    def scan_shot_dirs(self):
        """Scans the render directory structure to find shots with rendered sequences"""
        available_shots = []
        print("Inside scan_shot_dirs")
        print(f"Base path: {self.render_path}")
        print(f"Base path exists: {os.path.exists(self.render_path)}")
        # Get filters
        ep_filter = self.episode_knob.value().strip()
        # sq_filter = self.sequence_knob.value().strip()

        # Show a progress dialog
        task = nuke.ProgressTask("Scanning for shots")
        task.setMessage("Scanning render directories...")

        # Construct targeted paths based on filters
        scan_paths = []

        # Specific episode, all sequences
        if ep_filter:
            ep_path = f"{self.render_path}/ep{ep_filter}"
            if os.path.exists(ep_path):
                for sq_dir in os.listdir(ep_path):
                    if sq_dir.startswith("sq"):
                        scan_paths.append(os.path.join(ep_path, sq_dir))
        else:
            nuke.message("safe search")
            return
            # try:
            #     ep_dirs = [d for d in os.listdir(self.render_path) if d.startswith("ep")]
            #     for ep_dir in ep_dirs:
            #         ep_path = os.path.join(self.render_path, ep_dir)
            #         scan_paths.append(ep_path)
            # except Exception as e:
            #     print(f"Error finding episodes: {e}")
            #     # Fallback to base path
            #     scan_paths.append(self.render_path)

        # Process each scan path
        total_paths = len(scan_paths)
        for idx, scan_path in enumerate(scan_paths):
            if task.isCancelled():
                break

            task.setProgress(int(100 * idx / max(1, total_paths)))
            task.setMessage(f"Scanning: {scan_path}")

            for root, dirs, files in os.walk(scan_path):
                if task.isCancelled():
                    break

                # Check if we're in a render directory for a shot
                match = re.search(r'ep(\d+)[/\\]sq(\d+)[/\\]sh(\d+)[/\\]render', root)
                if match:
                    ep, sq, sh = match.groups()

                    # Apply filters if specified
                    if ep_filter and ep != ep_filter:
                        continue

                    shot_name = f"ep{ep}_sq{sq}_sh{sh}"

                    # Check for rendered sequences
                    # render_types = ["chars_layer", "env_layer", "matte_layer"]
                    has_render = False

                    # for render_type in render_types:
                        # render_dirs = [d for d in dirs if d.startswith(render_type) in d]
                    if dirs:
                        for render_dir in dirs:
                            render_path = os.path.join(root, render_dir)
                            if os.path.exists(render_path):
                                exr_files = [f for f in os.listdir(render_path) if f.endswith(".exr")]
                                if exr_files:
                                    has_render = True
                                    break

                    if has_render and shot_name not in available_shots:
                        available_shots.append(shot_name)

        # Update the dropdown menu
        available_shots.sort()
        self.shot_dropdown.setValues(available_shots)
        if available_shots:
            self.shot_dropdown.setValue(available_shots[0])

        # Save to cache
        self.save_to_cache(available_shots)

        task.setProgress(100)
        print(f"Found {len(available_shots)} shots with rendered sequences")


    def create_script(self):
        """Creates a new script and folder structure for the selected shot"""
        selected_shot = self.shot_dropdown.value()

        if not selected_shot:
            nuke.message("No shot selected. Please select a shot from the dropdown.")
            return

        # Parse shot name to get episode, sequence and shot numbers
        match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', selected_shot)
        if not match:
            nuke.message("Invalid shot format. Expected 'ep##_sq##_sh##'")
            return

        ep, sq, sh = match.groups()

        # Create paths
        comp_base = f"//192.168.99.202/prj/cinderella/render/ep{ep}/sq{sq}/sh{sh}/comp"
        nk_dir = os.path.join(comp_base, "nk")
        exr_dir = os.path.join(comp_base, "exr")
        mov_dir = os.path.join(comp_base, "mov")

        # Create directory structure
        for directory in [nk_dir, exr_dir, mov_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"Created directory: {directory}")

        # Create script file
        script_name = f"{selected_shot}_v01.nk"
        script_path = os.path.join(nk_dir, script_name)

        # Check if script already exists
        if os.path.exists(script_path):
            overwrite = nuke.ask(f"Script '{script_name}' already exists. Overwrite?")
            if not overwrite:
                return

        # Save current script if requested or create a new one
        if self.new_instance_check.value():
            # Launch a new Nuke instance with the script
            import subprocess
            nuke_path = nuke.EXE_PATH
            subprocess.Popen([nuke_path, script_path])
        else:
            # Create a new script in the current Nuke instance
            nuke.scriptClear()

            # Apply project settings from external config
            project_root_settings()

            # Set project directory
            nuke.root()['project_directory'].setValue(comp_base)

            # Save the script
            nuke.scriptSaveAs(script_path)
            print(f"Created script: {script_path}")


    def open_script(self):
        selected_shot = self.shot_dropdown.value()

        if not selected_shot:
            nuke.message("No shot selected. Please select a shot from the dropdown.")
            return

        # Parse shot name to get episode, sequence and shot numbers
        match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', selected_shot)
        if not match:
            nuke.message("Invalid shot format. Expected 'ep##_sq##_sh###_v##'")
            return

        ep, sq, sh = match.groups()

        nk_dir = f"//192.168.99.202/prj/cinderella/render/ep{ep}/sq{sq}/sh{sh}/comp/nk"
        nk_dir_file_list = os.listdir(nk_dir)
        nk_files = [f for f in nk_dir_file_list if f.endswith('.nk')]

        if not nk_files:
            nuke.message("No Nuke scripts to open here yet")
            return

        max_ver = 0
        recent_script = ""

        for nk in nk_files:
            match = re.search(r'_v(\d+)', nk)
            if match:
                ver = int(match.group(1))
                if max_ver <= ver:
                    max_ver = ver
                    recent_script = nk

        recent_script_path = f"{nk_dir}/{recent_script}"


        try:
            nuke.scriptOpen(recent_script_path)
        except RuntimeError as e:
            print(f"Error opening script: {e}")



_panel_instance = None

def show_panel():
    global _panel_instance

    if _panel_instance is None:
        _panel_instance = ShotManagerPanel()
    _panel_instance.showModalDialog()
