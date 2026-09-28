# Two Inkscape extensions for LaserGRBL

These are small Inkscape extensions for a workflow with blue interior cuts and red exterior cuts. The interface and status messages are currently in Dutch. The source files are included so you can inspect them before installing.

## 1. Route optimizer

`lasergrbl_route_optimizer.py` and `lasergrbl_route_optimizer.inx` reorder SVG paths within groups that have the same parent, transform, and rendered style. It chooses a nearby eligible path and can place contained paths before surrounding paths. With its default settings, paths of the same style are combined into one SVG path so their subpath order is more likely to be preserved by LaserGRBL. Blue and red stay separate.

The containment check uses bounding boxes. It is a useful heuristic, not a guarantee for concave or unusual geometry. Estimated travel reduction is a calculation on SVG endpoints; actual LaserGRBL motion may differ.

## 2. Holding tabs

`lasergrbl_brugjes.py` and `lasergrbl_brugjes.inx` add two evenly spaced uncut gaps to each closed, pure-red (`#ff0000`) contour. The default gap is 0.75 mm; count and width can be changed in the extension dialog. Blue paths are left alone. Gap width is approximate for paths under nonuniform transforms.

## Install on Windows

1. Close Inkscape.
2. Copy all four `.py` and `.inx` files into `%APPDATA%\inkscape\extensions`.
3. Start Inkscape. Both commands appear under **Extensions > LaserGRBL**.

## Use

1. Save a copy of the original SVG.
2. Run the route optimizer. The default option processes visible paths, with colors kept separate.
3. Run the holding-tab extension on the red outer contours.
4. Save the result under a new name.
5. In LaserGRBL, inspect the preview and travel moves carefully. In the original workflow, blue and red were imported as separate jobs, with blue first.

These extensions process SVG paths. Convert text and basic shapes to paths first if needed. The route optimizer was tested on a 104-path sample SVG; the holding-tab extension on 60 red contours. The result has not been validated on every Inkscape/LaserGRBL version or laser machine. Always check the toolpath before cutting.

The code was developed with AI assistance and manually checked against the sample SVG.
