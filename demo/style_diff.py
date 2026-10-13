"""Compare two demo/style_snapshot.py captures: every computed-style difference, grouped, plus screenshot pixel diffs.

usage: demo/.venv/bin/python demo/style_diff.py BEFORE_DIR AFTER_DIR [--allow-font-floor 12]
Exit 0 when nothing unexpected differs.
"""
import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

NOISE = {"-webkit-text-stroke-color", "-webkit-tap-highlight-color"}
# Box geometry follows from any text-size change, so these are reported separately, not counted as flips.
LAYOUT = {"width", "height", "inline-size", "block-size", "perspective-origin", "transform-origin", "min-width", "min-height",
          "max-width", "max-height", "top", "left", "right", "bottom", "inset-block-start", "inset-block-end", "inset-inline-start",
          "inset-inline-end", "grid-template-columns", "grid-template-rows", "flex-basis", "line-height", "border-image-width",
          "background-position", "background-size", "background-position-x", "background-position-y", "-webkit-mask-position",
          "mask-position", "mask-size", "-webkit-mask-size", "column-width", "text-indent", "offset-distance", "shape-outside", "transform"}


def load(path):
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def tiny(value):
    """Durations under a millisecond (reduced-motion 0s vs .01ms) are the same thing."""
    m = re.fullmatch(r"([\d.e+-]+)s", str(value).strip())
    try:
        return m is not None and abs(float(m.group(1))) < 0.001
    except ValueError:
        return False


def px(value):
    m = re.fullmatch(r"(\d*\.?\d+)px", str(value).strip())
    return float(m.group(1)) if m else None


def pixel_diff(a, b):
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return {"size": [ia.size, ib.size]}
    diff = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > 24 else 0)
    changed = sum(1 for v in diff.getdata() if v)
    return {"changed_pixels": changed, "share": round(changed / (ia.size[0] * ia.size[1]), 5)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--allow-font-floor", type=float, default=12)
    parser.add_argument("--out")
    args = parser.parse_args()
    before, after = Path(args.before), Path(args.after)
    report, unexpected_total = {}, 0
    for path in sorted(before.glob("*.json.gz")):
        name = path.name[:-8]
        other = after / path.name
        if not other.exists():
            report[name] = {"missing_after": True}
            continue
        a, b = load(path), load(other)
        missing = sorted(set(a) - set(b)), sorted(set(b) - set(a))
        by_prop, examples, expected = Counter(), defaultdict(list), Counter()
        for key in a.keys() & b.keys():
            pa, pb = a[key], b[key]
            for prop in pa.keys() | pb.keys():
                if prop in NOISE or prop.startswith("--walk-"):
                    continue
                va, vb = pa.get(prop), pb.get(prop)
                if va == vb or (prop.endswith("-duration") and tiny(va) and tiny(vb)):
                    continue
                if prop == "font-size" and px(va) is not None and px(vb) is not None and px(va) < args.allow_font_floor and px(va) < px(vb) <= args.allow_font_floor:
                    expected["font_floor"] += 1  # lifted to the floor, or an em-sized child of a lifted parent
                    continue
                if prop in LAYOUT:
                    expected["layout"] += 1
                    continue
                if prop.startswith("margin-") and px(va) not in (None, 0.0) and px(vb) not in (None, 0.0):
                    expected["layout"] += 1  # a resolved `auto` or percentage margin moving with its neighbours
                    continue
                by_prop[prop] += 1
                if len(examples[prop]) < 400:
                    examples[prop].append({"element": key.split("|", 1)[1][:120], "element_key": key, "before": str(va)[:80], "after": str(vb)[:80]})
        unexpected = sum(by_prop.values())
        unexpected_total += unexpected + len(missing[0]) + len(missing[1])
        report[name] = {"unexpected": unexpected, "expected": dict(expected), "by_property": dict(by_prop.most_common(25)),
                        "examples": dict(examples), "elements_only_before": missing[0][:10], "elements_only_after": missing[1][:10],
                        "pixels": pixel_diff(before / f"{name}.png", after / f"{name}.png") if (after / f"{name}.png").exists() else None}
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1))
    for name, item in report.items():
        line = f"{name:22s} unexpected={item.get('unexpected', '?'):>5}  expected={item.get('expected')}  pixels={item.get('pixels')}"
        if item.get("elements_only_before") or item.get("elements_only_after"):
            line += f"  only-before={len(item['elements_only_before'])} only-after={len(item['elements_only_after'])}"
        print(line)
    print("TOTAL unexpected", unexpected_total)
    raise SystemExit(0 if unexpected_total == 0 else 1)


main()
