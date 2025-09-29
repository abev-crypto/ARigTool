# LMrigger 2.07.23 - FK Control Rig Generator by Luismi Herrera (twitter: @luismiherrera)
from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets
from PySide2.QtWidgets import QFrame
from PySide2.QtWidgets import QRadioButton
from shiboken2 import wrapInstance
from functools import partial

import maya.OpenMayaUI as omui
import maya.cmds as cmds

def maya_main_window():
    """
    Return the maya Main window widget as a Python object
    """
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)

class LMriggerDialog(QtWidgets.QDialog):

    dlg_instance = None

    @classmethod
    def show_dialog(cls):
        if not cls.dlg_instance:
            cls.dlg_instance = LMriggerDialog()

        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()
        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()

    def __init__(self, parent=maya_main_window()):
        super(LMriggerDialog, self).__init__(parent)
        
        self.setWindowTitle("LMrigger 2.7.23")
        # self.setFixedWidth(250)
               
        self.create_widgets()
        self.create_layouts()
        self.create_connections()

        self.joint_orientation = "xyz"
        self.world_up_orientation = "yup"

        self.curveNormalX = 1
        self.curveNormalY = 0
        self.curveNormalZ = 0
        self.controlShape = "Circle"
        self.curveRadius = 1
        self.createScaleConstraint = 2
        self.sz = self.curveRadius # cube size
        self.rightControlsColor = (4,29,255)
        self.leftControlsColor = (139,12,12)
        self.restControlsColor = (190,190,17)
        self.rightControlsSuffix = '_R'
        self.leftControlsSuffix = '_L'

    def create_widgets(self):
        self.show_axis_btn = QtWidgets.QPushButton("Show Axis")
        self.hide_axis_btn = QtWidgets.QPushButton("Hide Axis")

        self.groupBox_A = QtWidgets.QGroupBox()
        self.primary_axis_label = QtWidgets.QLabel("Primary Axis:     ")
        self.primary_axis_x_rb = QtWidgets.QRadioButton("X")
        self.primary_axis_x_rb.setChecked(True)
        self.primary_axis_y_rb = QtWidgets.QRadioButton("Y")
        self.primary_axis_z_rb = QtWidgets.QRadioButton("Z")
        self.primary_axis_cbox = QtWidgets.QComboBox()
        self.primary_axis_cbox.addItem("+")
        self.primary_axis_cbox.addItem("-")

        self.groupBox_B = QtWidgets.QGroupBox()
        self.secondary_axis_label = QtWidgets.QLabel("Secondary Axis:")
        self.secondary_axis_x_rb = QtWidgets.QRadioButton("X")
        self.secondary_axis_y_rb = QtWidgets.QRadioButton("Y")
        self.secondary_axis_y_rb.setChecked(True)
        self.secondary_axis_z_rb = QtWidgets.QRadioButton("Z")
        self.secondary_axis_cbox = QtWidgets.QComboBox()
        self.secondary_axis_cbox.addItem("+")
        self.secondary_axis_cbox.addItem("-")
        
        self.groupBox_C = QtWidgets.QGroupBox()
        self.world_up_axis_label = QtWidgets.QLabel("World Up Axis:  ")
        self.world_up_axis_x_rb = QtWidgets.QRadioButton("X")
        self.world_up_axis_y_rb = QtWidgets.QRadioButton("Y")
        self.world_up_axis_y_rb.setChecked(True)
        self.world_up_axis_z_rb = QtWidgets.QRadioButton("Z")
        self.world_up_axis_cbox = QtWidgets.QComboBox()
        self.world_up_axis_cbox.addItem("+")
        self.world_up_axis_cbox.addItem("-")

        self.orient_to_world_btn = QtWidgets.QPushButton("Orient To World")
        self.orient_to_world_btn.setMaximumWidth(130)
        self.orient_joint_btn = QtWidgets.QPushButton("ORIENT JOINTS")
        self.orient_joint_btn.setMinimumHeight(50)

        self.tweak_axis_label = QtWidgets.QLabel("Tweak:")
        self.tweak_axis_x_sb = QtWidgets.QDoubleSpinBox()
        self.tweak_axis_x_sb.setMinimum(-360.0)
        self.tweak_axis_x_sb.setMaximum(360.0)
        self.tweak_axis_x_sb.setDecimals(1)
        self.tweak_axis_y_sb = QtWidgets.QDoubleSpinBox()
        self.tweak_axis_y_sb.setMinimum(-360.0)
        self.tweak_axis_y_sb.setMaximum(360.0)
        self.tweak_axis_y_sb.setDecimals(1)
        self.tweak_axis_z_sb = QtWidgets.QDoubleSpinBox()
        self.tweak_axis_z_sb.setMinimum(-360.0)
        self.tweak_axis_z_sb.setMaximum(360.0)
        self.tweak_axis_z_sb.setDecimals(1)
        self.tweak_axis_zero_btn = QtWidgets.QPushButton("Zero")
        
        self.tweak_axis_plus_btn = QtWidgets.QPushButton("Manual + Rotation")
        self.tweak_axis_minus_btn = QtWidgets.QPushButton("Manual - Rotation")
        
        self.groupBox_1 = QtWidgets.QGroupBox()
        self.control_shape_label = QtWidgets.QLabel("Control Shape:")
        self.control_shape_rb_circle = QtWidgets.QRadioButton("Circle")
        self.control_shape_rb_circle.setChecked(True)
        self.control_shape_rb_cube = QtWidgets.QRadioButton("Cube")
        self.control_shape_cbox = QtWidgets.QComboBox()
        self.control_shape_cbox.addItem("Circle")
        self.control_shape_cbox.addItem("Cube")
        self.control_shape_cbox.addItem("Square")
        self.control_shape_cbox.addItem("Triangle")
        self.control_shape_cbox.addItem("Cross")
        self.control_shape_cbox.addItem("Arrow")
        self.control_shape_cbox.addItem("Four Arrows")

        self.groupBox_2 = QtWidgets.QGroupBox()
        self.control_normal_label = QtWidgets.QLabel("Shape Normal: ")
        self.control_normal_rb_x = QtWidgets.QRadioButton("X")
        self.control_normal_rb_x.setChecked(True) 
        self.control_normal_rb_y = QtWidgets.QRadioButton("Y")
        self.control_normal_rb_z = QtWidgets.QRadioButton("Z")

        self.groupBox_3 = QtWidgets.QGroupBox()
        self.scale_constraint_label = QtWidgets.QLabel("Scale Constraint:")
        self.scale_constraint_rb_yes = QtWidgets.QRadioButton("Yes")
        self.scale_constraint_rb_yes.setChecked(True)
        self.scale_constraint_rb_no = QtWidgets.QRadioButton("No")

        self.groupBox_4 = QtWidgets.QGroupBox()
        self.control_shape_size_label = QtWidgets.QLabel("Shape Size:")
        self.control_shape_size_sb = QtWidgets.QDoubleSpinBox()
        self.control_shape_size_sb.setMinimum(0.001)
        self.control_shape_size_sb.setValue(1.0)

        self.suffix_left_label = QtWidgets.QLabel("Left Controls Suffix:")
        self.suffix_left_text = QtWidgets.QLineEdit("_L")
        self.suffix_right_label = QtWidgets.QLabel("Right Controls Suffix:")
        self.suffix_right_text = QtWidgets.QLineEdit("_R")

        self.color_picker = QtWidgets.QColorDialog()
        self.left_color_btn = QtWidgets.QPushButton("Left")
        self.left_color_btn.setStyleSheet('background-color: rgb(139,12,12)')
        self.middle_color_btn = QtWidgets.QPushButton("Middle")
        self.middle_color_btn.setStyleSheet('background-color: rgb(190,190,17)')
        self.right_color_btn = QtWidgets.QPushButton("Right")
        self.right_color_btn.setStyleSheet('background-color: rgb(4,29,255)')
        self.change_color_btn = QtWidgets.QPushButton("Change Selected Controls Color")

        self.about_btn = QtWidgets.QPushButton("?")
        self.about_btn.setMaximumWidth(50)
        self.about_btn.setMinimumHeight(50)
        self.create_btn = QtWidgets.QPushButton("CREATE CONTROLS")
        self.create_btn.setMinimumHeight(50)
        
        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.HLine)
        self.separator.setLineWidth(3)
        self.separator2 = QFrame()
        self.separator2.setFrameShape(QFrame.HLine)
        self.separator2.setLineWidth(3)
        self.separator3 = QFrame()
        self.separator3.setFrameShape(QFrame.VLine)
        self.separator3.setLineWidth(3)
    
    def create_layouts(self):
        axis_layout = QtWidgets.QHBoxLayout()
        axis_layout.addWidget(self.show_axis_btn)
        axis_layout.addWidget(self.hide_axis_btn)

        primary_axis_layout = QtWidgets.QHBoxLayout()
        primary_axis_layout.addWidget(self.primary_axis_label)
        primary_axis_layout.addWidget(self.primary_axis_x_rb)
        primary_axis_layout.addWidget(self.primary_axis_y_rb)
        primary_axis_layout.addWidget(self.primary_axis_z_rb)
        primary_axis_layout.addWidget(self.primary_axis_cbox)
        primary_axis_layout.setContentsMargins(5,0,5,0)
        self.groupBox_A.setLayout(primary_axis_layout)

        secondary_axis_layout = QtWidgets.QHBoxLayout()
        secondary_axis_layout.addWidget(self.secondary_axis_label)
        secondary_axis_layout.addWidget(self.secondary_axis_x_rb)
        secondary_axis_layout.addWidget(self.secondary_axis_y_rb)
        secondary_axis_layout.addWidget(self.secondary_axis_z_rb)
        secondary_axis_layout.addWidget(self.secondary_axis_cbox)
        secondary_axis_layout.setContentsMargins(5,0,5,0)
        self.groupBox_B.setLayout(secondary_axis_layout)
        
        world_up_axis_layout = QtWidgets.QHBoxLayout()
        world_up_axis_layout.addWidget(self.world_up_axis_label)
        world_up_axis_layout.addWidget(self.world_up_axis_x_rb)
        world_up_axis_layout.addWidget(self.world_up_axis_y_rb)
        world_up_axis_layout.addWidget(self.world_up_axis_z_rb)
        world_up_axis_layout.addWidget(self.world_up_axis_cbox)
        world_up_axis_layout.setContentsMargins(5,0,5,0)
        self.groupBox_C.setLayout(world_up_axis_layout)
        
        orient_joints_layout = QtWidgets.QHBoxLayout()
        orient_joints_layout.addWidget(self.orient_to_world_btn)
        orient_joints_layout.addWidget(self.orient_joint_btn)

        tweak_axis_layout = QtWidgets.QHBoxLayout()
        tweak_axis_layout.addWidget(self.tweak_axis_label)
        tweak_axis_layout.addWidget(self.tweak_axis_x_sb)
        tweak_axis_layout.addWidget(self.tweak_axis_y_sb)
        tweak_axis_layout.addWidget(self.tweak_axis_z_sb)
        tweak_axis_layout.addWidget(self.tweak_axis_zero_btn)
        
        manual_rot_layout = QtWidgets.QHBoxLayout()
        manual_rot_layout.addWidget(self.tweak_axis_minus_btn)
        manual_rot_layout.addWidget(self.tweak_axis_plus_btn)

        shape_layout = QtWidgets.QHBoxLayout()
        shape_layout.addWidget(self.control_shape_label)
        shape_layout.addWidget(self.control_shape_cbox)
        shape_layout.addWidget(self.control_shape_size_label)
        shape_layout.addWidget(self.control_shape_size_sb)
        shape_layout.setContentsMargins(5,0,5,0)
        self.groupBox_1.setLayout(shape_layout)

        normal_layout = QtWidgets.QHBoxLayout()
        normal_layout.addWidget(self.control_normal_label)
        normal_layout.addWidget(self.control_normal_rb_x)
        normal_layout.addWidget(self.control_normal_rb_y)
        normal_layout.addWidget(self.control_normal_rb_z)
        normal_layout.setContentsMargins(5,0,5,0)
        self.groupBox_2.setLayout(normal_layout)

        scale_constraint_layout = QtWidgets.QHBoxLayout()
        scale_constraint_layout.addWidget(self.scale_constraint_label)
        scale_constraint_layout.addWidget(self.scale_constraint_rb_yes)
        scale_constraint_layout.addWidget(self.scale_constraint_rb_no)
        scale_constraint_layout.setContentsMargins(5,0,5,0)
        self.groupBox_3.setLayout(scale_constraint_layout)

        options_layout = QtWidgets.QGridLayout()
        options_layout.addWidget(self.suffix_left_label,1,0)
        options_layout.addWidget(self.suffix_left_text,0,1)
        options_layout.addWidget(self.suffix_right_label,1,0)
        options_layout.addWidget(self.suffix_right_text,1,1)

        colors_layout = QtWidgets.QHBoxLayout()
        colors_layout.addWidget(self.left_color_btn)
        colors_layout.addWidget(self.middle_color_btn)
        colors_layout.addWidget(self.right_color_btn)

        change_color_layout = QtWidgets.QHBoxLayout()
        change_color_layout.addWidget(self.change_color_btn)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addWidget(self.about_btn)
        buttons_layout.addWidget(self.create_btn)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(axis_layout)
        main_layout.addWidget(self.groupBox_A)
        main_layout.addWidget(self.groupBox_B)
        main_layout.addWidget(self.groupBox_C)
        main_layout.addLayout(orient_joints_layout)
        main_layout.addWidget(self.separator)
        main_layout.addLayout(tweak_axis_layout)
        main_layout.addLayout(manual_rot_layout)
        main_layout.addWidget(self.separator2)
        main_layout.addWidget(self.groupBox_1)
        main_layout.addWidget(self.groupBox_2)
        # main_layout.addWidget(self.groupBox_3)
        main_layout.addLayout(options_layout)
        main_layout.addLayout(colors_layout)
        main_layout.addLayout(change_color_layout)
        main_layout.addLayout(buttons_layout)

    def create_connections(self):
        self.show_axis_btn.clicked.connect(self.show_axis)
        self.hide_axis_btn.clicked.connect(self.hide_axis)
        self.primary_axis_x_rb.toggled.connect(self.update_joint_orientation)
        self.primary_axis_y_rb.toggled.connect(self.update_joint_orientation)
        self.primary_axis_z_rb.toggled.connect(self.update_joint_orientation)
        self.secondary_axis_x_rb.toggled.connect(self.update_joint_orientation)
        self.secondary_axis_y_rb.toggled.connect(self.update_joint_orientation)
        self.secondary_axis_z_rb.toggled.connect(self.update_joint_orientation)
        self.world_up_axis_x_rb.toggled.connect(self.update_world_up_orientation)
        self.world_up_axis_y_rb.toggled.connect(self.update_world_up_orientation)
        self.world_up_axis_z_rb.toggled.connect(self.update_world_up_orientation)
        self.world_up_axis_cbox.currentIndexChanged.connect(self.update_world_up_orientation)
        self.orient_to_world_btn.clicked.connect(self.orient_to_world)
        self.orient_joint_btn.clicked.connect(self.orient_joints)
        self.tweak_axis_zero_btn.clicked.connect(self.zero_manual_rotation_spinboxes)
        self.tweak_axis_minus_btn.clicked.connect(lambda: self.manual_rotation(-1))
        self.tweak_axis_plus_btn.clicked.connect(lambda: self.manual_rotation(1))
        self.create_btn.clicked.connect(self.createControls)
        self.control_shape_size_sb.valueChanged.connect(self.updateControlRadius)
        self.about_btn.clicked.connect(self.Gumroad)
        self.left_color_btn.clicked.connect(self.pick_color_left)
        self.middle_color_btn.clicked.connect(self.pick_color_middle)
        self.right_color_btn.clicked.connect(self.pick_color_right)
        self.change_color_btn.clicked.connect(self.change_control_color)
    
    def orient_to_world(self):
        joints = cmds.ls(sl=True, type="joint")
        for joint in joints:
            cmds.joint(joint, edit=True, orientJoint = "none")

    def manual_rotation(self, sign):
        joints = cmds.ls(sl=True, type="joint")
        cmds.xform(joints, r=True, os=True, 
                   ra=(self.tweak_axis_x_sb.value()*sign,
                       self.tweak_axis_y_sb.value()*sign,
                       self.tweak_axis_z_sb.value()*sign))
        cmds.joint(joints, edit=True, zso=True)
        cmds.makeIdentity(joints, apply=True)
    
    def zero_manual_rotation_spinboxes(self):
        self.tweak_axis_x_sb.setValue(0)
        self.tweak_axis_y_sb.setValue(0)
        self.tweak_axis_z_sb.setValue(0)

    def update_joint_orientation(self):
        if (self.primary_axis_x_rb.isChecked()):
            if(self.secondary_axis_x_rb.isChecked()):
                self.secondary_axis_y_rb.setChecked(True)
                self.joint_orientation = "xyz"
            elif(self.secondary_axis_y_rb.isChecked()):
                self.joint_orientation = "xyz"
            elif(self.secondary_axis_z_rb.isChecked()):
                self.joint_orientation = "xzy"
        elif (self.primary_axis_y_rb.isChecked()):
            if(self.secondary_axis_x_rb.isChecked()):
                self.joint_orientation = "yxz"
            elif(self.secondary_axis_y_rb.isChecked()):
                self.secondary_axis_x_rb.setChecked(True)
                self.joint_orientation = "yxz"
            elif(self.secondary_axis_z_rb.isChecked()):
                self.joint_orientation = "yzx"
        elif (self.primary_axis_z_rb.isChecked()):
            if(self.secondary_axis_x_rb.isChecked()):
                self.joint_orientation = "zxy"
            elif(self.secondary_axis_y_rb.isChecked()):
                self.joint_orientation = "zyx"
            elif(self.secondary_axis_z_rb.isChecked()):
                self.secondary_axis_x_rb.setChecked(True)
                self.joint_orientation = "zxy"

    def update_world_up_orientation(self):
        if(self.world_up_axis_cbox.currentText() == "+"):
            if(self.world_up_axis_x_rb.isChecked()):
                self.world_up_orientation = "xup"
            elif(self.world_up_axis_y_rb.isChecked()):
                self.world_up_orientation = "yup"
            elif(self.world_up_axis_z_rb.isChecked()):
                self.world_up_orientation = "zup"
        else:
            if(self.world_up_axis_x_rb.isChecked()):
                self.world_up_orientation = "xdown"
            elif(self.world_up_axis_y_rb.isChecked()):
                self.world_up_orientation = "ydown"
            elif(self.world_up_axis_z_rb.isChecked()):
                self.world_up_orientation = "zdown"

    def orient_joints(self):
        pSign = 1
        sSign = 1
        if(self.primary_axis_cbox.currentText() == "-"): pSign = -1
        if(self.secondary_axis_cbox.currentText() == "-"): sSign = -1

        joints = cmds.ls(sl=True, type="joint")
        for joint in joints:
            children = cmds.listRelatives(joint, children=True)
            if(children == None):
                parent_joint = cmds.listRelatives(joint, parent=True)[0]
                tempConst = cmds.orientConstraint(parent_joint, joint, weight=-1)
                cmds.delete(tempConst)
                cmds.joint(joint, edit=True, zso=True)
                cmds.makeIdentity(joint, apply=True, t=True, r=True, s=True)
            else:
                cmds.joint(edit=True, 
                        orientJoint= self.joint_orientation,
                        secondaryAxisOrient= self.world_up_orientation,
                        zso=True)
        
        if(pSign == -1 or sSign == -1):
            for joint in joints:
                children = cmds.listRelatives(joint, children=True)

                if(children == None):
                    parent = cmds.listRelatives(joint, parent=True)[0]
                    self.aim_constriant(parent, joint, -pSign , sSign)
                else:
                    child = children[0]
                    cmds.parent(child, world=True)
                    self.aim_constriant(child, joint, pSign, sSign)
                    cmds.parent(child, joint)
                cmds.select(clear=True)
                cmds.select(joints)

    def aim_constriant(self, child, joint, primary_sign, secondary_sign):
        aimVector, upVector, worldUpVector = self.get_aim_constraint_vectors(primary_sign,
                                                                            secondary_sign)
        tempConst = cmds.aimConstraint(child, joint,
                                        offset=(0,0,0),
                                        aimVector=aimVector,
                                        upVector=upVector,
                                        worldUpVector=worldUpVector,
                                        worldUpType="vector")
        cmds.delete(tempConst)
        cmds.joint(joint,edit=True,zso=True)
        cmds.makeIdentity(joint, apply=True, t=True, r=True, s=True)
        
    def get_aim_constraint_vectors(self, primary_sign, secondary_sign):
        primary_axis = self.get_checked_radio_button(self.groupBox_A)
        secondary_axis = self.get_checked_radio_button(self.groupBox_B)
        world_up_axis = self.get_checked_radio_button(self.groupBox_C)

        if(primary_axis == "X"): aimVector = (primary_sign,0,0)
        if(primary_axis == "Y"): aimVector = (0,primary_sign,0)
        if(primary_axis == "Z"): aimVector = (0,0,primary_sign)
        
        if(secondary_axis == "X"): upVector = (secondary_sign,0,0)
        if(secondary_axis == "Y"): upVector = (0,secondary_sign,0)
        if(secondary_axis == "Z"): upVector = (0,0,secondary_sign)

        if(world_up_axis == "X"): worldUpVector = (1,0,0)
        if(world_up_axis == "Y"): worldUpVector = (0,1,0)
        if(world_up_axis == "Z"): worldUpVector = (0,0,1)

        return aimVector, upVector, worldUpVector
    
    def get_checked_radio_button(self, group_box):
        """Gets the checked radio button in a group box."""
        checked_button = None
        for button in group_box.findChildren(QRadioButton):
            if button.isChecked():
                checked_button = button.text()
                break
        return checked_button  

    def show_axis(self):
        joints = cmds.ls(sl=True)
        for joint in joints:
            cmds.toggle(state = True, localAxis = True)

    def hide_axis(self):
        joints = cmds.ls(sl=True)
        for joint in joints:
            cmds.toggle(state = False, localAxis = True)

    def change_control_color(self):
        #check if control is selected
        controls = cmds.ls(sl=True)
        if(len(controls)==0):
            cmds.warning("No controls selected!")
        else:
            new_color = self.color_picker.getColor()
            r, g, b, a = new_color.getRgb()
            for control in controls:
                print(control)
                cmds.setAttr(control + "Shape.overrideEnabled",1)
                cmds.setAttr(control + "Shape.overrideRGBColors",1)
                cmds.setAttr(control + "Shape.overrideColorRGB",
                            r/255,
                            g/255,
                            b/255)

    def pick_color_left(self):
        color = self.color_picker.getColor()
        r, g, b, a = color.getRgb()
        self.left_color_btn.setStyleSheet(f'background-color: rgb({r},{g},{b})')
        self.leftControlsColor = (r,g,b)

    def pick_color_middle(self):
        color = self.color_picker.getColor()
        r, g, b, a = color.getRgb()
        self.middle_color_btn.setStyleSheet(f'background-color: rgb({r},{g},{b})')
        self.restControlsColor = (r,g,b)

    def pick_color_right(self):
        color = self.color_picker.getColor()
        r, g, b, a = color.getRgb()
        self.right_color_btn.setStyleSheet(f'background-color: rgb({r},{g},{b})')
        self.rightControlsColor = (r,g,b)

    def updateControlNormal(self):
        if self.control_normal_rb_x.isChecked():
            self.curveNormalX = 1
            self.curveNormalY = 0
            self.curveNormalZ = 0

        elif self.control_normal_rb_y.isChecked(): 
            self.curveNormalX = 0
            self.curveNormalY = 1
            self.curveNormalZ = 0

        elif self.control_normal_rb_z.isChecked():
            self.curveNormalX = 0
            self.curveNormalY = 0
            self.curveNormalZ = 1

    def updateControlShape(self):
        self.controlShape = self.control_shape_cbox.currentText()
        print(self.controlShape)

    def updateControlRadius(self, value):
        self.curveRadius = value
        self.sz = self.curveRadius

    def updateLeftControlsSuffix(self):
        self.leftControlsSuffix = self.suffix_left_text.text()

    def updateRightControlsSuffix(self):
        self.rightControlsSuffix = self.suffix_right_text.text()

    def updateScaleConstraint(self):
        if self.scale_constraint_rb_yes.isChecked():
            self.createScaleConstraint = 1
        else:
            self.createScaleConstraint = 0

    #Hyperlink to Gumroad webpage
    def Gumroad(self):
        cmds.showHelp( 'https://gumroad.com/luismiherrera', absolute=True )


    def create_shape(self, joint_name):
        if self.controlShape == "Circle":
            controlCurve = cmds.circle( normal=(self.curveNormalX, 
                                                self.curveNormalY, 
                                                self.curveNormalZ), 
                                        radius = self.curveRadius, 
                                                    center=(0, 0, 0), 
                                                    name = (joint_name + '_Ctrl'))

        elif self.controlShape == "Cube":
            curve = cmds.curve (d= 1, name = (joint_name + '_Ctrl'),
            p=[(-self.sz, self.sz, self.sz), (self.sz, self.sz, self.sz),
            (self.sz, self.sz, -self.sz), (-self.sz, self.sz, -self.sz),
            (-self.sz, self.sz, self.sz), (-self.sz, -self.sz, self.sz),
            (-self.sz, -self.sz, -self.sz), (self.sz, -self.sz, -self.sz),
            (self.sz, -self.sz, self.sz),(-self.sz, -self.sz, self.sz),
            (self.sz, -self.sz, self.sz), (self.sz, self.sz, self.sz),
            (self.sz, self.sz, -self.sz), (self.sz, -self.sz, -self.sz),
            (-self.sz, -self.sz, -self.sz), (-self.sz, self.sz, -self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        elif self.controlShape == "Square":
            curve = cmds.curve (d=1, name = (joint_name + '_Ctrl'),
            p=[ (-self.sz, 0.0, -self.sz),
                (-self.sz, 0.0, self.sz),
                (self.sz, 0.0, self.sz),
                (self.sz, 0.0, -self.sz),
                (-self.sz, 0.0, -self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        elif self.controlShape == "Triangle":
            curve = cmds.curve (d=1, name = (joint_name + '_Ctrl'),
            p=[ (self.sz, 0.0, -self.sz),
                (0.0, 0.0, self.sz),
                (-self.sz, 0.0, -self.sz),
                (self.sz, 0.0, -self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        elif self.controlShape == "Cross":
            curve = cmds.curve (d=1, name = (joint_name + '_Ctrl'),
            p=[ (-self.sz, 0.0, -2*self.sz),
                (self.sz, 0.0, -2*self.sz),
                (self.sz, 0.0, -self.sz),
                (2*self.sz, 0.0, -self.sz),
                (2*self.sz, 0.0, self.sz),
                (self.sz, 0.0, self.sz),
                (self.sz, 0.0, 2*self.sz),
                (-self.sz, 0.0, 2*self.sz),
                (-self.sz, 0.0, self.sz),
                (-2*self.sz, 0.0, self.sz),
                (-2*self.sz, 0.0, -self.sz),
                (-self.sz, 0.0, -self.sz),
                (-self.sz, 0.0, -2*self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        elif self.controlShape == "Arrow":
            curve = cmds.curve (d=1, name = (joint_name + '_Ctrl'),
            p=[ (0.0, 0.0, 2*self.sz),
                (-1.6*self.sz, 0.0, 0.4*self.sz),
                (-0.8*self.sz, 0.0, 0.4*self.sz),
                (-0.8*self.sz, 0.0, -2*self.sz),
                (0.8*self.sz, 0.0, -2*self.sz),
                (0.8*self.sz, 0.0, 0.4*self.sz),
                (1.6*self.sz, 0.0, 0.4*self.sz),
                (0.0, 0.0, 2*self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        elif self.controlShape == "Four Arrows":
            curve = cmds.curve (d=1, name = (joint_name + '_Ctrl'),
            p=[ (0.0, 0.0, -2*self.sz),
                (0.8*self.sz, 0.0, -1.2*self.sz),
                (0.4*self.sz, 0.0, -1.2*self.sz),
                (0.4*self.sz, 0.0, -0.4*self.sz),
                (1.2*self.sz, 0.0, -0.4*self.sz),
                (1.2*self.sz, 0.0, -0.8*self.sz),
                (2*self.sz, 0.0, 0.0),
                (1.2*self.sz, 0.0, 0.8*self.sz),
                (1.2*self.sz, 0.0, 0.4*self.sz),
                (0.4*self.sz, 0.0, 0.4*self.sz),
                (0.4*self.sz, 0.0, 1.2*self.sz),
                (0.8*self.sz, 0.0, 1.2*self.sz),
                (0.0, 0.0, 2*self.sz),
                (-0.8*self.sz, 0.0, 1.2*self.sz),
                (-0.4*self.sz, 0.0, 1.2*self.sz),
                (-0.4*self.sz, 0.0, 0.4*self.sz),
                (-1.2*self.sz, 0.0, 0.4*self.sz),
                (-1.2*self.sz, 0.0, 0.8*self.sz),
                (-2*self.sz, 0.0, 0.0),
                (-1.2*self.sz, 0.0, -0.8*self.sz),
                (-1.2*self.sz, 0.0, -0.4*self.sz),
                (-0.4*self.sz, 0.0, -0.4*self.sz),
                (-0.4*self.sz, 0.0, -1.2*self.sz),
                (-0.8*self.sz, 0.0, -1.2*self.sz),
                (0.0, 0.0, -2*self.sz)])
            controlCurve = self.create_controlCurve(curve) 

        return controlCurve

    def create_controlCurve(self, curve):
        curve_cvs = cmds.ls(curve+'.cv[:]', fl=True)
        cmds.select(curve_cvs)
        cmds.rotate(self.curveNormalZ*90,
                    self.curveNormalY*90,
                    self.curveNormalX*90, 
                    r=True, os=True)
        cmds.select(curve)
        controlCurve = []
        controlCurve.append(curve)
        curve_shapes = cmds.listRelatives(curve, shapes=True)
        cmds.rename(curve_shapes[0], curve+"Shape")
        return controlCurve

    #Creates curve controls in selected joints
    def createControls(self):
        self.updateControlNormal()
        self.updateControlShape()
        self.updateScaleConstraint()
        self.updateLeftControlsSuffix()
        self.updateRightControlsSuffix()

        selJoints = cmds.ls(sl=True)

        if len(selJoints) == 0:
            cmds.warning( "Nothing Selected" )
        else:
            if not cmds.objExists('Controls'):
                cmds.createDisplayLayer(name='Controls', empty=True)
            if not cmds.objExists('Joints'):
                cmds.createDisplayLayer(name='Joints', empty=True)

            constraints_group_name = "Constraints_Grp"
            if not cmds.objExists(constraints_group_name): 
                cmds.group(empty = True, 
                           name = constraints_group_name, 
                           world = True)

            for i in range (len(selJoints)):
                controlCurve = self.create_shape(selJoints[i])

                controlGroup = cmds.group( controlCurve , name = (selJoints[i]+'_Grp'))
                tempConstraint = cmds.parentConstraint(selJoints[i], 
                                                       controlGroup, w=1, 
                                                       maintainOffset = False)
                cmds.delete (tempConstraint[0])
                pConst = cmds.parentConstraint(controlCurve, selJoints[i], 
                                               w=1, maintainOffset = False)
                cmds.parent(pConst, constraints_group_name)
                if(self.createScaleConstraint == 1):
                    sConst = cmds.scaleConstraint(controlCurve, selJoints[i])
                    cmds.parent(sConst, constraints_group_name)
                #cmds.select (controlCurve)

                cmds.setAttr(controlCurve[0] + "Shape.overrideEnabled",1)
                cmds.setAttr(controlCurve[0] + "Shape.overrideRGBColors",1)
                if self.rightControlsSuffix in controlCurve[0]:
                    cmds.setAttr(controlCurve[0] + "Shape.overrideColorRGB",
                                 self.rightControlsColor[0]/255,
                                 self.rightControlsColor[1]/255,
                                 self.rightControlsColor[2]/255)
                elif self.leftControlsSuffix in controlCurve[0]:
                    cmds.setAttr(controlCurve[0] + "Shape.overrideColorRGB",
                                 self.leftControlsColor[0]/255,
                                 self.leftControlsColor[1]/255,
                                 self.leftControlsColor[2]/255)
                else:
                    cmds.setAttr(controlCurve[0] + "Shape.overrideColorRGB",
                                 self.restControlsColor[0]/255,
                                 self.restControlsColor[1]/255,
                                 self.restControlsColor[2]/255)

                cmds.editDisplayLayerMembers( 'Joints', selJoints[i], noRecurse=True )
                if self.controlShape=="Circle":
                    cmds.editDisplayLayerMembers('Controls', controlCurve[0], noRecurse=True)
                elif self.controlShape=="Cube":
                    cmds.editDisplayLayerMembers('Controls', controlCurve, noRecurse=True)

            for i in range (len(selJoints)):
                jointParent = cmds.listRelatives (selJoints[i], parent=True)
                if jointParent != None:
                    if cmds.objExists(jointParent[0]+'_Ctrl'):
                        cmds.parent(selJoints[i] + '_Grp', jointParent[0] + '_Ctrl')

if __name__ == "__main__":   
    try:
        lmrigger_dialog.close()
        lmrigger_dialog.deleteLater()
    except:
        pass
            
    lmrigger_dialog = LMriggerDialog()
    lmrigger_dialog.show()