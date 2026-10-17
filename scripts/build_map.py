"""Convert the state boundary topology into plain GeoJSON for the site.

    python scripts/build_map.py

The site has no build step and no bundler, so every dependency it takes is a
script tag. Decoding TopoJSON in the browser would cost one more; decoding it
here costs nothing at run time and ships a file d3.geoPath can draw directly.

Also writes the code aliases the map needs: the boundary file and the budget
data disagree on three codes, because there is no single official two-letter
list and both are defensible.

Boundaries come from the sibling Lok Sabha delimitation project, simplified
from the Survey of India state boundaries. They are for reading a choropleth,
not for any question about where a border actually runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as c  # noqa: E402

SRC = c.ROOT / "data" / "india-states.topo.json"
DEST = c.ROOT / "data" / "india-states.geo.json"

# The budget data keys Odisha, Telangana and Uttarakhand one way and the
# boundary file another. Neither is wrong; this maps boundary -> budget.
GEO_TO_BUDGET = {
    "OD": "OR",
    "TS": "TG",
    "UK": "UT",
}


def decode_arcs(topology):
    """TopoJSON stores arcs as quantised deltas; turn them into coordinates."""
    transform = topology.get("transform")
    out = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            if transform:
                sx, sy = transform["scale"]
                tx, ty = transform["translate"]
                points.append([x * sx + tx, y * sy + ty])
            else:
                points.append([x, y])
        out.append(points)
    return out


def ring(arc_indices, arcs):
    """Stitch a ring together from its arc indices; a negative index is a
    reversed arc, and the shared endpoint is dropped where arcs join."""
    coords = []
    for idx in arc_indices:
        if idx < 0:
            part = arcs[~idx][::-1]
        else:
            part = arcs[idx]
        if coords:
            coords.extend(part[1:])
        else:
            coords.extend(part)
    return coords


def geometry(geom, arcs):
    kind = geom.get("type")
    if kind == "Polygon":
        return {"type": "Polygon",
                "coordinates": [ring(r, arcs) for r in geom["arcs"]]}
    if kind == "MultiPolygon":
        return {"type": "MultiPolygon",
                "coordinates": [[ring(r, arcs) for r in poly]
                                for poly in geom["arcs"]]}
    return None


def main() -> None:
    if not SRC.exists():
        raise SystemExit("missing %s" % SRC)
    topology = c.read_json(SRC)
    arcs = decode_arcs(topology)

    layer = topology["objects"].get("states")
    if not layer:
        raise SystemExit("no 'states' object in the topology")

    features = []
    for geom in layer["geometries"]:
        shape = geometry(geom, arcs)
        if shape is None:
            continue
        props = dict(geom.get("properties") or {})
        geo_code = props.get("code", "")
        props["geo_code"] = geo_code
        props["code"] = GEO_TO_BUDGET.get(geo_code, geo_code)
        features.append({"type": "Feature", "properties": props,
                         "geometry": shape})

    if len(features) < 30:
        raise SystemExit("only %d features decoded; expected 36" % len(features))

    # Sanity: the decoded coordinates must land inside India's bounding box.
    xs = []
    ys = []
    for f in features:
        polys = (f["geometry"]["coordinates"]
                 if f["geometry"]["type"] == "MultiPolygon"
                 else [f["geometry"]["coordinates"]])
        for poly in polys:
            for r in poly:
                for x, y in r:
                    xs.append(x)
                    ys.append(y)
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    if not (66 < bbox[0] < 80 and 5 < bbox[1] < 15
            and 90 < bbox[2] < 100 and 30 < bbox[3] < 40):
        raise SystemExit("decoded bounding box looks wrong: %s" % bbox)

    c.write_json({"type": "FeatureCollection", "features": features}, DEST,
                 indent=0)
    print("%d states, bbox %.2f,%.2f .. %.2f,%.2f"
          % (len(features), bbox[0], bbox[1], bbox[2], bbox[3]))

    # Report which budget entities will have no shape to colour.
    states = c.read_json(c.ROOT / "data" / "states.json")
    have = {f["properties"]["code"] for f in features}
    want = {e["code"] for e in states["states"] if e["kind"] != "aggregate"}
    missing = sorted(want - have)
    extra = sorted(have - want)
    print("budget entities without a shape: %s" % (missing or "none"))
    print("shapes without budget data: %s" % (extra or "none"))
    if missing:
        raise SystemExit("every budget entity needs a shape; fix GEO_TO_BUDGET")


if __name__ == "__main__":
    main()
