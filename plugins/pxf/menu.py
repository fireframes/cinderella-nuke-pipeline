#############################################################
# menmenu.py
# Add Pixelfuger menu to Nuke's Nodes menmenu.
# (C) 2024 - Xavier Bourque - www.pixelfudger.com
#############################################################

import nuke

def register_pixelfudger_menu(menu, toolbar):
    """Add Pixelfudger menu to Nuke's Nodes menmenu."""
    aboutMsg = 'Pixelfudger 3.3 \nDecember 2024\nCreated by: Xavier Bourque\nwww.pixelfudger.com\n(c) 2011-2024'

    menu.addCommand( "PxF_IDefocus", "nuke.createNode('PxF_IDefocus', inpanel=False)")
    menu.addCommand( "PxF_ZDefocus", "nuke.createNode('PxF_ZDefocus', inpanel=False)")
    menu.addCommand( "PxF_HueSat", "nuke.createNode('PxF_HueSat', inpanel=False)")
    menu.addCommand( "PxF_Distort", "nuke.createNode('PxF_Distort', inpanel=False)")
    menu.addCommand( "PxF_SmokeBox", "nuke.createNode('PxF_SmokeBox', inpanel=False)")
    menu.addCommand( "PxF_VectorEdgeBlur", "nuke.createNode('PxF_VectorEdgeBlur', inpanel=False)")
    menu.addSeparator()
    menu.addCommand("About Pixelfudger...", lambda a=aboutMsg: nuke.message(a))

    toolbar.addCommand("PxF_IDefocus", "nuke.createNode('PxF_IDefocus', inpanel=False)")
    toolbar.addCommand("PxF_ZDefocus", "nuke.createNode('PxF_ZDefocus', inpanel=False)")
    toolbar.addCommand("PxF_HueSat", "nuke.createNode('PxF_HueSat', inpanel=False)")
    toolbar.addCommand("PxF_Distort", "nuke.createNode('PxF_Distort', inpanel=False)")
    toolbar.addCommand("PxF_SmokeBox", "nuke.createNode('PxF_SmokeBox', inpanel=False)")
    toolbar.addCommand("PxF_VectorEdgeBlur", "nuke.createNode('PxF_VectorEdgeBlur', inpanel=False)")
    toolbar.addSeparator()
    toolbar.addCommand("About Pixelfudger...", lambda a=aboutMsg: nuke.message(a))
