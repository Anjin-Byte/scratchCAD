import math
import sys
from typing import Dict, Iterable, List, Optional, Tuple

SQ_IN_PER_SQ_FT = 144

SCALE_IN_PER_PT = 629 / 799  # ≈ 0.7471839799749687
SCALE_PT_PER_IN = 1 / SCALE_IN_PER_PT
SCALE_PT_PER_FT = 12 * SCALE_PT_PER_IN


def pts_to_ft_in(pts: float, round_to_frac: int = 16):
    inches = pts * SCALE_IN_PER_PT
    ft = int(inches // 12)
    in_rem = inches - ft * 12

    step = 1 / round_to_frac
    in_rem = round(in_rem / step) * step
    if in_rem >= 12:
        ft += 1
        in_rem -= 12
    return ft, in_rem


def ft_in_to_pts(feet: int = 0, inches: float = 0.0):
    return (feet * 12 + inches) * SCALE_PT_PER_IN


def convert_sq_in_to_ft_in(square_inches: float) -> Tuple[int, float]:
    sq_ft = int(square_inches // SQ_IN_PER_SQ_FT)
    rem_in = square_inches % SQ_IN_PER_SQ_FT
    return sq_ft, rem_in


class Opening:
    def __init__(self, width_in: float, height_in: float):
        self.width_in = width_in
        self.height_in = height_in

    def area_sq_in(self) -> float:
        return self.width_in * self.height_in


def panels_needed_for_area_sq_in(
    total_area_sq_in: float, panel_sq_ft: float, waste_pct: float = 0.0
) -> int:
    if panel_sq_ft <= 0:
        raise ValueError("panel_sq_ft must be > 0")

    total_sq_ft = max(0.0, total_area_sq_in) / SQ_IN_PER_SQ_FT
    total_sq_ft *= 1.0 + waste_pct
    return math.ceil(total_sq_ft / panel_sq_ft)


class RectSection:
    def __init__(self, width_in: float, height_in: float):
        self.width_in = width_in
        self.height_in = height_in

    def area_sq_in(self) -> float:
        return self.width_in * self.height_in


class TriSection:
    def __init__(self, base_in: float, pitch_rise: float, pitch_run: float = 12.0):
        if base_in < 0:
            raise ValueError("base_in must be ≥ 0")
        self.base_in = float(base_in)
        self.pitch_rise = float(pitch_rise)
        self.pitch_run = float(pitch_run)

    @property
    def pitch(self) -> float:
        return self.pitch_rise / self.pitch_run

    def area_sq_in(self) -> float:
        h = (self.base_in / 2.0) * self.pitch
        return 0.5 * self.base_in * h

    def equivalent_difference(self, inner: "TriSection") -> "TriSection":
        if not math.isclose(self.pitch, inner.pitch, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("Pitches must match to subtract as a single triangle.")
        if inner.base_in > self.base_in:
            raise ValueError("Inner base must be ≤ outer base.")
        b_eq = math.sqrt(self.base_in**2 - inner.base_in**2)
        return TriSection(b_eq, self.pitch_rise, self.pitch_run)

    def __sub__(self, other: "TriSection") -> "TriSection":
        return self.equivalent_difference(other)


class Wall:
    def __init__(self):
        self.sections: List[TriSection | RectSection] = []
        self.openings: List[Opening] = []

    def add_section(self, section):
        self.sections.append(section)

    def add_opening(self, opening: Opening):
        self.openings.append(opening)

    def section_area_sq_in(self) -> float:
        return sum(s.area_sq_in() for s in self.sections)

    def opening_area_sq_in(self) -> float:
        return sum(o.area_sq_in() for o in self.openings)

    def siding_area_sq_in(self) -> float:
        return self.section_area_sq_in() - self.opening_area_sq_in()

    def siding_area_ft_in(self) -> Tuple[int, float]:
        return convert_sq_in_to_ft_in(self.siding_area_sq_in())

    def panels_needed(self, panel_sq_ft: float, waste_pct: float = 0.0) -> int:
        return panels_needed_for_area_sq_in(
            self.siding_area_sq_in(), panel_sq_ft, waste_pct
        )


# ---- optional: normalize common direction labels ----
_DIR_MAP = {
    "n": "north",
    "north": "north",
    "s": "south",
    "south": "south",
    "e": "east",
    "east": "east",
    "w": "west",
    "west": "west",
    "front": "front",
    "back": "back",
    "left": "left",
    "right": "right",
}


def normalize_direction(label: str) -> str:
    key = (label or "").strip().lower()
    return _DIR_MAP.get(key, key)  # fall back to the given text


# ---- wrapper that associates a Wall with a direction label ----
class OrientedWall:
    def __init__(self, wall: "Wall", direction: str):
        self.wall = wall
        self.direction = normalize_direction(direction)

    def siding_area_sq_in(self) -> float:
        # Clamp to 0 to avoid negative area if openings > sections by mistake
        return max(0.0, self.wall.siding_area_sq_in())


# ---- the container itself ----
class WallContainer:
    def __init__(self):
        self._walls: List[OrientedWall] = []

    def add_wall(self, wall: "Wall", direction: str) -> None:
        """Add a wall with a direction label (e.g., 'back', 'north')."""
        self._walls.append(OrientedWall(wall, direction))

    def total_siding_area_sq_in(
        self, directions: Optional[Iterable[str]] = None
    ) -> float:
        """
        Sum siding areas (sections minus openings) for all walls whose
        direction is in `directions`. If `directions` is None, include all.
        """
        if directions is None:
            dirs = None
        else:
            dirs = {normalize_direction(d) for d in directions}

        total = 0.0
        for ow in self._walls:
            if dirs is None or ow.direction in dirs:
                total += ow.siding_area_sq_in()
        return total

    def total_siding_area_ft_in(
        self, directions: Optional[Iterable[str]] = None
    ) -> Tuple[int, float]:
        """Return (sq_ft, leftover_sq_in) for the selected directions."""
        area_si = self.total_siding_area_sq_in(directions)
        return convert_sq_in_to_ft_in(area_si)

    def breakdown_by_direction(self) -> Dict[str, float]:
        """Return {direction: area_in_square_inches} for all stored walls."""
        out: Dict[str, float] = {}
        for ow in self._walls:
            out[ow.direction] = out.get(ow.direction, 0.0) + ow.siding_area_sq_in()
        return out

    def breakdown_by_direction_ft_in(self) -> Dict[str, Tuple[int, float]]:
        """Return {direction: (sq_ft, leftover_sq_in)}."""
        si = self.breakdown_by_direction()
        return {k: convert_sq_in_to_ft_in(v) for k, v in si.items()}


def main():
    wall = Wall()
    wall.add_section(RectSection(12 * 12, 8 * 12))
    # wall.add_section(TriangularSection(base_in=12*12, pitch_rise=6, pitch_run=12))
    wall.add_opening(Opening(35, 59))

    ft, sq_in = wall.siding_area_ft_in()
    print(f"Siding required: {ft} sq ft {sq_in:.0f} sq in")

    print(pts_to_ft_in(689))

    outer = TriSection(322.4, 6, 12)
    inner = TriSection(213.6, 6, 12)
    net = outer - inner  # TriSection with same pitch

    print(
        f"inner: {inner.area_sq_in()}, outer: {outer.area_sq_in()}, diff: {net.area_sq_in()}"
    )

    # Build two walls that face the "back" and one that faces "right"


    w_back1 = Wall()
    w_back1.add_section(RectSection(12 * 12, 8 * 12))  # 12' x 8'
    w_back1.add_opening(Opening(35, 59))

    w_back2 = Wall()
    w_back2.add_section(TriSection(base_in=12 * 12, pitch_rise=6, pitch_run=12))  # gable

    w_right = Wall()
    w_right.add_section(RectSection(10 * 12, 8 * 12))  # 10' x 8'
    w_right.add_opening(Opening(36, 80))  # door

    container = WallContainer()
    container.add_wall(w_back1, "back")
    container.add_wall(w_back2, "back")
    container.add_wall(w_right, "right")

    # Totals for the back of the house
    ft, sqin = container.total_siding_area_ft_in(directions=["back"])
    print(f"Back total: {ft} sq ft {sqin:.0f} sq in")

    # All directions
    ft_all, sqin_all = container.total_siding_area_ft_in()
    print(f"All walls total: {ft_all} sq ft {sqin_all:.0f} sq in")

    # Breakdown per direction
    for dir_label, (ft_d, si_d) in container.breakdown_by_direction_ft_in().items():
        print(f"{dir_label.capitalize()}: {ft_d} sq ft {si_d:.0f} sq in")


if __name__ == "__main__":
    rc = 1
    try:
        main()
        rc = 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    sys.exit(rc)
