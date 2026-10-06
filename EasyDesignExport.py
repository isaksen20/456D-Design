# SPDX-License-Identifier: LGPL-2.1-or-later

"""Export one selected solid without adding objects or changing the document."""

import os
from pathlib import Path
import re
import tempfile


STL_FILTER = "STL mesh (*.stl)"
STEP_FILTER = "STEP solid (*.step *.stp)"


def file_label(obj):
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", obj.Label).strip(". ")
    return label or obj.Name


def solid_shape(obj):
    if not hasattr(obj, "Shape"):
        raise ValueError("Select a solid to export.")
    from EasyDesignMM import _shape
    shape = _shape(obj).copy()
    if shape.isNull() or not shape.Solids or not shape.isValid():
        raise ValueError("Export needs a valid solid.")
    return shape


def export_selected(obj, filename):
    path = Path(filename)
    extension = path.suffix.lower()
    if extension not in (".stl", ".step", ".stp"):
        raise ValueError("Choose an STL (.stl) or STEP (.step/.stp) filename.")
    shape = solid_shape(obj)
    # Complete and validate the output before replacing an existing export.
    with tempfile.TemporaryDirectory(prefix=".easydesign-export-", dir=path.parent) as directory:
        temporary = Path(directory) / ("solid" + extension)
        if extension == ".stl":
            import MeshPart
            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=.1,
                                          AngularDeflection=.25, Relative=False)
            if mesh.CountFacets == 0:
                raise ValueError("The solid could not be meshed for STL export.")
            mesh.write(str(temporary))
        else:
            shape.exportStep(str(temporary))
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ValueError("Export did not produce a file.")
        os.replace(temporary, path)
    return path
