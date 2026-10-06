# 456D Design workbench

For manual ZIP installation and GitHub distribution, see [INSTALL.md](INSTALL.md).
The visible name is 456D Design; internal EasyDesign identifiers remain unchanged
for compatibility with saved documents and existing preferences.

This workbench gives FreeCAD a direct sketch-to-solid workflow. It uses native
Sketcher sketches and Part Design Pad/Pocket features, so profiles and solids
remain editable in the model tree.

## Text and wrapping

Choose **Sketch > Text**, click the grid or a planar solid face, then enter
text, size in millimetres and a typeface. Text is an editable outline profile
in the sketch list. Its gear offers **Edit text**, **Move / rotate**, **Extrude**,
**Cut** and **Wrap text**. Double-clicking its tree entry also edits the text.
Copy/paste, visibility and the transform arrows work as for other sketches.
Independent letters form multiple solids in one text result; letter holes are
preserved. Editing the text rebuilds dependent extrusions.

Choose **Wrap text**, then click a cylindrical side. **Start angle** and
**Height** position the text; **Spiral angle** sets its baseline pitch.
**Wrap span** is the circumferential extent in degrees (0/Auto retains the
natural font width). A span of 720 degrees with a nonzero spiral angle makes
two turns. Wrapped glyphs use cylindrical CAD faces, not a mesh. Extrusion
is radial: positive millimetres produce relief, negative millimetres engrave.
The same Auto/New Solid/Merge/Subtract selector is available; New Solid keeps
letters independent of the cylinder. Choose **Unwrap text** to return to its
saved planar placement. Wrapping supports cylindrical faces only, not cones
or arbitrary curved surfaces. Overlapping letters and cuts beyond the radius
are rejected. Taper is unavailable for text.

## Shell validation

Shell uses the floating thickness control and validates both the geometry
and actual material removal before keeping a result. Unsupported offsets
cannot silently leave the original solid or an invalid shell. For a single
planar end cap, a section-offset cavity is available when the native normal
offset fails. This fallback preserves the outer solid but approximates the
inner wall between sampled sections; its feature explicitly reports
**Section offset (approximate)**. It is not an exact constant-normal wall
thickness on a curved loft. Apply/Cancel and Undo/Redo retain the source solid.
Straight through-holes retain their collars in the fallback. Blind pockets
on the removed cap open into the main cavity instead of leaving disconnected
islands; this is reported as **blind pockets opened** in Method and on Apply.
If a collar has insufficient clearance for the thickness, reduce thickness.
Shell geometry is cached until its source geometry, opening or thickness changes.
Grouped source solids still follow parent transformations. Apply revalidates
Shell, extrusion and face operations before committing; a failed Apply remains
cancellable and does not replace the last valid preview.
Geometrically planar B-spline sides of lofts are supported as openings.
For prismatic shapes the fallback extrudes the inner outline rather than
lofting identical sections. If OCC returns an invalid spline offset, the
inner outline alone uses a chord approximation bounded by 0.01 mm or one
twentieth of thickness, whichever is smaller. The outer geometry is unchanged.
Non-prismatic cavities use 25 sampled sections and a separate extension above
the opening, avoiding spline overshoot near the cap. For openings without
holes, the fallback rejects cavities that break through an unselected outer
face, even when the resulting solid would otherwise pass validity checks.
Unsupported openings are checked before an undo transaction starts, so a
failed Shell does not block subsequent attempts. An orphaned older Shell
transaction is committed only when no task or edit owns it, preserving edits.

## Use

Select a solid (or one of its faces/edges), then choose **Export selected** in
its gear menu. The save dialog defaults to STL, with STEP as an alternative.
Only the selected solid is exported, including its full assembly placement;
sketches, other solids and hidden history are not included. Export does not
change geometry, selection or visibility. An omitted extension is added by
the save dialog, which confirms replacement of an existing file.

The three toggles beside Grid control solid outlines, filled solid surfaces
and transparent solids independently. Turning surfaces off leaves wireframe
outlines; turning both layers off makes them invisible without changing model
tree visibility. Transparent mode uses at least 75 percent transparency.
Sketches and already hidden solids are unaffected. Settings are per document,
new visible solids follow active modes, and original appearances return when
the modes are turned off or the workbench is deactivated.

1. Switch to **456D Design**. The blue XY grid appears in the viewport. Drag
   with the right mouse button to orbit; use the mouse wheel to zoom.
   Nearly horizontal right drags orbit around the grid normal at constant
   camera height. Nearly vertical drags change elevation without changing
   azimuth. Diagonal drags remain free, and changing direction can release or
   change the axis lock during the same drag. Small pointer jitter is ignored.
   Middle-button pan, wheel zoom and modified navigation gestures remain native.
   The default is natural perspective with a restrained 30-degree vertical
   field of view: nearby geometry appears larger than distant geometry.
   **View > Orthographic** gives equal scale at every depth for comparing
   dimensions; **View > Natural perspective** restores perspective. The choice
   is remembered for 456D Design. Switching projection keeps the camera target,
   orientation and scale at the target plane; it does not change model geometry.
2. Choose **Sketch > Rectangle** or **Sketch > Circle**. Click the grid or a
   flat face to choose a drawing plane, then click the first corner or center.
   Move the pointer to size the shape, or type exact millimetres in the floating
   fields. Tab locks a dimension and moves to the next field; Enter confirms
   once the dimensions are set. The lock buttons also lock/unlock each value.
   You can also click the second point or drag.
   Press Esc to cancel. The click after choosing a tool decides the target,
   regardless of what was previously selected: click an existing sketch to
   continue drawing in it, or click the grid or a solid face for a new sketch.
3. Select the drawn profile. Click its gear to open a horizontal action strip.
   Simple profiles offer **Move / rotate**, **Scale**, **Extrude**, **Sweep**, **Revolve**,
   **Edit dimension**, **Hide**, and **Cut**. Multiple selected sketches also offer
   **Loft**. Faces, edges and whole
   solids show different actions. Move and Scale update dependent solids and
   support Undo.
4. Choose **Extrude** and drag the yellow handle or type a signed millimetre
   value. Positive values follow the sketch normal, independent of outline
   drawing order. Negative values reverse a standalone extrusion, or cut into
   an existing solid in Auto mode. The opposite-arrows button flips the sign.
   Press Enter or the checkmark to keep the result; press Esc
   or the cross to cancel.

Source sketches remain visible after extrusion. The **Skisser** list on the
left controls visibility with one checkbox per sketch and eye buttons for
showing or hiding all sketches. Click a name to select it, or to resume it
after choosing a drawing tool. Internal extrusion profiles are hidden and
are not included in this list. Visibility changes support Undo.

Hold **Ctrl** or **Shift** while clicking to select multiple sketches in the
viewport or the sketch list. Ctrl-click toggles individual selections. Alt-click
cycles through overlapping sketches and solids; Ctrl+Alt is also available when
the desktop reserves Alt-click. Plain clicks replace the selection.

Select closed sketches in the desired order and choose **Loft** in the gear,
**Construct > Loft**, or the 456D Design menu (shortcut **L**). Two sketches
always produce a straight transition. Three or more default to a smooth solid
through every section, including translated and rotated profiles; **Straight**
connects consecutive sections with ruled surfaces instead. The preview lists
the sections in selection order, with arrow buttons to reorder them. Apply
keeps the solid; Cancel removes the preview. Source sketches remain visible
and editable, and moving them updates the loft. Each sketch must contain one
closed profile; open extra lines are ignored. Separate holes or multiple closed
loops in one section are not supported. Undo/Redo handles the loft as one action.
If a source sketch is deleted, its loft section keeps its last valid outline
and reports a frozen source instead of losing the solid. Opening the document
in 456D Design recovers an independent, editable sketch from that saved
outline in a new Body. This recovery is undoable; save to retain it. Original
constraints and attachments cannot be recovered from the outline alone.
The operation defaults to **Auto**: a loft intersecting existing visible solids
cuts away the intersecting material; otherwise it creates a new solid. The
automatic choice is displayed in the operation selector. **New Solid** retains
the loft as a separate part, including when it overlaps another part.
**Subtract / Cut** explicitly requires intersection. Cuts retain the target's
color, hide the loft tool and original input, and follow edits to the source
sketches. Cancel restores the original parts. A cut that removes an entire
target is rejected; select New Solid to retain the overlapping loft instead.

Drawing uses weak screen-space snapping: grid intersections capture only
within 5 pixels, while visible sketch endpoints capture within 9 pixels and
take priority, including endpoints moved off the grid. A small circular cursor
marks the next point before it is placed. Sketch endpoints remain marked in
the viewport.

The grid toolbar button switches between full visibility and a very faint
grid, retaining its plane and snapping. The toolbar's neutral cube, pencil,
pattern and magnet symbols are original icons inspired by direct-modelling
tools; their tooltips identify each group.

Select a solid, face or edge and choose **Fargevelger** in its gear menu to
change the whole object's color. The color dialog previews changes live;
Cancel restores the original appearance, and an accepted change supports
Undo. For a Part Design body, its displayed tip and body color are updated
together. Other objects retain their colors.

For multimaterial printing, select the insert solid (or one of its faces) and
choose **Cut MM** in the gear menu. Its overlap is subtracted from the other
visible solids; the selected insert remains intact and visible. Each trimmed
object keeps its own color and becomes a separate, editable native Cut, while
its original is retained as a hidden input. A hidden snapshot of the insert
keeps the cut at its original location even when the retained insert is moved,
rotated or edited. Changes to the target's hidden input still update the cut.
Hidden objects and parts that merely touch are ignored. All overlapping
targets are handled in one Undo operation. A cut that would entirely consume
another object is rejected, preserving both material parts. Cut MM adds no
clearance between materials.

Older 456D Design Cut MM operations are upgraded when their document is opened
in this workbench. The saved cavity is frozen without moving the retained
insert or changing either part's color. This is one undoable change in memory;
save the document to retain the upgrade. Ordinary Part cuts are untouched.

**Sketch > Line / polyline** draws consecutive segments directly in the
viewport. Its floating fields set length in millimetres and angle in degrees
relative to the drawing plane. Enter locks length and moves to angle; Enter
after the angle adds the segment. Continue clicking or typing for more
segments; Esc ends the chain, retaining finished segments and discarding the
unfinished preview. Choose the tool, then click an existing sketch inside
its profile or on one of its edges to add lines to it. Drawing on flat faces
and typing exact dimensions remain supported.

Sketches can be drawn on any planar face, including vertical side faces and
tilted faces. Standalone Part objects use a linked support binder in a new
body. With a drawing tool selected, hovering over a solid face previews a
compact local grid anchored to the nearest visible face corner. Clicking
locks that corner as the sketch origin. The ground grid becomes faint while
the local grid is shown, then returns to its previous visibility afterward.
The saved corner and grid also return when continuing that sketch.
Select a flat solid face and choose **Make sketch** in its gear menu to copy
the complete outline, including holes and curved edges, into an editable
sketch on that face's plane. The new sketch is selected and visible in the
sketch list; the solid stays unchanged. This is an independent snapshot,
not an attachment: it can be moved, rotated, edited or extruded without
following later changes to the source face. Curved surfaces are not supported.
Select a sketch and choose **Move / rotate** to use the same XYZ arrows,
rotation arcs and numeric controls as solids. Attached sketches retain their
support and move through AttachmentOffset; Undo and Cancel restore their
previous placement. Choose Rectangle, Circle or Line, then click the moved
sketch to continue drawing in its own plane. Extrusion follows the
sketch normal, including after arbitrary translation and rotation.

Click inside a closed profile to select that region for extrusion. Crossing
lines partition the profile into independently selectable faces, so a corner
diagonal leaves the little triangle out when selecting the main area. The
highlight and Pad/Pocket use the same exact region. A linked profile rebuilds
the selected region when its source sketch changes; sketch lines are retained.

Choose **Transform > Move / rotate** or the selected object's gear to show
three axis arrows and three rotation arcs at its center. Drag an arrow to
translate along a world axis; drag an arc to rotate about that axis. The
floating axis selector also switches between Move X/Y/Z and Rotate X/Y/Z.
Type an exact distance in millimetres or angle in degrees, then confirm with
Enter or the green checkmark. Esc or the red cross restores the original
placement. Several axis changes can be previewed and applied as one Undo
operation. Solids inside a Body move as a complete Body; moving an attached
profile retains its support. Linear snap applies to arrow dragging, not to
typed values. Viewport navigation is unchanged.

Select one or more solid edges and choose **Fillet** or **Chamfer** from the
gear or Modify toolbar. Hold **Ctrl** while clicking edges on the same solid to add them;
Ctrl-click a selected edge again to remove only that edge. All selected edges
share the radius or size in the floating control.
A marked edge and directional handle appear with a
floating millimetre field: Radius for fillet, Size for equal-distance chamfer.
Drag the handle or type an exact positive value. Enter or the checkmark applies
the native feature; Esc or the cross cancels. Invalid sizes restore the last
valid preview. A selected face applies the operation to its boundary edges.
Part Design solids and standalone Part solids are supported, with editable
native features and Undo.

Select the face to remove and choose **Shell** in its gear menu or the Modify
toolbar (shortcut **J**). 456D Design activates the selected solid's Body and
opens FreeCAD's thickness task, where you choose wall thickness and direction.
Standalone Part solids use the equivalent Part thickness task. Several faces
of the same solid can be selected as openings.

The extrusion panel offers **Taper** (degrees) and four operations: **Auto**,
**New Solid**, **Merge**, and **Subtract / Cut**. Auto normally merges outward
extrusions and cuts inward extrusions; without contact or intersection it
creates a separate solid instead. Its label shows the current automatic
choice. A profile lifted 1 mm above a part therefore previews a visible new
solid when extruded away from that part.

New Solid always builds a separate body linked to the original profile, even
when extruded into an existing part. Merge and Subtract / Cut explicitly
override the automatic operation without changing the signed distance; a
positive cut or negative merge is possible. Merge requires contact, and Cut
requires overlap. Invalid choices restore the last valid preview. Merged and
cut features inherit the source part's appearance; separate extrusions leave
the original part's appearance and visibility untouched. Cancel and Undo
restore the source model and remove temporary profiles and bodies.
Changing operation keeps the distance and taper. Invalid angles and distances
restore the last valid preview. Cancel removes the entire preview, including
any temporary body or profile binder.

Select a planar solid face and choose **Press/Pull** from its gear to extend
the whole face or cut it inward using the same signed depth field and handle.
**Mesh** fills the face with a repeating circle, square or hexagon pattern.
Set spacing, opening size and border, then choose its extrusion depth in the
viewport. Negative depths perforate/recess the part; positive depths add the
pattern as relief. Apply is a white checkmark on green; Cancel is a white
cross on red. Face operations remain editable through their tree properties
and support Undo. Existing face holes and the specified border are preserved.
Opening is the diameter for circles and hexagons, and side length for squares.
Patterns are limited to 600 candidate cells to avoid unresponsive previews.
Mesh here means a patterned solid, not a triangulated STL mesh. Curved-face
Press/Pull is not supported yet.

For **Gear**, draw a circle and a separate tooth/profile sketch. Select the
circle, choose **Gear** in its gear menu (or the top **Pattern** menu), then
click the profile sketch. A compact count field previews equally spaced,
rotated copies around the circle's center and normal, including on vertical
or tilted sketch planes. Count is the total number, including the original;
it accepts 1-360. The source's existing distance from the center is preserved.
Apply keeps the copies as independent editable sketches under a Gear group;
Cancel/Escape removes the entire preview, and Undo reverses Apply. Copies
preserve the solved geometry, not attachments or constraints to other objects.
The source circle and profile stay unchanged and visible. This is a circular
sketch pattern, not an involute gear generator or an automatic solid union.

Select the circle, original tooth and Gear copies together with Ctrl/Shift,
then choose **Extrude** from their gear menu or the Construct toolbar. Closed
profiles on the same plane are fused before extrusion, so overlapping teeth
and the circle form one solid with one shared distance/arrow control. Inner
holes are preserved; unselected sketches and open auxiliary lines are not
included. Separated profiles are rejected rather than creating multiple
solids; different sketch planes use Loft instead. Source sketches remain
visible and linked to the result. Signed depth, taper, operation modes,
Cancel, Undo and save/reopen use the existing extrusion workflow.

For a cut, draw a closed profile on a flat face of an existing solid and use a
negative **Extrude** value. **Cut** remains as a shortcut that starts with a
negative value. The preview removes material inward and can be cancelled.

Hover over a top toolbar group to open its horizontal icon flyout; click an
icon to run the tool. The toolbar follows the task order found in 123D's UI:
transform, primitives, sketch, construct, modify, pattern, group and combine.
The flyout stays open while the pointer is inside it and hides after a short
delay when the pointer leaves. Tooltips identify the icons. Extrude also uses
**U** when the viewport has focus.

With the viewport focused, the 123D-style shortcuts **P**, **W**, **V**, **L**,
**E**, **C** and **J** invoke Press/Pull, Sweep, Revolve, Loft, Fillet, Chamfer
and Shell. Press/Pull requires one selected planar solid face and is also in
the top **Modify** group. Modified key combinations are left to FreeCAD.

The linear snap menu offers **0.1**, **0.25**, **0.5**, **0.75**, **1**, **5**,
**10 mm**, and **Off**, and remembers the choice. Snap applies to mouse-drawn
extrusion and translation dragging. Drawing-point snapping instead uses the
pixel-distance rules above, independent of the numeric step. Typed dimensions stay
exact. It defaults to Off.

All sketch tools in 456D Design use the same viewport, local face grid,
point indicator, teal preview and screen-space snapping. They never enter
Sketcher's edit mode. Three-point arcs take the two endpoints first, then a
point on the arc. Ellipses take the center, the first axis endpoint, then the
second radius. Center arcs take center, start and end, with a typed sweep.
Polygons expose radius and side count (3-128). Splines interpolate the clicked
points; Apply finishes an open spline and clicking the first point closes it.
Pending points also have the stronger endpoint snap, including off-grid points.
Each stage has floating dimensions with locks and Apply/Cancel controls.

Sketch fillet selects a corner shared by two lines and accepts a radius.
Trim removes the clicked portion of a sketch curve. Extend selects a line and
extends its nearest endpoint by the signed distance. Offset selects an outline
and adds an offset copy without replacing the source. These edits also remain
in the viewport and support undo; Cancel restores the original sketch.
**Edit sketch** resumes the selected sketch with the viewport polyline tool.
Sweep and Revolve still use native FreeCAD task dialogs.

To use this workbench with an existing FreeCAD installation, follow
[INSTALL.md](INSTALL.md). Install its files inside `Mod/EasyDesign` in FreeCAD's
user data folder and restart FreeCAD. The workbench is listed as **456D Design**.

This version supports direct sketch tools on arbitrary planar faces. It does
not yet support all of 123D Design's modelling operations. Sketch extension
currently handles line segments, and sketch fillets require two joined lines.
