#!/usr/bin/env python3
"""Add small holding bridges to red laser-cut outer contours."""

from copy import deepcopy
import math

import inkex
from inkex import bezier, CubicSuperPath, PathElement


RED_VALUES = {"#ff0000", "red", "rgb(255,0,0)", "rgb(100%,0%,0%)"}


def same_point(first, second, tolerance=1e-7):
    return (
        abs(first[0] - second[0]) <= tolerance
        and abs(first[1] - second[1]) <= tolerance
    )


def inside_gap(position, intervals):
    return any(start < position < end for start, end in intervals)


class LaserGRBLBrugjes(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--gap", type=float, default=0.75)
        pars.add_argument("--count", type=int, default=2)
        pars.add_argument("--scope", default="auto")

    @staticmethod
    def effective_style(node):
        try:
            return node.specified_style()
        except AttributeError:
            return node.style

    def is_red_path(self, node):
        stroke = str(self.effective_style(node).get("stroke", "none"))
        normalized = stroke.lower().replace(" ", "")
        return normalized in RED_VALUES and bool(node.get("d", "").strip())

    def target_paths(self):
        selected = list(self.svg.selection.filter(PathElement))
        selected_red = [node for node in selected if self.is_red_path(node)]
        if self.options.scope == "selection":
            return selected_red
        if self.options.scope == "auto" and selected_red:
            return selected_red
        return [
            node
            for node in self.svg.xpath("//svg:path")
            if self.is_red_path(node)
        ]

    @staticmethod
    def local_scale(node):
        """Approximate document-units per local unit for transformed paths."""
        transform = node.composed_transform()
        origin = transform.apply_to_point((0, 0))
        x_axis = transform.apply_to_point((1, 0))
        y_axis = transform.apply_to_point((0, 1))
        scale_x = math.hypot(x_axis.x - origin.x, x_axis.y - origin.y)
        scale_y = math.hypot(y_axis.x - origin.x, y_axis.y - origin.y)
        scale = (scale_x + scale_y) / 2.0
        return scale if scale > 1e-12 else 1.0

    @staticmethod
    def split_segment(start_node, end_node, segment_start, segment_end, boundaries):
        """Split one CSP segment at global-length boundaries."""
        pieces = []
        current_start = deepcopy(start_node)
        current_end = deepcopy(end_node)
        cursor = segment_start

        for boundary in boundaries:
            if not (segment_start + 1e-9 < boundary < segment_end - 1e-9):
                continue
            remaining_length = bezier.cspseglength(current_start, current_end)
            wanted = boundary - cursor
            if remaining_length <= 1e-12 or wanted <= 1e-12:
                continue
            fraction = min(1.0, max(0.0, wanted / remaining_length))
            left, middle, right = bezier.cspbezsplitatlength(
                current_start, current_end, fraction
            )
            pieces.append((left, middle, cursor, boundary))
            current_start = middle
            current_end = right
            cursor = boundary

        pieces.append((current_start, current_end, cursor, segment_end))
        return pieces

    def bridge_subpath(self, subpath, gap_size, count):
        """Return open CSP sections with evenly spaced gaps removed."""
        if len(subpath) < 3 or not same_point(subpath[0][1], subpath[-1][1]):
            return [deepcopy(subpath)], 0, False

        segment_lengths = [
            bezier.cspseglength(subpath[index - 1], subpath[index])
            for index in range(1, len(subpath))
        ]
        perimeter = sum(segment_lengths)
        spacing = perimeter / count if count else 0.0
        if count < 1 or gap_size <= 0 or gap_size >= spacing * 0.8:
            return [deepcopy(subpath)], 0, False

        centers = [(index + 0.5) * spacing for index in range(count)]
        intervals = [
            (center - gap_size / 2.0, center + gap_size / 2.0)
            for center in centers
        ]
        boundaries = sorted(value for interval in intervals for value in interval)

        sections = []
        current_section = None
        cursor = 0.0
        for index, segment_length in enumerate(segment_lengths, start=1):
            segment_end = cursor + segment_length
            local_boundaries = [
                value for value in boundaries if cursor < value < segment_end
            ]
            pieces = self.split_segment(
                subpath[index - 1],
                subpath[index],
                cursor,
                segment_end,
                local_boundaries,
            )
            for piece_start, piece_end, piece_from, piece_to in pieces:
                midpoint = (piece_from + piece_to) / 2.0
                if inside_gap(midpoint, intervals):
                    current_section = None
                    continue
                if current_section is None:
                    current_section = [piece_start, piece_end]
                    sections.append(current_section)
                else:
                    # Keep the incoming handle from the preceding piece and
                    # take the outgoing handle from the following piece.
                    current_section[-1][2] = deepcopy(piece_start[2])
                    current_section.append(piece_end)
            cursor = segment_end

        return sections, count, True

    def effect(self):
        targets = self.target_paths()
        if not targets:
            raise inkex.AbortExtension(
                "Geen rode paden gevonden. Gebruik een zuiver rode lijn (#ff0000)."
            )

        gap_document_units = self.svg.unittouu(f"{self.options.gap}mm")
        bridge_count = max(1, min(12, self.options.count))
        changed_paths = 0
        changed_contours = 0
        total_bridges = 0
        skipped_contours = 0

        for node in targets:
            gap_local = gap_document_units / self.local_scale(node)
            original = CubicSuperPath(node.path)
            output = []
            node_changed = False
            for subpath in original:
                sections, bridges, changed = self.bridge_subpath(
                    subpath, gap_local, bridge_count
                )
                output.extend(sections)
                if changed:
                    node_changed = True
                    changed_contours += 1
                    total_bridges += bridges
                elif same_point(subpath[0][1], subpath[-1][1]):
                    skipped_contours += 1

            if node_changed:
                node.path = CubicSuperPath(output).to_path(curves_only=False)
                node.set("data-lasergrbl-brugjes", str(bridge_count))
                node.set("data-lasergrbl-brugbreedte-mm", f"{self.options.gap:g}")
                changed_paths += 1

        if not changed_paths:
            raise inkex.AbortExtension(
                "Geen geschikte gesloten rode contouren gevonden. Mogelijk zijn "
                "de contouren te klein voor deze brugbreedte."
            )

        message = (
            f"Brugjes toegevoegd aan {changed_contours} rode buitencontouren: "
            f"{total_bridges} openingen van {self.options.gap:g} mm."
        )
        if skipped_contours:
            message += f" {skipped_contours} contouren zijn overgeslagen."
        message += " Gebruik Ctrl+Z om terug te gaan en sla op onder een nieuwe naam."
        inkex.errormsg(message)


if __name__ == "__main__":
    LaserGRBLBrugjes().run()
