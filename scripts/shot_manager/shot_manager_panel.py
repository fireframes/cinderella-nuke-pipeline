# SPDX-License-Identifier: Apache-2.0
# shot_manager_panel.py - Qt-based Shot Manager Panel with Navigation
# Copyright © 2025 Maxim Maximov. All rights reserved.

from PySide2 import QtWidgets, QtCore, QtGui
import os
import sys
import re
import json
import nuke
import nukescripts
import subprocess
from datetime import datetime
from ..config import get_project_config
from ..config import project_root_settings
from ..cerebro import (publish_shot_to_cerebro, 
                        cerebro_database_connect,
                        construct_cerebro_task_url,
                        STATUSES,
                        pref)
from pycerebro import database, dbtypes, cargador
from ..tools import import_tools

_widget_instance = None


class ShotScannerWorker(QtCore.QObject):
    """Background worker to scan shots without freezing the UI."""
    finished = QtCore.Signal(list)
    progress = QtCore.Signal(str)

    def __init__(self, render_path):
        super(ShotScannerWorker, self).__init__()
        self.render_path = render_path
        self._is_cancelled = False

    def run(self):
        available_shots = []
        
        if not os.path.exists(self.render_path):
            self.finished.emit([])
            return

        try:
            # Level 1: Episodes
            with os.scandir(self.render_path) as ep_it:
                for ep_entry in ep_it:
                    if self._is_cancelled: break
                    if not ep_entry.is_dir() or not ep_entry.name.startswith('ep'): continue

                    # Level 2: Sequences
                    path_ep = ep_entry.path
                    with os.scandir(path_ep) as sq_it:
                        for sq_entry in sq_it:
                            if not sq_entry.is_dir() or not sq_entry.name.startswith('sq'): continue

                            # Level 3: Shots
                            path_sq = sq_entry.path
                            with os.scandir(path_sq) as sh_it:
                                for sh_entry in sh_it:
                                    if not sh_entry.is_dir() or not sh_entry.name.startswith('sh'): continue
                                    
                                    # Level 4: Render folder
                                    render_root = os.path.join(sh_entry.path, "render")
                                    if not os.path.exists(render_root): continue

                                    # Check for any .exr efficiently
                                    if self.fast_check_renders(render_root):
                                        shot_name = f"{ep_entry.name}_{sq_entry.name}_{sh_entry.name}"
                                        available_shots.append(shot_name)
                                        self.progress.emit(f"Found: {shot_name}")

        except Exception as e:
            print(f"Scan error: {e}")

        available_shots.sort()
        self.finished.emit(available_shots)

    def fast_check_renders(self, render_root):
        """
        Checks for EXRs using an iterator. 
        Returns True immediately on the first EXR found.
        """
        try:
            with os.scandir(render_root) as layers:
                for layer in layers:
                    if not layer.is_dir(): continue
                    
                    with os.scandir(layer.path) as files:
                        for f in files:
                            if f.name.lower().endswith('.exr'):
                                return True
        except OSError:
            pass
        return False

    def cancel(self):
        self._is_cancelled = True


class ShotManagerWidget(QtWidgets.QWidget):
    def __init__(self):
        super(ShotManagerWidget, self).__init__()

        self.setWindowTitle("Shot Manager")
        self.setMinimumSize(600, 500)

        self.is_initialized = False

        self.config = get_project_config()

        # Base paths
        self.render_path = self.config.get("server_render_path")
        self.prj_comp_path = self.config.get("server_comp_path")
        self.prj_cache_path_old = self.config.get("cache_path_old")
        self.prj_cache_path_new = self.config.get("cache_path_new")
        self.comp_template_path = self.config.get("tools", {}).get("comp_template_path")
        self.precomp_template_path = self.config.get("tools", {}).get("precomp_template_path")

        # Cache and State
        self.cache_file = os.path.join(os.path.expanduser("~"), ".nuke", "shot_manager_cache.json")
        self.all_shots = []
        self.shot_data = {}
        self.current_shot_thumbs = {}
        self.current_shot_index = 0
        self.shot_context = None

        self.thread = None
        self.worker = None
        self.loading_label = QtWidgets.QLabel("Scanning...")

        self.setup_ui()
        self.connect_signals()

    def showEvent(self, event):
        super(ShotManagerWidget, self).showEvent(event)
        if not self.is_initialized:
            # QTimer to avoid blocking the UI thread while the panel is drawn.
            QtCore.QTimer.singleShot(0, self.initialize_data)
            self.is_initialized = True

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout()

        # Upper panel - image preview with navigation
        upper_panel = QtWidgets.QWidget()
        upper_layout = QtWidgets.QHBoxLayout()

        # Left arrow button
        self.prev_shot_btn = QtWidgets.QPushButton("◀")
        self.prev_shot_btn.setMaximumWidth(70)
        self.prev_shot_btn.setMinimumHeight(100)
        self.prev_shot_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
                background-color: #404040;
                border: 1px solid #666;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #303030;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
        """)

        # Image display area
        image_widget = QtWidgets.QWidget()
        image_layout = QtWidgets.QVBoxLayout()
        image_layout.setContentsMargins(0, 0, 0, 0)

        # Shot info label
        self.shot_info_label = QtWidgets.QLabel("Select a shot")
        self.shot_info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.shot_info_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #333; color: white;")

        # Image display
        self.image_label = QtWidgets.QLabel("Select a shot to preview")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        # self.image_label.setStyleSheet("background-color: #2a2a2a; border: 1px solid #555;")
        self.pixmap = QtGui.QPixmap()

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        # Version dropdown below image
        version_layout = QtWidgets.QHBoxLayout()
        version_layout.addWidget(QtWidgets.QLabel("Version:"))
        self.version_dropdown = QtWidgets.QComboBox()
        self.version_dropdown.setMaximumWidth(100)
        version_layout.addWidget(self.version_dropdown)
        version_layout.addStretch()

        image_layout.addWidget(self.shot_info_label)
        image_layout.addWidget(self.scroll_area)
        image_layout.addLayout(version_layout)
        image_widget.setLayout(image_layout)

        # Right arrow button
        self.next_shot_btn = QtWidgets.QPushButton("▶")
        self.next_shot_btn.setMaximumWidth(70)
        self.next_shot_btn.setMinimumHeight(100)
        self.next_shot_btn.setStyleSheet(self.prev_shot_btn.styleSheet())

        upper_layout.addWidget(self.prev_shot_btn)
        upper_layout.addWidget(image_widget, 1)
        upper_layout.addWidget(self.next_shot_btn)
        upper_panel.setLayout(upper_layout)

        # Lower panel - controls
        lower_panel = QtWidgets.QWidget()
        lower_layout = QtWidgets.QHBoxLayout()

        # Filter section
        filter_group = QtWidgets.QGroupBox("Shot Filter")
        filter_layout = QtWidgets.QVBoxLayout()

        # Episode dropdown
        ep_layout = QtWidgets.QHBoxLayout()
        ep_layout.addWidget(QtWidgets.QLabel("Episode:"))
        self.episode_dropdown = QtWidgets.QComboBox()
        ep_layout.addWidget(self.episode_dropdown)
        filter_layout.addLayout(ep_layout)

        # Sequence dropdown
        sq_layout = QtWidgets.QHBoxLayout()
        sq_layout.addWidget(QtWidgets.QLabel("Sequence:"))
        self.sequence_dropdown = QtWidgets.QComboBox()
        sq_layout.addWidget(self.sequence_dropdown)
        filter_layout.addLayout(sq_layout)

        # Shot dropdown
        sh_layout = QtWidgets.QHBoxLayout()
        sh_layout.addWidget(QtWidgets.QLabel("Shot:"))
        self.shot_dropdown = QtWidgets.QComboBox()
        sh_layout.addWidget(self.shot_dropdown)
        filter_layout.addLayout(sh_layout)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Force Refresh")
        self.refresh_btn.setToolTip("Force update shot list from server (ignores 24-hour cache)")

        self.set_as_current_btn = QtWidgets.QPushButton("Set Current")
        self.set_as_current_btn.setToolTip("Set initially opened script as current shot context in Shot Manager")

        buttons_layout.addWidget(self.refresh_btn, 1)
        buttons_layout.addWidget(self.set_as_current_btn, 1)

        filter_layout.addLayout(buttons_layout)

        filter_group.setLayout(filter_layout)
        lower_layout.addWidget(filter_group)

        # Action buttons - Compositing
        comp_group = QtWidgets.QGroupBox("Compositing")
        comp_layout = QtWidgets.QVBoxLayout()

        self.open_btn = QtWidgets.QPushButton("Open Comp")
        self.create_btn = QtWidgets.QPushButton("Create Comp")
        self.open_comp_dir_btn = QtWidgets.QPushButton("Open Comp Directory")
        self.import_template_btn = QtWidgets.QPushButton("Import Template")
        self.import_render_btn = QtWidgets.QPushButton("Import Render")

        comp_layout.addWidget(self.open_btn)
        comp_layout.addWidget(self.create_btn)
        comp_layout.addWidget(self.open_comp_dir_btn)
        comp_layout.addWidget(self.import_template_btn)
        comp_layout.addWidget(self.import_render_btn)

        comp_group.setLayout(comp_layout)
        lower_layout.addWidget(comp_group)

        # Action buttons - Lighting + Publish
        light_publish_group = QtWidgets.QVBoxLayout()

        light_group = QtWidgets.QGroupBox("Lighting")
        light_layout = QtWidgets.QVBoxLayout()
        self.create_light_precomp_btn = QtWidgets.QPushButton("Create Light Precomp")
        self.open_precomp_dir_btn = QtWidgets.QPushButton("Open Precomp Directory")
        light_layout.addWidget(self.create_light_precomp_btn)
        light_layout.addWidget(self.open_precomp_dir_btn)
        light_group.setLayout(light_layout)

        publish_group = QtWidgets.QGroupBox("Publish")
        publish_layout = QtWidgets.QVBoxLayout()
        self.publish_to_cerebro_btn = QtWidgets.QPushButton("Publish to Cerebro")
        publish_layout.addWidget(self.publish_to_cerebro_btn)
        publish_group.setLayout(publish_layout)

        light_publish_group.addWidget(light_group)
        light_publish_group.addWidget(publish_group)

        lower_layout.addLayout(light_publish_group)
        lower_panel.setLayout(lower_layout)

        # Add panels to main layout
        main_layout.addWidget(upper_panel)
        main_layout.addWidget(lower_panel)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def connect_signals(self):
        # Connect dropdowns
        self.episode_dropdown.currentTextChanged.connect(self.on_episode_changed)
        self.sequence_dropdown.currentTextChanged.connect(self.on_sequence_changed)
        self.shot_dropdown.currentTextChanged.connect(self.on_shot_changed)
        self.version_dropdown.currentTextChanged.connect(self.on_version_changed)

        # Connect navigation buttons
        self.prev_shot_btn.clicked.connect(self.go_to_previous_shot)
        self.next_shot_btn.clicked.connect(self.go_to_next_shot)

        # Connect action buttons
        self.set_as_current_btn.clicked.connect(self.set_as_current_shot)
        self.refresh_btn.clicked.connect(self.force_refresh)
        self.create_btn.clicked.connect(self.create_script)
        self.open_btn.clicked.connect(self.open_script)
        self.open_comp_dir_btn.clicked.connect(self.open_comp_dir)
        self.import_render_btn.clicked.connect(import_tools.import_render_layers)
        self.import_template_btn.clicked.connect(import_tools.import_template)
        self.create_light_precomp_btn.clicked.connect(self.create_light_precomp)
        self.open_precomp_dir_btn.clicked.connect(self.open_precomp_dir)
        self.publish_to_cerebro_btn.clicked.connect(self.publish_shot)

    def initialize_data(self):
        if not self.load_from_cache():
            self.scan_shot_dirs() # This triggers the thread
        else:
            self.set_initial_shot_context()

    def scan_shot_dirs(self):
        # 1. Check if a scan is already running or cleaning up
        if hasattr(self, 'thread') and self.thread is not None:
            if self.thread.isRunning():
                nuke.tprint("Scan already in progress.")
                return

        if not os.path.exists(self.render_path):
            nuke.message(f"Render path not found: {self.render_path}")
            return

        # 2. UI Feedback
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Scanning...")
        
        # 3. Setup Thread (Standard Qt Pattern)
        self.thread = QtCore.QThread()
        self.worker = ShotScannerWorker(self.render_path)
        self.worker.moveToThread(self.thread)

        # 4. Connect Signals
        self.thread.started.connect(self.worker.run)
        
        # CEnsure data is passed cleanly before cleanup
        self.worker.finished.connect(self.on_scan_finished)
        
        # Standard Cleanup
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # 5. Start
        self.thread.start()

    def on_scan_finished(self, found_shots):
        """
        Called when the background thread finishes. 
        Runs on the Main Thread automatically via Qt Signal/Slot.
        """
        try:
            self.all_shots = found_shots
            
            # Re-enable UI
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Force Refresh")
            
            # Update Data
            self.build_shot_hierarchy()
            self.update_episode_dropdown()
            self.save_to_cache(found_shots)
            
            # Handle initialization logic
            if not self.is_initialized:
                 self.set_initial_shot_context()
            
            nuke.tprint(f"Scan complete. Found {len(found_shots)} shots.")

        except Exception as e:
            nuke.tprint(f"Error updating UI after scan: {e}")
            # Ensure button is re-enabled even if an error occurs
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Force Refresh")

    def on_scan_progress(self, msg):
        # Optional: Update status bar or log
        pass 

    def set_initial_shot_context(self):
        script_path = nuke.root().name()
        shot_name = None

        if script_path and script_path != 'Root':
            match = re.search(r'(ep\d+_sq\d+_sh\d+)', script_path)
            if match:
                shot_name_from_script = match.group(1)
                if shot_name_from_script in self.all_shots:
                    shot_name = shot_name_from_script

        if not shot_name and self.all_shots:
            shot_name = self.all_shots[0]

        if shot_name:
            self.navigate_to_shot_by_name(shot_name)
        else:
            self.update_shot_info()
            self.update_navigation_buttons()

    def load_from_cache(self):
        if not os.path.exists(self.cache_file):
            return False

        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            cache_time = datetime.strptime(cache_data.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
            current_time = datetime.now()

            if (current_time - cache_time).total_seconds() < 86400:  # 24 hours
                self.all_shots = cache_data.get('shots', [])
                self.build_shot_hierarchy()
                self.update_episode_dropdown()
                return True
            return False

        except Exception as e:
            print(f"Error loading cache: {e}")
            return False

    def save_to_cache(self, shots):
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

        except Exception as e:
            print(f"Error saving cache: {e}")

    def force_refresh(self):
        nuke.tprint("Forcing refresh of shot list...")
        self.refresh_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()  # Allow UI to update

        try:
            self.scan_shot_dirs()
            self.set_initial_shot_context()
            nuke.tprint("Shot list refreshed successfully.")
        finally:
            self.refresh_btn.setEnabled(True)

    def build_shot_hierarchy(self):
        self.shot_data = {}

        for shot in self.all_shots:
            match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', shot)
            if not match:
                continue

            ep, sq, sh = match.groups()

            if ep not in self.shot_data:
                self.shot_data[ep] = {}
            if sq not in self.shot_data[ep]:
                self.shot_data[ep][sq] = []

            self.shot_data[ep][sq].append(sh)

    def update_episode_dropdown(self):
        self.episode_dropdown.blockSignals(True)
        self.episode_dropdown.clear()

        if not self.shot_data:
            self.episode_dropdown.addItem("No episodes found")
        else:
            episodes = sorted(self.shot_data.keys())
            self.episode_dropdown.addItems(episodes)

        self.episode_dropdown.blockSignals(False)
        if self.episode_dropdown.count() > 0:
            self.episode_dropdown.setCurrentIndex(0)
            self.on_episode_changed()

    def update_sequence_dropdown(self):
        self.sequence_dropdown.blockSignals(True)
        self.sequence_dropdown.clear()

        selected_ep = self.episode_dropdown.currentText()
        if selected_ep and selected_ep in self.shot_data:
            sequences = sorted(self.shot_data[selected_ep].keys())
            self.sequence_dropdown.addItems(sequences)
        else:
            self.sequence_dropdown.addItem("Select Sequence")

        self.sequence_dropdown.blockSignals(False)
        if self.sequence_dropdown.count() > 0:
            self.sequence_dropdown.setCurrentIndex(0)
            self.on_sequence_changed()

    def update_shot_dropdown(self):
        self.shot_dropdown.blockSignals(True)
        self.shot_dropdown.clear()

        selected_ep = self.episode_dropdown.currentText()
        selected_sq = self.sequence_dropdown.currentText()

        if (selected_ep and selected_sq and
                selected_ep in self.shot_data and
                selected_sq in self.shot_data[selected_ep]):
            shots = sorted(self.shot_data[selected_ep][selected_sq])
            self.shot_dropdown.addItems(shots)
        else:
            self.shot_dropdown.addItem("Select Shot")

        self.shot_dropdown.blockSignals(False)
        if self.shot_dropdown.count() > 0:
            self.shot_dropdown.setCurrentIndex(0)
            self.on_shot_changed()

    def on_episode_changed(self):
        self.update_sequence_dropdown()

    def on_sequence_changed(self):
        self.update_shot_dropdown()
    
    def on_shot_changed(self):
        self.shot_context = self.get_current_shot()
        self.update_current_shot_index()
        self.scan_for_thumbnails()
        self.update_preview()
        self.update_navigation_buttons()
        self.update_shot_info()

    def on_version_changed(self):
        self.update_preview()

    def update_current_shot_index(self):
        if self.shot_context and self.shot_context in self.all_shots:
            self.current_shot_index = self.all_shots.index(self.shot_context)
        else:
            self.current_shot_index = 0

    def update_navigation_buttons(self):
        self.prev_shot_btn.setEnabled(self.current_shot_index > 0)
        self.next_shot_btn.setEnabled(self.current_shot_index < len(self.all_shots) - 1)

    def update_shot_info(self):
        if self.shot_context:
            shot_num = self.current_shot_index + 1
            total_shots = len(self.all_shots)
            self.shot_info_label.setText(f"{self.shot_context} ({shot_num}/{total_shots})")
        else:
            self.shot_info_label.setText("Select a shot")

    def go_to_previous_shot(self):
        if self.current_shot_index > 0:
            self.current_shot_index -= 1
            self.navigate_to_shot_by_index(self.current_shot_index)

    def go_to_next_shot(self):
        if self.current_shot_index < len(self.all_shots) - 1:
            self.current_shot_index += 1
            self.navigate_to_shot_by_index(self.current_shot_index)

    def navigate_to_shot_by_name(self, shot_name):
        if shot_name in self.all_shots:
            index = self.all_shots.index(shot_name)
            self.navigate_to_shot_by_index(index)

    def navigate_to_shot_by_index(self, index):
        if not (0 <= index < len(self.all_shots)):
            return

        target_shot = self.all_shots[index]
        match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', target_shot)
        if not match:
            return

        ep, sq, sh = match.groups()

        self.episode_dropdown.blockSignals(True)
        self.sequence_dropdown.blockSignals(True)
        self.shot_dropdown.blockSignals(True)

        ep_index = self.episode_dropdown.findText(ep)
        if ep_index >= 0:
            self.episode_dropdown.setCurrentIndex(ep_index)
            self.update_sequence_dropdown()

        sq_index = self.sequence_dropdown.findText(sq)
        if sq_index >= 0:
            self.sequence_dropdown.setCurrentIndex(sq_index)
            self.update_shot_dropdown()

        sh_index = self.shot_dropdown.findText(sh)
        if sh_index >= 0:
            self.shot_dropdown.setCurrentIndex(sh_index)

        self.episode_dropdown.blockSignals(False)
        self.sequence_dropdown.blockSignals(False)
        self.shot_dropdown.blockSignals(False)

        # Manually trigger updates as signals were blocked
        self.on_shot_changed()

    def get_current_shot(self):
        ep = self.episode_dropdown.currentText()
        sq = self.sequence_dropdown.currentText()
        sh = self.shot_dropdown.currentText()

        if not all([ep, sq, sh]) or any("Select" in t for t in [ep, sq, sh]) or "No" in ep:
            return None

        return f"ep{ep}_sq{sq}_sh{sh}"

    def set_as_current_shot(self):
        self.set_initial_shot_context()

    def get_shot_paths(self, selected_shot=None, show_message=False):
        if selected_shot is None:
            selected_shot = self.shot_context

        if not selected_shot:
            if show_message:
                nuke.message("No shot selected.")
            return None

        match = re.match(r'ep(\d+)_sq(\d+)_sh(\d+)', selected_shot)
        if not match:
            if show_message:
                nuke.message(f"Invalid shot format: {selected_shot}")
            return None

        ep, sq, sh = match.groups()
        shot_comp_path = f"{self.prj_comp_path}/ep{ep}/sq{sq}/sh{sh}/comp"
        shot_precomp_path = f"{self.prj_comp_path}/ep{ep}/sq{sq}/sh{sh}/light_precomp"
        shot_cam_path = f"{self.prj_cache_path_new}/ep{ep}/sq{sq}/sh{sh}/src/shot_camera.abc"

        if not os.path.exists(shot_cam_path):
            shot_cam_path = f"{self.prj_cache_path_old}/ep{ep}/sq{sq}/sh{sh}/src/shot_camera.abc"

        return {
            "shot_name": selected_shot,
            "ep": ep, "sq": sq, "sh": sh,
            "comp_dir": shot_comp_path,
            "precomp_dir": shot_precomp_path,
            "cam_dir": shot_cam_path,
            "nk_dir": os.path.join(shot_comp_path, "nk"),
            "exr_dir": os.path.join(shot_comp_path, "exr"),
            "mov_dir": os.path.join(shot_comp_path, "mov"),
            "thumb_dir": os.path.join(shot_comp_path, "mov/.thumb"),
        }

    def scan_for_thumbnails(self):
        self.current_shot_thumbs = {}
        self.version_dropdown.blockSignals(True)
        self.version_dropdown.clear()

        shot_paths = self.get_shot_paths()
        if not shot_paths:
            self.version_dropdown.addItem("No versions")
            self.version_dropdown.blockSignals(False)
            return

        thumb_dir = shot_paths["thumb_dir"]
        if not os.path.exists(thumb_dir):
            self.version_dropdown.addItem("No thumbnails")
            self.version_dropdown.blockSignals(False)
            return

        try:
            files = os.listdir(thumb_dir)
            thumb_pattern = re.compile(r'(.+)_v(\d+).*\.(jpg|jpeg|png)', re.IGNORECASE)

            for f in files:
                match = thumb_pattern.match(f)
                if match:
                    base_name, version, ext = match.groups()
                    version_key = f"v{version.zfill(2)}"
                    self.current_shot_thumbs[version_key] = os.path.join(thumb_dir, f)

            if self.current_shot_thumbs:
                versions = sorted(self.current_shot_thumbs.keys(), reverse=True)
                self.version_dropdown.addItems(versions)
                self.version_dropdown.setCurrentIndex(0)
            else:
                self.version_dropdown.addItem("No thumbnails")

        except Exception as e:
            print(f"Error scanning thumbnails: {e}")
            self.version_dropdown.addItem("Error")

        self.version_dropdown.blockSignals(False)

    def update_preview(self):
        if not self.shot_context:
            self.image_label.clear()
            self.pixmap = QtGui.QPixmap()
            self.image_label.setText("Select a shot to preview")
            return

        selected_version = self.version_dropdown.currentText()
        if selected_version and selected_version in self.current_shot_thumbs:
            thumb_path = self.current_shot_thumbs[selected_version]
            self.load_thumb_preview(thumb_path)
        else:
            self.image_label.clear()
            self.pixmap = QtGui.QPixmap()
            self.image_label.setText(f"No preview available for:\n{self.shot_context}")

    def load_thumb_preview(self, thumb_path):
        try:
            self.pixmap = QtGui.QPixmap(thumb_path)
            if self.pixmap.isNull():
                self.image_label.setText(f"Could not load:\n{thumb_path}")
                return
            QtCore.QTimer.singleShot(0, self._update_scaled_pixmap)
        except Exception as e:
            self.image_label.setText(f"Error loading image:\n{str(e)}")

    def scaledPixmap(self):
        available_size = self.scroll_area.viewport().size()
        if available_size.width() <= 0 or available_size.height() <= 0:
            available_size = QtCore.QSize(self.image_label.width(), self.image_label.height())
        return self.pixmap.scaled(available_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

    def resizeEvent(self, event):
        super(ShotManagerWidget, self).resizeEvent(event)
        if self.image_label.isVisible() and not self.pixmap.isNull():
            self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self.pixmap.isNull():
            scaled = self.scaledPixmap()
            if not scaled.isNull():
                self.image_label.setPixmap(scaled)
                self.image_label.resize(scaled.size())

    def create_script(self):
        paths = self.get_shot_paths(show_message=True)
        if not paths:
            return

        self.update_cerebro_status_to_inprogress(paths['shot_name'])

        for directory in [paths["nk_dir"], paths["exr_dir"], paths["mov_dir"], paths["thumb_dir"]]:
            if not os.path.exists(directory):
                os.makedirs(directory)

        script_name = f"{paths['shot_name']}_v01.nk"
        script_path = os.path.join(paths["nk_dir"], script_name)

        if os.path.exists(script_path):
            if not nuke.ask(f"Script '{script_name}' exists. Overwrite?"):
                return

        nuke.scriptClear()
        project_root_settings()
        nuke.root()['project_directory'].setValue(paths["comp_dir"])
        nuke.scriptSaveAs(script_path)
        nuke.tprint(f"Created script: {script_path}")

    def open_script(self):
        paths = self.get_shot_paths(show_message=True)
        if not paths:
            return

        nk_dir = paths["nk_dir"]
        try:
            nk_files = [f for f in os.listdir(nk_dir) if f.endswith('.nk')]
        except FileNotFoundError:
            nuke.message("No Nuke scripts found for this shot.")
            return

        if not nk_files:
            nuke.message("No Nuke scripts found for this shot.")
            return

        recent_script = max(nk_files,
                            key=lambda f: (int(re.search(r'_v(\d+)', f).group(1)) if re.search(r'_v(\d+)', f) else 0,
                                           f))

        if not recent_script:
            recent_script = nk_files[0]

        recent_script_path = os.path.join(nk_dir, recent_script)

        self.update_cerebro_status_to_inprogress(paths['shot_name'])

        try:
            nuke.scriptOpen(recent_script_path)

        except RuntimeError as e:
            nuke.tprint(f"Error opening script: {e}")
            return None

    def update_cerebro_status_to_inprogress(self, shot_name):
        """
        Updates the shot status in Cerebro to 'in progress' if it is currently 
        'to fix' or 'ready for operation'.
        """
        nuke.tprint(f"Attempting Cerebro status update for: {shot_name}")
        
        try:
            # Connect
            db = cerebro_database_connect()
            if not db:
                nuke.tprint("Cerebro: Could not connect to database.")
                return

            # Find Task
            task_url = construct_cerebro_task_url(shot_name)
            # Ensure safe slashes just in case
            task_url = task_url.replace('\\', '/') 
            
            task = db.task_by_url(task_url)
            
            if not task or len(task) == 0 or task[0] is None:
                nuke.tprint(f"Cerebro: Task not found for URL: {task_url}")
                return

            task_id = task[0]
            
            # Get current status
            task_details = db.task(task_id)
            if not task_details:
                return

            task_curr_status = task_details[37] # Index 37 is status ID

            # Check if update is needed
            if task_curr_status == STATUSES['to_fix'] or task_curr_status == STATUSES['ready_fw']:
                db.task_set_status(task_id, STATUSES['in_progress'])
                nuke.tprint(f"Cerebro: {shot_name} status updated to 'in progress'")
            else:
                nuke.tprint(f"Cerebro: Status update not required (Current ID: {task_curr_status})")

        except Exception as e:
            nuke.tprint(f"Cerebro Error: {e}")        

    def open_comp_dir(self):
        paths = self.get_shot_paths(show_message=True)
        if not paths:
            return
        if os.path.exists(paths["comp_dir"]):
            self._open_directory(paths["comp_dir"])
        else:
            nuke.message("Comp directory does not exist.")

    def open_precomp_dir(self):
        paths = self.get_shot_paths(show_message=True)
        if not paths:
            return
        self._open_directory(paths["precomp_dir"])

    def _open_directory(self, directory):
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
            if sys.platform == 'win32':
                os.startfile(os.path.normpath(directory))
            elif sys.platform == 'darwin':
                subprocess.run(['open', directory])
            else:
                subprocess.run(['xdg-open', directory])
        except Exception as e:
            nuke.tprint(f"Failed to open folder: {e}")

    def create_light_precomp(self):
        paths = self.get_shot_paths(show_message=True)
        if not paths:
            return

        selected_shot = paths["shot_name"]
        ep, sq, sh = paths["ep"], paths["sq"], paths["sh"]
        precomp_base = paths["precomp_dir"]
        precomp_dirs = {
            "base": precomp_base,
            "nk": os.path.join(precomp_base, "nk"),
            "mov": os.path.join(precomp_base, "mov")
        }

        for directory in precomp_dirs.values():
            if not os.path.exists(directory):
                os.makedirs(directory)

        script_name = f"{selected_shot}_light_precomp.nk"
        script_path = os.path.join(precomp_dirs['nk'], script_name)

        if os.path.exists(script_path):
            if not nuke.ask(f"Script '{script_name}' exists. Overwrite?"):
                nuke.scriptOpen(script_path)
                return

        nuke.scriptClear()
        project_root_settings()
        nuke.root()['project_directory'].setValue(precomp_dirs["base"])

        if self.precomp_template_path and os.path.exists(self.precomp_template_path):
            nuke.nodePaste(self.precomp_template_path)

        shot_render_path = f"{self.render_path}/ep{ep}/sq{sq}/sh{sh}/render"
        if not os.path.exists(shot_render_path):
            nuke.message(f"No renders found at: {shot_render_path}")
            nuke.scriptSaveAs(script_path)
            return

        render_layers = [d for d in os.listdir(shot_render_path) if os.path.isdir(os.path.join(shot_render_path, d))]

        for node in nuke.allNodes('Read'):
            file_path = node['file'].getValue()
            for layer in render_layers:
                if layer in file_path:
                    layer_dir = os.path.join(shot_render_path, layer).replace('\\', '/')
                    sequence = nuke.getFileNameList(layer_dir)
                    if sequence:
                        new_path = os.path.join(layer_dir, sequence[0]).replace('\\', '/')
                        node['file'].fromUserText(new_path)
                        nuke.tprint(f"Updated Read node for: {layer}")
                    break

        for node in nuke.allNodes('Write'):
            write_path = os.path.join(precomp_dirs['mov'], f"{selected_shot}_light_precomp.mov").replace('\\', '/')
            node['file'].setValue(write_path)
            nuke.tprint(f"Updated Write node path: {write_path}")

        nuke.scriptSaveAs(script_path)
        nuke.tprint(f"Created light precomp script: {script_path}")

    def publish_shot(self):
        if self.shot_context is None:
            nuke.message("No shot selected.")
            return
        publish_shot_to_cerebro(self.shot_context)

    def reload_context(self):
        self.shot_context = self.get_current_shot()


def show_floating_panel():
    global _widget_instance
    if _widget_instance is None:
        _widget_instance = ShotManagerWidget()

    _widget_instance.reload_context()
    _widget_instance.show()
    _widget_instance.raise_()
    _widget_instance.activateWindow()

    def on_destroy():
        global _widget_instance
        _widget_instance = None
    _widget_instance.destroyed.connect(on_destroy)


def create_shot_manager_panel():
    return ShotManagerWidget()
