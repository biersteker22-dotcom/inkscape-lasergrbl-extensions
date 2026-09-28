#!/usr/bin/env python3
"""Optimize SVG path order for LaserGRBL without changing geometry."""

import math
from collections import defaultdict

import inkex


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_tuple(point):
    return (float(point.x), float(point.y))


def is_closed(node):
    return node.get("d", "").rstrip().lower().endswith("z")


def box_contains(outer, inner, epsilon=1e-7):
    """Return True when inner's complete bounding box lies inside outer."""
    if outer.area <= inner.area + epsilon:
        return False
    return (
        outer.left <= inner.left + epsilon
        and outer.right >= inner.right - epsilon
        and outer.top <= inner.top + epsilon
        and outer.bottom >= inner.bottom - epsilon
    )


class PathInfo:
    def __init__(self, node):
        self.node = node
        self.refresh()

    def refresh(self):
        document_path = self.node.path.transform(self.node.composed_transform())
        endpoints = list(document_path.end_points)
        if not endpoints:
            raise ValueError("Leeg pad")
        self.start = point_tuple(endpoints[0])
        self.end = point_tuple(endpoints[-1])
        self.box = document_path.bounding_box()
        self.closed = is_closed(self.node)

    def reverse(self):
        self.node.path = self.node.path.reverse()
        self.refresh()


class LaserGRBLRouteOptimizer(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--scope", default="document")
        pars.add_argument("--start", default="bottom_left")
        pars.add_argument("--inside-first", type=inkex.Boolean, default=True)
        pars.add_argument("--reverse-open", type=inkex.Boolean, default=True)
        pars.add_argument("--combine", type=inkex.Boolean, default=True)

    def _selected_paths(self):
        selected = list(self.svg.selection.filter(inkex.PathElement))
        if self.options.scope == "selection" and selected:
            return selected
        return list(self.svg.xpath("//svg:path"))

    @staticmethod
    def _effective_style(node):
        try:
            return node.specified_style()
        except AttributeError:
            return node.style

    def _usable(self, node):
        style = self._effective_style(node)
        return (
            node.getparent() is not None
            and style.get("display", "inline") != "none"
            and style.get("visibility", "visible") != "hidden"
            and style.get("stroke", "none") != "none"
            and bool(node.get("d", "").strip())
        )

    def _group_key(self, node):
        # Combining is safe only when parent, transform and full rendered style match.
        style = str(self._effective_style(node))
        return (node.getparent(), node.get("transform", ""), style)

    def _corner(self, infos):
        left = min(item.box.left for item in infos)
        right = max(item.box.right for item in infos)
        top = min(item.box.top for item in infos)
        bottom = max(item.box.bottom for item in infos)
        corners = {
            "top_left": (left, top),
            "top_right": (right, top),
            "bottom_right": (right, bottom),
            "bottom_left": (left, bottom),
        }
        return corners.get(self.options.start, corners["bottom_left"])

    @staticmethod
    def _travel(infos, start):
        cursor = start
        total = 0.0
        for item in infos:
            total += distance(cursor, item.start)
            cursor = item.end
        return total

    def _optimize(self, infos):
        start = self._corner(infos)
        dependencies = {item: set() for item in infos}
        if self.options.inside_first:
            for outer in infos:
                if not outer.closed:
                    continue
                for inner in infos:
                    if inner is not outer and box_contains(outer.box, inner.box):
                        dependencies[outer].add(inner)

        remaining = set(infos)
        completed = set()
        ordered = []
        cursor = start

        while remaining:
            eligible = [
                item for item in remaining if dependencies[item].issubset(completed)
            ]
            # Defensive fallback for malformed/equal contours.
            if not eligible:
                eligible = list(remaining)

            best = None
            best_reverse = False
            best_distance = float("inf")
            for item in eligible:
                forward = distance(cursor, item.start)
                reverse = distance(cursor, item.end)
                may_reverse = self.options.reverse_open and not item.closed
                candidate_distance = min(forward, reverse) if may_reverse else forward
                tie_break = (candidate_distance, item.box.area, item.node.get("id", ""))
                if best is None or tie_break < best_distance:
                    best = item
                    best_reverse = may_reverse and reverse < forward
                    best_distance = tie_break

            if best_reverse:
                best.reverse()
            ordered.append(best)
            cursor = best.end
            remaining.remove(best)
            completed.add(best)

        return ordered, start

    @staticmethod
    def _stroke_label(node):
        stroke = str(node.specified_style().get("stroke", "kleur"))
        return stroke.replace("#", "") or "kleur"

    def _combine(self, ordered, group_number):
        first = ordered[0].node
        parent = first.getparent()
        insertion_index = min(parent.index(item.node) for item in ordered)

        combined = inkex.PathElement()
        combined.set("id", self.svg.get_unique_id("lasergrbl-geoptimaliseerd-"))
        combined.set("style", str(self._effective_style(first)))
        if first.get("transform"):
            combined.set("transform", first.get("transform"))
        combined.set("data-lasergrbl-route", str(group_number))
        combined.set("data-lasergrbl-kleur", self._stroke_label(first))
        combined.set(
            "d", " ".join(str(item.node.path.to_absolute()) for item in ordered)
        )

        for item in ordered:
            parent.remove(item.node)
        parent.insert(insertion_index, combined)

    def effect(self):
        nodes = [node for node in self._selected_paths() if self._usable(node)]
        if len(nodes) < 2:
            raise inkex.AbortExtension(
                "Minstens twee zichtbare paden met een lijnkleur zijn nodig."
            )

        groups = defaultdict(list)
        for node in nodes:
            groups[self._group_key(node)].append(PathInfo(node))

        original_total = 0.0
        optimized_total = 0.0
        optimized_paths = 0
        combined_groups = 0

        for group_number, infos in enumerate(groups.values(), start=1):
            if len(infos) < 2:
                continue
            ordered, start = self._optimize(infos)
            original_total += self._travel(infos, start)
            optimized_total += self._travel(ordered, start)
            optimized_paths += len(ordered)

            if self.options.combine:
                self._combine(ordered, group_number)
                combined_groups += 1
            else:
                parent = ordered[0].node.getparent()
                if all(item.node.getparent() is parent for item in ordered):
                    for item in ordered:
                        parent.remove(item.node)
                        parent.append(item.node)
                for index, item in enumerate(ordered, start=1):
                    item.node.set("data-lasergrbl-volgorde", str(index))

        if optimized_paths == 0:
            raise inkex.AbortExtension(
                "Geen groep met meerdere gelijk opgemaakte paden gevonden."
            )

        saving = max(0.0, original_total - optimized_total)
        percentage = 100.0 * saving / original_total if original_total else 0.0
        inkex.errormsg(
            "LaserGRBL-route geoptimaliseerd: {} paden, {} kleurgroepen. "
            "Geschatte loze beweging: {:.1f} naar {:.1f} documenteenheden "
            "({:.1f}% korter). Gebruik Ongedaan maken om terug te gaan.".format(
                optimized_paths,
                combined_groups if self.options.combine else len(groups),
                original_total,
                optimized_total,
                percentage,
            )
        )


if __name__ == "__main__":
    LaserGRBLRouteOptimizer().run()
