# SPDX-License-Identifier: Apache-2.0
# shot_manager_panel.py - Qt-based Shot Manager Panel with Navigation
# Copyright © 2025 Max Jemer. All rights reserved.

from PySide2 import QtWidgets, QtCore, QtGui
import os
import re
import nuke
import nukescripts

from .pipeline_client import PipelineClient, PipelineError
from ..tools import import_tools

_widget_instance = None


# ---------------------------------------------------------------------------
# Background worker — HTTP scan instead of filesystem walk
# ---------------------------------------------------------------------------

class ShotScannerWorker(QtCore.QObject):
    """Background worker to scan shots without freezing the UI."""
    finished = QtCore.Signal(list)
    progress = QtCore.Signal(str)

    def __init__(self, client: PipelineClient):
        super(ShotScannerWorker, self).__init__()
        self.client = client
        self._is_cancelled = False

    def run(self):
        if self._is_cancelled:
            self.finished.emit([])
            return
        try:
            self.progress.emit("Requesting shot scan from backend...")
            self.client.scan_shots()
            shots_data = self.client.get_shots()
            shot_ids = [s["shot_id"] for s in shots_data]
            shot_ids.sort()
            self.finished.emit(shot_ids)
        except PipelineError as exc:
            nuke.tprint(f"Shot scan error: {exc}")
            self.finished.emit([])

    def cancel(self):
        self._is_cancelled = True


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class ShotManagerWidget(QtWidgets.QWidget):
    def __init__(self):
        super(ShotManagerWidget, self).__init__()

        self.setWindowTitle("Shot Manager")
        self.setMinimumSize(600, 500)

        self.is_initialized = False

        self.client = PipelineClient()

        # Cache and State
        self.all_shots = []
        self.shot_data = {}
        self.current_shot_thumbs = {}
        self.current_shot_index = 0
        self.shot_context = None
        self._shot_detail_cache = {}  # shot_id → detail dict from backend

        self.thread = None
        self.worker = None
        self.loading_label = QtWidgets.QLabel("Scanning...")

        self.setup_ui()
        self.connect_signals()

    def showEvent(self, event):
        super(ShotManagerWidget, self).showEvent(event)
        if not self.is_initialized:
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

        ep_layout = QtWidgets.QHBoxLayout()
        ep_layout.addWidget(QtWidgets.QLabel("Episode:"))
        self.episode_dropdown = QtWidgets.QComboBox()
        ep_layout.addWidget(self.episode_dropdown)
        filter_layout.addLayout(ep_layout)

        sq_layout = QtWidgets.QHBoxLayout()
        sq_layout.addWidget(QtWidgets.QLabel("Sequence:"))
        self.sequence_dropdown = QtWidgets.QComboBox()
        sq_layout.addWidget(self.sequence_dropdown)
        filter_layout.addLayout(sq_layout)

        sh_layout = QtWidgets.QHBoxLayout()
        sh_layout.addWidget(QtWidgets.QLabel("Shot:"))
        self.shot_dropdown = QtWidgets.QComboBox()
        sh_layout.addWidget(self.shot_dropdown)
        filter_layout.addLayout(sh_layout)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Force Refresh")
        self.refresh_btn.setToolTip("Force update shot list from server (ignores cache)")
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
        self.open_precomp_btn = QtWidgets.QPushButton("Open Light Precomp")
        self.create_precomp_btn = QtWidgets.QPushButton("Create Light Precomp")
        self.open_precomp_dir_btn = QtWidgets.QPushButton("Open Precomp Directory")
        light_layout.addWidget(self.open_precomp_btn)
        light_layout.addWidget(self.create_precomp_btn)
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

        main_layout.addWidget(upper_panel)
        main_layout.addWidget(lower_panel)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def connect_signals(self):
        self.episode_dropdown.currentTextChanged.connect(self.on_episode_changed)
        self.sequence_dropdown.currentTextChanged.connect(self.on_sequence_changed)
        self.shot_dropdown.currentTextChanged.connect(self.on_shot_changed)
        self.version_dropdown.currentTextChanged.connect(self.on_version_changed)

        self.prev_shot_btn.clicked.connect(self.go_to_previous_shot)
        self.next_shot_btn.clicked.connect(self.go_to_next_shot)

        self.set_as_current_btn.clicked.connect(self.set_as_current_shot)
        self.refresh_btn.clicked.connect(self.force_refresh)
        self.create_btn.clicked.connect(self.create_script)
        self.open_btn.clicked.connect(self.open_script)
        self.open_comp_dir_btn.clicked.connect(self.open_comp_dir)
        self.import_render_btn.clicked.connect(self.import_render)
        self.import_template_btn.clicked.connect(import_tools.import_template)
        self.open_precomp_btn.clicked.connect(self.open_precomp)
        self.create_precomp_btn.clicked.connect(self.create_precomp)
        self.open_precomp_dir_btn.clicked.connect(self.open_precomp_dir)
        self.publish_to_cerebro_btn.clicked.connect(self.publish_shot)

    # -----------------------------------------------------------------------
    # Data initialisation
    # -----------------------------------------------------------------------

    def initialize_data(self):
        self.scan_shot_dirs()

    def scan_shot_dirs(self):
        if hasattr(self, 'thread') and self.thread is not None:
            if self.thread.isRunning():
                nuke.tprint("Scan already in progress.")
                return

        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Scanning...")

        self.thread = QtCore.QThread()
        self.worker = ShotScannerWorker(self.client)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_scan_finished(self, found_shots):
        try:
            self.all_shots = found_shots
            self._shot_detail_cache.clear()

            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Force Refresh")

            self.build_shot_hierarchy()
            self.update_episode_dropdown()

            if not self.is_initialized:
                self.set_initial_shot_context()

            nuke.tprint(f"Scan complete. Found {len(found_shots)} shots.")

        except Exception as e:
            nuke.tprint(f"Error updating UI after scan: {e}")
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("Force Refresh")

    def force_refresh(self):
        nuke.tprint("Forcing refresh of shot list...")
        self.scan_shot_dirs()

    # -----------------------------------------------------------------------
    # Shot detail (cached)
    # -----------------------------------------------------------------------

    def _get_shot_detail(self, shot_id: str):
        """Fetch shot detail from backend (cached per session)."""
        if shot_id not in self._shot_detail_cache:
            try:
                self._shot_detail_cache[shot_id] = self.client.get_shot(shot_id)
            except PipelineError as exc:
                nuke.tprint(f"Could not fetch shot detail for {shot_id}: {exc}")
                return None
        return self._shot_detail_cache.get(shot_id)

    # -----------------------------------------------------------------------
    # Shot hierarchy / dropdowns
    # -----------------------------------------------------------------------

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
            self.episode_dropdown.addItems(sorted(self.shot_data.keys()))
        self.episode_dropdown.blockSignals(False)
        if self.episode_dropdown.count() > 0:
            self.episode_dropdown.setCurrentIndex(0)
            self.on_episode_changed()

    def update_sequence_dropdown(self):
        self.sequence_dropdown.blockSignals(True)
        self.sequence_dropdown.clear()
        selected_ep = self.episode_dropdown.currentText()
        if selected_ep and selected_ep in self.shot_data:
            self.sequence_dropdown.addItems(sorted(self.shot_data[selected_ep].keys()))
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
            self.shot_dropdown.addItems(sorted(self.shot_data[selected_ep][selected_sq]))
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
            self.navigate_to_shot_by_index(self.all_shots.index(shot_name))

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

    def set_initial_shot_context(self):
        script_path = nuke.root().name()
        shot_name = None
        if script_path and script_path != 'Root':
            match = re.search(r'(ep\d+_sq\d+_sh\d+)', script_path)
            if match:
                candidate = match.group(1)
                if candidate in self.all_shots:
                    shot_name = candidate
        if not shot_name and self.all_shots:
            shot_name = self.all_shots[0]
        if shot_name:
            self.navigate_to_shot_by_name(shot_name)
        else:
            self.update_shot_info()
            self.update_navigation_buttons()

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def scan_for_thumbnails(self):
        """Populate version dropdown from thumbnails found in comp/mov/.thumb/."""
        self.current_shot_thumbs = {}
        self.version_dropdown.blockSignals(True)
        self.version_dropdown.clear()

        if not self.shot_context:
            self.version_dropdown.addItem("No versions")
            self.version_dropdown.blockSignals(False)
            return

        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            self.version_dropdown.addItem("No thumbnails")
            self.version_dropdown.blockSignals(False)
            return

        thumb_dir = detail["comp_path"] + "/mov/.thumb"
        if not os.path.isdir(thumb_dir):
            self.version_dropdown.addItem("No thumbnails")
            self.version_dropdown.blockSignals(False)
            return

        try:
            thumb_pattern = re.compile(r'(.+)_v(\d+).*\.(jpg|jpeg|png)', re.IGNORECASE)
            for f in os.listdir(thumb_dir):
                match = thumb_pattern.match(f)
                if match:
                    version_key = f"v{match.group(2).zfill(2)}"
                    self.current_shot_thumbs[version_key] = os.path.join(thumb_dir, f)

            if self.current_shot_thumbs:
                self.version_dropdown.addItems(sorted(self.current_shot_thumbs.keys(), reverse=True))
                self.version_dropdown.setCurrentIndex(0)
            else:
                self.version_dropdown.addItem("No thumbnails")
        except Exception as e:
            nuke.tprint(f"Error scanning thumbnails: {e}")
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
            self.load_thumb_preview(self.current_shot_thumbs[selected_version])
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

    # -----------------------------------------------------------------------
    # Actions — comp scripts
    # -----------------------------------------------------------------------

    def create_script(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return
        try:
            result = self.client.create_comp_script(self.shot_context)
        except PipelineError as exc:
            nuke.message(f"Could not create comp script:\n{exc}")
            return

        script_path = result["path"]
        if not result["created"]:
            if not nuke.ask(f"Script already exists:\n{script_path}\n\nOpen it?"):
                return

        self._update_cerebro_status_to_inprogress(self.shot_context)
        try:
            nuke.scriptOpen(script_path)
            nuke.tprint(f"Opened comp script: {script_path}")
        except RuntimeError as e:
            nuke.tprint(f"Error opening script: {e}")

    def open_script(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return

        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            return

        nk_dir = detail["comp_path"] + "/nk"
        try:
            nk_files = [f for f in os.listdir(nk_dir) if f.endswith('.nk')]
        except FileNotFoundError:
            nuke.message("No Nuke scripts found for this shot.")
            return

        if not nk_files:
            nuke.message("No Nuke scripts found for this shot.")
            return

        recent_script = max(
            nk_files,
            key=lambda f: (int(re.search(r'_v(\d+)', f).group(1)) if re.search(r'_v(\d+)', f) else 0, f)
        )
        script_path = os.path.join(nk_dir, recent_script)

        self._update_cerebro_status_to_inprogress(self.shot_context)
        try:
            nuke.scriptOpen(script_path)
        except RuntimeError as e:
            nuke.tprint(f"Error opening script: {e}")

    def open_comp_dir(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return
        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            return
        comp_dir = detail["comp_path"]
        if os.path.exists(comp_dir):
            self._open_directory(comp_dir)
        else:
            nuke.message("Comp directory does not exist.")

    def import_render(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return
        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            return
        import_tools.import_render_layers(detail)

    # -----------------------------------------------------------------------
    # Actions — precomp scripts
    # -----------------------------------------------------------------------

    def open_precomp(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return

        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            return

        precomp_nk_dir = detail["precomp_path"] + "/nk"
        if not os.path.isdir(precomp_nk_dir) or not os.listdir(precomp_nk_dir):
            nuke.message("No precomp scripts found for this shot. Use 'Create Light Precomp' first.")
            return

        nk_files = [f for f in os.listdir(precomp_nk_dir) if f.endswith('.nk')]
        if not nk_files:
            nuke.message("No precomp scripts found for this shot.")
            return

        versioned = [f for f in nk_files if re.search(r'_v(\d+)', f)]
        if versioned:
            latest_script = max(versioned, key=lambda f: (int(re.search(r'_v(\d+)', f).group(1)), f))
        else:
            latest_script = max(nk_files)

        script_path = os.path.join(precomp_nk_dir, latest_script).replace('\\', '/')
        try:
            nuke.scriptOpen(script_path)
            nuke.tprint(f"Opened precomp: {script_path}")
        except Exception as e:
            nuke.tprint(f"Error opening precomp: {e}")

    def create_precomp(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return
        try:
            result = self.client.create_precomp_script(self.shot_context)
        except PipelineError as exc:
            nuke.message(f"Could not create precomp script:\n{exc}")
            return

        script_path = result["path"]
        try:
            nuke.scriptOpen(script_path)
            nuke.tprint(f"Opened precomp: {script_path}")
        except Exception as e:
            nuke.tprint(f"Error opening precomp: {e}")

    def open_precomp_dir(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return
        detail = self._get_shot_detail(self.shot_context)
        if not detail:
            return
        self._open_directory(detail["precomp_path"])

    # -----------------------------------------------------------------------
    # Actions — Cerebro
    # -----------------------------------------------------------------------

    def _update_cerebro_status_to_inprogress(self, shot_id):
        """Set Cerebro task to in_progress if it is currently to_fix or ready_fw."""
        nuke.tprint(f"Attempting Cerebro status update for: {shot_id}")
        try:
            tasks = self.client.get_cerebro_tasks(shot_id)
            if not tasks:
                nuke.tprint(f"Cerebro: no tasks found for {shot_id}")
                return
            statuses = self.client.get_cerebro_statuses()
            status_by_name = {s["name"]: s["id"] for s in statuses}

            ready_fw_id = status_by_name.get("ready_fw")
            to_fix_id = status_by_name.get("to_fix")
            in_progress_id = status_by_name.get("in_progress")

            if in_progress_id is None:
                nuke.tprint("Cerebro: could not find 'in_progress' status — skipping update")
                return

            for task in tasks:
                current = task.get("status_id")
                if current in (ready_fw_id, to_fix_id):
                    self.client.set_cerebro_status(shot_id, task["id"], in_progress_id)
                    nuke.tprint(f"Cerebro: {shot_id} status updated to 'in progress'")
                else:
                    nuke.tprint(f"Cerebro: status update not required (current: {current})")
        except PipelineError as exc:
            nuke.tprint(f"Cerebro update skipped: {exc}")

    def publish_shot(self):
        if not self.shot_context:
            nuke.message("No shot selected.")
            return

        comment = nuke.getInput("Add comment:")
        if comment is None:
            return

        work_time = self._choose_work_time()
        if work_time is None:
            return

        try:
            tasks = self.client.get_cerebro_tasks(self.shot_context)
            if not tasks:
                nuke.message(f"No Cerebro task found for {self.shot_context}.")
                return
            task_id = tasks[0]["id"]

            # Thumbnail generation is triggered on the backend
            try:
                thumb_result = self.client.get_thumbnail(self.shot_context)
                preview_path = thumb_result.get("path")
            except PipelineError:
                preview_path = None

            self.client.add_cerebro_report(
                self.shot_context,
                task_id=task_id,
                message=comment,
                preview_path=preview_path,
                work_time=work_time,
            )
            nuke.message(f"Successfully published {self.shot_context} to Cerebro")
        except PipelineError as exc:
            nuke.message(f"Cerebro publish failed:\n{exc}")

    def _choose_work_time(self):
        WORK_TIME_OPTIONS = [
            ('0 h', 0), ('15 mins', 15), ('30 mins', 30),
            ('1 h', 60), ('1 h 30 mins', 90), ('2 h', 120),
            ('2 h 30 mins', 150), ('3 h', 180), ('3 h 30 mins', 210),
        ]
        labels = [label for label, _ in WORK_TIME_OPTIONS]
        choice = nuke.choice("Work Time", "Select time spent on task:", labels)
        if choice is None:
            return None
        return WORK_TIME_OPTIONS[choice][1]

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def _open_directory(self, directory):
        import sys
        import subprocess
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

    def reload_context(self):
        self.shot_context = self.get_current_shot()


# ---------------------------------------------------------------------------
# Panel entry points
# ---------------------------------------------------------------------------

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
