# SPDX-License-Identifier: LGPL-2.1-or-later

"""Keep a material insert while subtracting it from other visible solids."""

import Part


def solid_object(obj):
    if obj.isDerivedFrom("PartDesign::Body"):
        return obj
    parent = obj.getParentGeoFeatureGroup()
    return parent if parent and parent.isDerivedFrom("PartDesign::Body") else obj


def _reference(obj):
    names = []
    root = obj
    parent = root.getParentGeoFeatureGroup()
    while parent:
        names.insert(0, root.Name)
        root = parent
        parent = root.getParentGeoFeatureGroup()
    return root, ".".join(names) + "." if names else ""


def _visible(obj):
    while obj:
        if obj.ViewObject and not obj.ViewObject.Visibility:
            return False
        obj = obj.getParentGeoFeatureGroup()
    return True


def _shape(obj):
    root, path = _reference(obj)
    return Part.getShape(root, path)


def _plan(cutter):
    cutter = solid_object(cutter)
    if cutter.isDerivedFrom("App::Part"):
        raise ValueError("Select an individual solid, not a group, for Cut MM.")
    tool = _shape(cutter)
    if tool.isNull() or not tool.Solids or not tool.isValid():
        raise ValueError("Select a valid solid for Cut MM.")
    targets = []
    for obj in cutter.Document.Objects:
        if (obj == cutter or obj.isDerivedFrom("App::Part")
                or solid_object(obj) != obj or not _visible(obj)
                or not hasattr(obj, "Shape") or not obj.Shape.Solids
                or obj.isDerivedFrom("PartDesign::SubShapeBinder")
                or obj.isDerivedFrom("PartDesign::ShapeBinder")):
            continue
        base = _shape(obj)
        if not base.BoundBox.intersect(tool.BoundBox):
            continue
        if base.common(tool).Volume <= 1e-7:
            continue
        result = base.cut(tool).removeSplitter()
        if result.isNull() or not result.Solids or result.Volume <= 1e-7:
            raise ValueError("Cut MM would remove all of '%s'. Both parts must retain solid material." % obj.Label)
        if not result.isValid():
            raise ValueError("Cut MM could not produce a valid solid for '%s'." % obj.Label)
        targets.append((obj, result.Volume))
    return cutter, targets


def _input(doc, obj, cache):
    root, path = _reference(obj)
    if not path:
        return obj
    if obj.Name not in cache:
        # Native booleans only see their inputs' local frames. A root-level
        # binder resolves the full group path and follows parent placements.
        binder = doc.addObject("PartDesign::SubShapeBinder", "MMReference")
        binder.Label = obj.Label + " (MM reference)"
        binder.Support = [(root, [path])]
        binder.ViewObject.Visibility = False
        cache[obj.Name] = binder
    return cache[obj.Name]


def _appearance(target, result):
    source = target.Tip if target.isDerivedFrom("PartDesign::Body") and target.Tip else target
    for name in ("ShapeColor", "LineColor", "PointColor", "Transparency", "LineWidth"):
        if hasattr(source.ViewObject, name) and hasattr(result.ViewObject, name):
            setattr(result.ViewObject, name, getattr(source.ViewObject, name))
    if hasattr(source.ViewObject, "ShapeColor"):
        result.ViewObject.DiffuseColor = [tuple(source.ViewObject.ShapeColor[:3])] * len(result.Shape.Faces)


def _tool_snapshot(doc, cutter):
    tool = doc.addObject("Part::Feature", "MMTool")
    tool.Label = cutter.Label + " (MM tool snapshot)"
    tool.Shape = _shape(cutter).copy()
    tool.ViewObject.Visibility = False
    return tool


def upgrade_legacy_cuts(doc):
    """Freeze older 456D Design cuts without changing their saved cavities."""
    legacy = [obj for obj in doc.Objects
              if obj.isDerivedFrom("Part::Cut") and obj.Name.startswith("CutMM")
              and obj.Label.endswith(" (Cut MM)") and obj.Base and obj.Tool
              and not (obj.Tool.TypeId == "Part::Feature" and obj.Tool.Name.startswith("MMTool"))]
    if not legacy:
        return []
    planned = []
    for cut in legacy:
        base, result = _shape(cut.Base), _shape(cut)
        removed = base.cut(result).removeSplitter()
        if (not removed.Solids or removed.Volume <= 1e-7
                or result.cut(base).Volume > 1e-7 or not removed.isValid()):
            raise ValueError("The saved '%s' has no recoverable Cut MM cavity." % cut.Label)
        appearance = {name: getattr(cut.ViewObject, name)
                      for name in ("ShapeColor", "DiffuseColor", "Transparency", "LineColor")}
        planned.append((cut, removed, result.copy(), appearance))
    doc.openTransaction("Upgrade Cut MM")
    try:
        for cut, removed, previous, appearance in planned:
            # The saved result retains the original cavity even if the insert
            # has since moved. Freeze only that removed material for old cuts.
            tool = doc.addObject("Part::Feature", "MMTool")
            tool.Label = cut.Label + " (MM tool snapshot)"
            tool.Shape = removed
            tool.ViewObject.Visibility = False
            cut.Tool = tool
        doc.recompute()
        for cut, removed, previous, appearance in planned:
            shape = _shape(cut)
            if (shape.isNull() or not shape.isValid() or not shape.Solids
                    or shape.cut(previous).Volume + previous.cut(shape).Volume > 1e-7):
                raise ValueError("Could not preserve the saved cavity for '%s'." % cut.Label)
            for name, value in appearance.items():
                setattr(cut.ViewObject, name, value)
            cut.Tool.ViewObject.Visibility = False
        doc.commitTransaction()
        return legacy
    except Exception:
        doc.abortTransaction()
        raise


def cut_mm(obj):
    """Create undoable native cuts; the selected cutter stays visible and intact."""
    doc = obj.Document
    doc.recompute()
    cutter, targets = _plan(obj)
    if not targets:
        return []
    originals = []
    for source in [cutter] + [target for target, _ in targets]:
        originals.append((source, source.ViewObject.Visibility))
        if source.isDerivedFrom("PartDesign::Body") and source.Tip:
            originals.append((source.Tip, source.Tip.ViewObject.Visibility))
    doc.openTransaction("Cut MM")
    try:
        references = {}
        # Keep the cut at the insertion position when the material part moves.
        tool = _tool_snapshot(doc, cutter)
        results = []
        for target, expected_volume in targets:
            result = doc.addObject("Part::Cut", "CutMM")
            result.Label = target.Label + " (Cut MM)"
            result.Base = _input(doc, target, references)
            result.Tool = tool
            result.Refine = True
            results.append((target, result, expected_volume))
        doc.recompute()
        for target, result, expected_volume in results:
            if ("Invalid" in result.State or result.Shape.isNull() or not result.Shape.isValid()
                    or not result.Shape.Solids
                    or abs(result.Shape.Volume - expected_volume) > max(1e-7, expected_volume * 1e-7)):
                raise ValueError("Cut MM failed for '%s'." % target.Label)
            _appearance(target, result)
            target.ViewObject.Visibility = False
            result.ViewObject.Visibility = True
        for binder in references.values():
            binder.ViewObject.Visibility = False
        for source, visible in originals:
            if source == cutter or (cutter.isDerivedFrom("PartDesign::Body") and source == cutter.Tip):
                source.ViewObject.Visibility = visible
        doc.commitTransaction()
        return [result for _, result, _ in results]
    except Exception:
        doc.abortTransaction()
        for source, visible in originals:
            source.ViewObject.Visibility = visible
        raise
