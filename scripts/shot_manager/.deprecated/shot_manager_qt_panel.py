from PySide2 import QtWidgets, QtCore, QtGui
import os
import sys
import re
import json
import nuke
import nukescripts
import subprocess
from datetime import datetime

_widget_instance = None
_active_panel = None


class ShotManagerWidget(QtWidgets.QWidget):
    def __init__(self):
        super(ShotManagerWidget, self).__init__()

        global _active_panel
        _active_panel = self

        self.setWindowTitle("Shot Manager")
        self.setMinimumSize(800, 600)
        self.setMaximumSize(800, 600)

        self.setup_ui()
        self.connect_signals()
        self.populate_test_data()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout()
        
        # Upper panel - image preview
        upper_panel = QtWidgets.QWidget()
        upper_layout = QtWidgets.QHBoxLayout()

        # Image display
        self.image_label = QtWidgets.QLabel("Select a shot to preview")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(1, 1)
        self.image_label.setStyleSheet("background-color: #2a2a2a;")
        #self.image_label.adjustSize()
        self.pixmap = QtGui.QPixmap()


        self.scroll_area = QtWidgets.QScrollArea()  # Store reference
        self.scroll_area.setWidget(self.image_label)
        #self.scroll_area.setWidgetResizable(True)
        #self.scroll_area.ensureVisible(0, 0)  # Reset scroll to top-left
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        upper_layout.addWidget(self.scroll_area)
        upper_panel.setLayout(upper_layout)


        # Left panel - controls
        lower_panel = QtWidgets.QWidget()
        # lower_panel.setMaximumWidth(300)
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

        filter_group.setLayout(filter_layout)
        lower_layout.addWidget(filter_group)

        # Preview controls
        preview_group = QtWidgets.QGroupBox("Preview")
        preview_layout = QtWidgets.QVBoxLayout()

        # # Layer dropdown
        # layer_layout = QtWidgets.QHBoxLayout()
        # layer_layout.addWidget(QtWidgets.QLabel("Layer:"))
        # self.layer_dropdown = QtWidgets.QComboBox()
        # layer_layout.addWidget(self.layer_dropdown)
        # preview_layout.addLayout(layer_layout)

        # Frame slider
        frame_layout = QtWidgets.QVBoxLayout()
        frame_layout.addWidget(QtWidgets.QLabel("Frame:"))
        self.frame_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.frame_label = QtWidgets.QLabel("1")
        frame_layout.addWidget(self.frame_slider)
        frame_layout.addWidget(self.frame_label)
        preview_layout.addLayout(frame_layout)

        preview_group.setLayout(preview_layout)
        lower_layout.addWidget(preview_group)

        # Action buttons
        button_group = QtWidgets.QGroupBox("Actions")
        button_layout = QtWidgets.QVBoxLayout()

        self.reload_btn = QtWidgets.QPushButton("Reload Shots")
        self.create_btn = QtWidgets.QPushButton("Create Script")
        self.open_btn = QtWidgets.QPushButton("Open Script")
        self.open_dir_btn = QtWidgets.QPushButton("Open Directory")
        self.import_btn = QtWidgets.QPushButton("Import Renders")

        button_layout.addWidget(self.reload_btn)
        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.open_btn)
        button_layout.addWidget(self.open_dir_btn)
        button_layout.addWidget(self.import_btn)

        self.new_instance_check = QtWidgets.QCheckBox("Open in New Instance")
        button_layout.addWidget(self.new_instance_check)

        button_group.setLayout(button_layout)
        lower_layout.addWidget(button_group)

        # lower_layout.addStretch()
        lower_panel.setLayout(lower_layout)

        # Add panels to main layout
        main_layout.addWidget(upper_panel)
        main_layout.addWidget(lower_panel)

        self.setLayout(main_layout)
        self.adjustSize()

    def scaledPixmap(self):
        # Get the actual available size from the scroll area instead of the label
        available_size = self.scroll_area.viewport().size()

        if available_size.width() <= 0 or available_size.height() <= 0:
            # Fallback to label size if scroll area size isn't ready
            available_size = QtCore.QSize(self.image_label.width(), self.image_label.height())
        
        return self.pixmap.scaledToHeight(available_size.height(),QtCore.Qt.SmoothTransformation)

    def resizeEvent(self, event):
        super(ShotManagerWidget, self).resizeEvent(event)
        if self.image_label.isVisible() and not self.pixmap.isNull():
            self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self.pixmap.isNull():
            scaled = self.scaledPixmap()
            if not scaled.isNull():
                self.image_label.setPixmap(scaled)
                #self.image_label.setMinimumSize(scaled.size())  # Optional: allow resizing scroll area
                self.image_label.resize(scaled.size())


    def connect_signals(self):
        # Connect dropdowns
        self.episode_dropdown.currentTextChanged.connect(self.on_episode_changed)
        self.sequence_dropdown.currentTextChanged.connect(self.on_sequence_changed)
        self.shot_dropdown.currentTextChanged.connect(self.on_shot_changed)
        # self.layer_dropdown.currentTextChanged.connect(self.on_layer_changed)
        self.frame_slider.valueChanged.connect(self.on_frame_changed)

        # Connect buttons
        self.reload_btn.clicked.connect(self.reload_shots)
        self.create_btn.clicked.connect(self.placeholder_method)
        self.open_btn.clicked.connect(self.placeholder_method)
        self.open_dir_btn.clicked.connect(self.placeholder_method)
        self.import_btn.clicked.connect(self.placeholder_method)

    def populate_test_data(self):
        """Add some test data for prototype"""
        self.episode_dropdown.addItems(["01", "02", "03"])
        self.sequence_dropdown.addItems(["01", "02", "03"])
        self.shot_dropdown.addItems(["01", "02", "03", "04", "05"])
        # self.layer_dropdown.addItems(["beauty", "chars", "env", "fx"])

    def on_episode_changed(self):
        print(f"Episode changed to: {self.episode_dropdown.currentText()}")
        self.update_preview()

    def on_sequence_changed(self):
        print(f"Sequence changed to: {self.sequence_dropdown.currentText()}")
        self.update_preview()

    def on_shot_changed(self):
        print(f"Shot changed to: {self.shot_dropdown.currentText()}")
        self.update_preview()

    # def on_layer_changed(self):
    #     print(f"Layer changed to: {self.layer_dropdown.currentText()}")
    #     self.update_preview()

    def on_frame_changed(self, value):
        frame_num = 1 + value
        self.frame_label.setText(str(frame_num))
        self.update_preview()

    def update_preview(self):
        """Update the image preview based on current selections"""

        # Get current selection
        ep = self.episode_dropdown.currentText()
        sq = self.sequence_dropdown.currentText()
        sh = self.shot_dropdown.currentText()
        # layer = self.layer_dropdown.currentText()

        if not all([ep, sq, sh]):
            self.image_label.setText("Select episode, sequence, shot")
            return

        # Construct path (adjust this to match your folder structure)
        frame_num = self.frame_slider.value()
        thumb_path = "//192.168.99.202/prj/cinderella/render/ep99/sq99/sh999/comp/.thumb/ep99_sq99_sh99.thumb.png"  # f"{self.comp_path}/ep{ep}/sq{sq}/sh{sh}/comp/exr/ep{ep}_sq{sq}_sh{sh}.{frame_num:04d}.exr"

        # For prototype, show the path we're looking for
        if os.path.exists(thumb_path):
            self.load_thumb_preview(thumb_path)
        else:
            self.image_label.setText(f"Preview not found:\n{thumb_path}")

    def load_thumb_preview(self, thumb_path):
        """Load PNG file and display as preview"""
        try:
            # Read PNG
            self.pixmap = QtGui.QPixmap(thumb_path)
            if not self.pixmap:
                self.image_label.setText(f"Could not open:\n{thumb_path}")
                return
            
            QtCore.QTimer.singleShot(0, self._update_scaled_pixmap)
            
        except Exception as e:
            self.image_label.setText(f"Error loading image:\n{str(e)}")



    def reload_shots(self):
        """Reload shot data"""
        print("Reloading shots...")
        # Set frame range for prototype
        self.frame_slider.setMinimum(1)
        self.frame_slider.setMaximum(100)  # Adjust to shot range
        self.frame_slider.setValue(0)
        self.update_preview()

    def placeholder_method(self):
        """Placeholder for other functionality"""
        sender = self.sender()
        print(f"Button '{sender.text()}' clicked - implement functionality here")


def show_shot_manager():
    global _widget_instance

    if _widget_instance is None:
        _widget_instance = ShotManagerWidget()

    _widget_instance.show()
    _widget_instance.raise_()
    _widget_instance.activateWindow()


#if __name__ == "__main__":
#    show_shot_manager()

HRName='Shot Manager' #the Human-readable name you want for your panel
regName='NukePanel.ShotManager'
nukescripts.panels.registerWidgetAsPanel("ShotManagerWidget", HRName, regName, True).addToPane(nuke.getPaneFor('Properties.1'))

