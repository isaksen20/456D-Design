# 456D Design

I’ve used Autodesk 123D Design for years. Even long after it was discontinued, I kept using it because the workflow was simple, fast, and intuitive. Over the years I tried several alternatives, but I never found anything that truly replaced the way 123D Design let me go directly from a simple sketch to a finished 3D model.

Eventually, I decided to build the alternative I had been missing.

**456D Design** is a FreeCAD workbench designed to combine the simple, direct workflow of 123D Design with FreeCAD’s modern parametric CAD engine.

The goal is not to create a one-to-one copy of 123D Design, but to recreate much of the same feel and workflow: draw directly in the 3D view, select profiles and faces, and use simple tools to extrude, cut, move, rotate, scale, and continue building the model without constantly switching between different work environments.

456D Design uses FreeCAD’s own Sketcher, Part, and Part Design functionality underneath. This means sketches, extrusions, cuts, and other operations remain real, editable FreeCAD objects in the model tree rather than temporary or “dumb” geometry.

The workflow is built around direct modelling:

- Draw rectangles, circles, lines, arcs, polygons, splines, and text directly in the viewport.
- Sketch on the main grid or directly on planar faces of existing solids.
- Click a closed profile and extrude or cut it.
- Move and rotate objects using axis arrows and rotation handles directly in the 3D view.
- Use Extrude, Loft, Sweep, Revolve, Fillet, Chamfer, Shell, and Press/Pull in a workflow inspired by 123D Design.
- Edit source sketches later and let dependent geometry update automatically.
- Use snapping, exact dimensions, and keyboard shortcuts without entering FreeCAD’s traditional Sketcher edit mode.

The interface also follows much of the philosophy behind 123D Design. Tools are organized into familiar groups such as **Transform**, **Primitives**, **Sketch**, **Construct**, **Modify**, **Pattern**, **Group**, and **Combine**, with horizontal tool flyouts and a more direct workflow than standard FreeCAD.

Over time, 456D Design has also gained features that go beyond what 123D Design offered, including wrapped text on cylindrical surfaces, multimaterial cutting for 3D printing, more flexible loft workflows, pattern tools, and improved sketching on arbitrary planar faces.

The project is still under active development, and the goal is not to replicate every feature from 123D Design immediately. The goal is to create a workbench that is fast to learn, comfortable to use, and makes FreeCAD more approachable for people who prefer a direct modelling workflow.

If you are coming from 123D Design, the workflow should hopefully feel familiar very quickly.

**123D Design was the starting point. FreeCAD is the foundation. 456D Design is my attempt to bridge the two.**
