# Installing 456D Design

This package is a FreeCAD workbench, not a standalone application. It has been
tested with FreeCAD 1.0.0. It uses the Python, Qt and geometry modules supplied
with FreeCAD; no separate pip installation is needed.

## Manual ZIP Installation

1. Save your documents and close FreeCAD.
2. Locate FreeCAD's user data folder. In FreeCAD's Python console,
   `App.getUserAppDataDir()` prints its location. The workbench belongs in the
   `Mod` subfolder of that location.
3. If `Mod/EasyDesign` already exists, back it up outside `Mod` first. Do not
   leave a second copy inside `Mod`, where FreeCAD would load it too.
4. Extract the ZIP's `EasyDesign` folder into `Mod`. Check that
   `Mod/EasyDesign/InitGui.py` exists, without an extra nested folder.
5. Start FreeCAD and select **456D Design** from the workbench list.

The folder, Python modules, saved property identifiers and workbench class keep
their existing EasyDesign names for compatibility with older documents and
preferences. The name shown in the interface is **456D Design**. Installation
does not change documents, camera preferences or other FreeCAD settings.

## GitHub Distribution

Publish the contents of the ZIP's `EasyDesign` folder at the root of a dedicated
repository, rather than uploading the entire FreeCAD source tree. The ZIP can
also be attached to a GitHub release for manual/offline installation.

FreeCAD's Addon Manager supports custom repositories. Inclusion in its public
catalog requires submitting the repository to the FreeCAD addon index; simply
uploading to GitHub does not add it to that catalog. Before requesting catalog
inclusion, add `package.xml` with the real repository URL, maintainer contact,
version, license, icon and workbench class `EasyDesignWorkbench`.

References:
- https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/How_to_install_additional_workbenches.md
- https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Package_Metadata.md
- https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Add_Workbench_to_Addon_Manager.md
