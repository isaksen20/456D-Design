# SPDX-License-Identifier: LGPL-2.1-or-later

"""Reversible solid rendering overrides; model visibility is never changed."""


class SolidDisplay:
    def __init__(self):
        self.outlines = True
        self.solids = True
        self.transparent = False
        self._appearance = {}

    @staticmethod
    def _visible_solid(obj):
        view = obj.ViewObject
        if (not view or not view.Visibility or not hasattr(obj, "Shape")
                or not hasattr(view, "DisplayMode") or not hasattr(view, "Transparency")
                or view.DisplayMode not in ("Flat Lines", "Shaded", "Wireframe", "Points")):
            return False
        parent = obj.getParentGeoFeatureGroup()
        while parent:
            if parent.ViewObject and not parent.ViewObject.Visibility:
                return False
            parent = parent.getParentGeoFeatureGroup()
        return bool(obj.Shape.Solids)

    def _capture(self, obj):
        original = {name: getattr(obj.ViewObject, name) for name in ("DisplayMode", "Transparency")}
        # New dress-ups can copy their source's temporary appearance. Keep its
        # underlying settings so turning the mode off does not bake in the override.
        for source in obj.OutList:
            entry = self._appearance.get(source.Name)
            if entry and entry["object"] == source:
                for name in original:
                    if original[name] == entry["applied"].get(name):
                        original[name] = entry["original"][name]
                break
        return {"object": obj, "original": original, "applied": {}}

    @staticmethod
    def _restore_changes(entry):
        view = entry["object"].ViewObject
        return [(entry["object"], name, value) for name, value in entry["original"].items()
                if getattr(view, name) == entry["applied"].get(name)]

    @staticmethod
    def _write(changes):
        explicit = {(obj.Name, prop) for obj, prop, value in changes}
        protected = {}
        materials = {}
        body_changes, other_changes = [], []
        for obj, prop, value in changes:
            if getattr(obj, "isDerivedFrom", lambda kind: False)("PartDesign::Body"):
                if getattr(obj.ViewObject, prop) == value:
                    continue
                body_changes.append((obj, prop, value))
                for child in obj.Group:
                    if hasattr(child.ViewObject, "ShapeAppearance"):
                        materials[child.Name] = (child, child.ViewObject.ShapeAppearance)
                    if (child.Name, prop) not in explicit and hasattr(child.ViewObject, prop):
                        protected[child.Name, prop] = (child, prop, getattr(child.ViewObject, prop))
            else:
                other_changes.append((obj, prop, value))
        # Body setters propagate to child view providers. Decide every value
        # before writing, and protect sketches/history not targeted by the mode.
        for obj, prop, value in body_changes:
            if getattr(obj.ViewObject, prop) != value:
                setattr(obj.ViewObject, prop, value)
        for obj, appearance in materials.values():
            if obj.ViewObject.ShapeAppearance != appearance:
                obj.ViewObject.ShapeAppearance = appearance
        for obj, prop, value in other_changes:
            if getattr(obj.ViewObject, prop) != value:
                setattr(obj.ViewObject, prop, value)
        for obj, prop, value in protected.values():
            if getattr(obj.ViewObject, prop) != value:
                setattr(obj.ViewObject, prop, value)

    def restore(self, doc):
        changes = []
        for name, entry in self._appearance.items():
            if doc.getObject(name) == entry["object"]:
                changes.extend(self._restore_changes(entry))
        self._write(changes)
        self._appearance.clear()

    def apply(self, doc):
        if self.outlines and self.solids and not self.transparent:
            self.restore(doc)
            return
        targets = {obj.Name: obj for obj in doc.Objects if self._visible_solid(obj)}
        # Capture new results before releasing the source's hidden-history entry.
        for name, obj in targets.items():
            if name not in self._appearance or self._appearance[name]["object"] != obj:
                self._appearance[name] = self._capture(obj)
        for name, obj in targets.items():
            entry = self._appearance[name]
            for prop, last in entry["applied"].items():
                if getattr(obj.ViewObject, prop) != last:
                    entry["original"][prop] = getattr(obj.ViewObject, prop)
        changes = []
        for name in list(self._appearance):
            entry = self._appearance[name]
            if name not in targets:
                if doc.getObject(name) == entry["object"]:
                    changes.extend(self._restore_changes(entry))
                else:
                    del self._appearance[name]
                continue
            original = entry["original"]
            mode = original["DisplayMode"]
            if not self.solids:
                mode = "Wireframe" if self.outlines else "Shaded"
            elif not self.outlines:
                mode = "Shaded"
            transparency = max(original["Transparency"], 75) if self.transparent else original["Transparency"]
            if not self.solids and not self.outlines:
                # Hide both rendered layers without changing Visibility, which
                # modelling operations use to manage source/history objects.
                transparency = 100
            desired = {"DisplayMode": mode, "Transparency": transparency}
            for prop, value in desired.items():
                changes.append((entry["object"], prop, value))
            entry["applied"] = desired
        self._write(changes)
