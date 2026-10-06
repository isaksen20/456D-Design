# SPDX-License-Identifier: LGPL-2.1-or-later

class EasyDesignWorkbench(Workbench):
    MenuText = "456D Design"
    ToolTip = "Draw a profile, then pull it into a solid"
    def __init__(self):
        import os
        from importlib.util import find_spec

        self.Icon = os.path.join(
            os.path.dirname(find_spec("EasyDesignCommands").origin),
            "Resources", "icons", "EasyDesign.svg"
        )
        if not os.path.isfile(self.Icon):
            self.Icon = os.path.join(
                FreeCAD.getResourceDir(), "Mod", "EasyDesign", "Resources", "icons", "EasyDesign.svg"
            )

    def Initialize(self):
        import PartDesignGui  # noqa: F401
        import SketcherGui  # noqa: F401
        import EasyDesignCommands

        EasyDesignCommands.register_commands()
        self.appendMenu(
            "456D Design",
            [
                "EasyDesign_Draw",
                "EasyDesign_Rectangle",
                "EasyDesign_Circle",
                "EasyDesign_Polyline",
                "EasyDesign_Text",
                "EasyDesign_FinishPull",
                "EasyDesign_FinishCut",
                "EasyDesign_Loft",
            ],
        )

    def Activated(self):
        import EasyDesignView

        EasyDesignView.activate()

    def Deactivated(self):
        import EasyDesignView

        EasyDesignView.deactivate()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(EasyDesignWorkbench())
