#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from greg_security import resolve_under_root


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_NODE = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"
SETUP_ARTIFACT_WORKSPACE = (
    Path.home()
    / ".codex"
    / "plugins"
    / "cache"
    / "openai-primary-runtime"
    / "presentations"
    / "26.805.11740"
    / "skills"
    / "presentations"
    / "container_tools"
    / "setup_artifact_tool_workspace.mjs"
)
RENDERER_SOURCE = ROOT / "workspace" / "renderers" / "deck" / "greg-buildstak-deck-renderer.mjs"
SPEC_CHECK_SOURCE = ROOT / "tools" / "greg_artifact_spec_check.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_spec(spec_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("greg_artifact_spec_check", SPEC_CHECK_SOURCE)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load artifact spec checker: {SPEC_CHECK_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["greg_artifact_spec_check"] = module
    spec.loader.exec_module(module)
    data = module.run_checks(spec_path, "deck")
    if not data["passed"]:
        failures = [item for item in data["findings"] if item["status"] == "fail"]
        raise RuntimeError(f"Deck spec failed validation: {failures}")


def run_folder_from_spec(spec: dict[str, Any]) -> Path:
    run_folder = spec.get("run_folder")
    if not run_folder:
        raise ValueError("Deck spec is missing `run_folder`.")
    return resolve_under_root(str(run_folder))


def workspace_for_spec(spec_path: Path, spec: dict[str, Any]) -> Path:
    run_folder = run_folder_from_spec(spec)
    explicit = spec.get("renderer_workspace")
    if explicit:
        return resolve_under_root(str(explicit))
    return run_folder / "deck" / "tmp"


def node_path() -> Path:
    if BUNDLED_NODE.exists():
        return BUNDLED_NODE
    return Path("node")


def setup_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    if SETUP_ARTIFACT_WORKSPACE.exists():
        subprocess.run(
            [str(node_path()), str(SETUP_ARTIFACT_WORKSPACE), "--workspace", str(workspace)],
            cwd=ROOT,
            check=True,
        )
    else:
        (workspace / "package.json").write_text('{"private":true,"type":"module"}\n', encoding="utf-8")
    bundled_node_modules = BUNDLED_NODE.parent.parent / "node_modules"
    workspace_node_modules = workspace / "node_modules"
    if bundled_node_modules.exists() and not workspace_node_modules.exists():
        try:
            workspace_node_modules.symlink_to(bundled_node_modules, target_is_directory=True)
        except OSError:
            pass


def copy_renderer(workspace: Path) -> Path:
    if not RENDERER_SOURCE.exists():
        raise FileNotFoundError(f"Reusable renderer not found: {RENDERER_SOURCE}")
    target = workspace / RENDERER_SOURCE.name
    shutil.copy2(RENDERER_SOURCE, target)
    return target


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def slide_text_parts(slide: dict[str, Any]) -> list[str]:
    parts = [text_of(slide.get("title")), text_of(slide.get("subtitle")), text_of(slide.get("intro"))]
    if slide.get("topics"):
        parts.append("Main topics covered")
        parts.extend(text_of(item) for item in slide.get("topics", [])[:5])
    if slide.get("bullets"):
        parts.extend(text_of(item) for item in slide.get("bullets", [])[:5])
    for key in ("items",):
        for item in slide.get(key, [])[:6]:
            if isinstance(item, dict):
                parts.extend([text_of(item.get("title")), text_of(item.get("body"))])
    for key in ("left", "right"):
        item = slide.get(key)
        if isinstance(item, dict):
            parts.extend([text_of(item.get("title")), text_of(item.get("body"))])
    parts.extend([text_of(slide.get("body")), text_of(slide.get("bottom_line")), text_of(slide.get("takeaway")), text_of(slide.get("final_line"))])
    return [part.strip() for part in parts if part and part.strip()]


def px(value: float) -> int:
    return int(round(value * 9525))


def xml_text_runs(text: str, size: int = 2200, bold: bool = False) -> str:
    escaped_lines = [html.escape(line) for line in text.splitlines() if line.strip()]
    if not escaped_lines:
        escaped_lines = [""]
    paragraphs = []
    bold_attr = ' b="1"' if bold else ""
    for line in escaped_lines:
        paragraphs.append(
            f'<a:p><a:r><a:rPr lang="en-US" sz="{size}"{bold_attr}/><a:t>{line}</a:t></a:r></a:p>'
        )
    return "".join(paragraphs)


def textbox(shape_id: int, name: str, x: float, y: float, w: float, h: float, text: str, *, size: int = 2200, bold: bool = False) -> str:
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{shape_id}" name="{html.escape(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="{px(x)}" y="{px(y)}"/><a:ext cx="{px(w)}" cy="{px(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr wrap="square" anchor="t"/><a:lstStyle/>{xml_text_runs(text, size=size, bold=bold)}</p:txBody>
      </p:sp>
    """


def rect(shape_id: int, name: str, x: float, y: float, w: float, h: float, fill: str = "F5F7FA") -> str:
    return f"""
      <p:sp>
        <p:nvSpPr><p:cNvPr id="{shape_id}" name="{html.escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="{px(x)}" y="{px(y)}"/><a:ext cx="{px(w)}" cy="{px(h)}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill><a:ln><a:solidFill><a:srgbClr val="CBD3DF"/></a:solidFill></a:ln></p:spPr>
      </p:sp>
    """


def slide_xml(slide: dict[str, Any], index: int, course_title: str) -> str:
    parts = slide_text_parts(slide)
    title = parts[0] if parts else f"Slide {index}"
    body = "\n".join(parts[1:9])
    shapes = [
        textbox(2, "eyebrow", 50, 32, 200, 28, f"LESSON {index if index == 1 else ''}".strip(), size=1200, bold=True),
        textbox(3, "title", 50, 68, 1100, 110, title, size=3000, bold=True),
    ]
    if index == 1:
        shapes.append(rect(4, "cover-panel", 50, 205, 560, 350, "FFF3EA"))
        shapes.append(textbox(5, "main-topics", 85, 235, 500, 300, body or "Main topics covered", size=1800, bold=False))
    elif slide.get("layout") in {"card_sequence", "checklist_rows", "row_list"}:
        for item_index, text in enumerate(parts[1:5], start=0):
            x = 70 + item_index * 285
            shapes.append(rect(10 + item_index, f"card-{item_index + 1}", x, 235, 235, 145))
            shapes.append(textbox(20 + item_index, f"card-text-{item_index + 1}", x + 18, 260, 200, 90, text, size=1500, bold=item_index == 0))
        shapes.append(textbox(40, "bottom-line", 130, 525, 1020, 60, text_of(slide.get("bottom_line") or slide.get("takeaway") or ""), size=1800, bold=True))
    elif slide.get("layout") == "comparison":
        shapes.append(rect(10, "left-panel", 80, 225, 500, 260))
        shapes.append(rect(11, "right-panel", 700, 225, 500, 260, "FFF3EA"))
        shapes.append(textbox(20, "left-text", 115, 255, 430, 190, "\n".join(parts[2:4]), size=1700, bold=False))
        shapes.append(textbox(21, "right-text", 735, 255, 430, 190, "\n".join(parts[4:6]), size=1700, bold=False))
        shapes.append(textbox(40, "bottom-line", 130, 525, 1020, 60, text_of(slide.get("bottom_line")), size=1800, bold=True))
    else:
        shapes.append(rect(10, "body-panel", 85, 210, 1110, 360))
        shapes.append(textbox(20, "body", 120, 245, 1040, 280, body, size=1800, bold=False))
    shapes.append(textbox(90, "footer-course", 82, 670, 520, 28, course_title, size=1050))
    shapes.append(textbox(91, "footer-number", 1180, 670, 45, 28, f"{index:02d}", size=1050))
    shape_xml = "\n".join(shapes)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>{shape_xml}</p:spTree></p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def write_inspect(deck_path: Path, spec: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    layout_dir = deck_path.parent / f"rendered_slides_lesson_{int(spec.get('lesson_number', 1)):02d}"
    layout_dir.mkdir(parents=True, exist_ok=True)
    for index, slide in enumerate(spec.get("slides") or [], start=1):
        rows.append({"kind": "slide", "slide": index})
        parts = slide_text_parts(slide)
        rows.append({"kind": "textbox", "slide": index, "name": "title", "text": parts[0] if parts else "", "bbox": [50, 68, 1100, 110]})
        rows.append({"kind": "textbox", "slide": index, "name": "body", "text": "\n".join(parts[1:]), "bbox": [120, 245, 1040, 280]})
        rows.append({"kind": "shape", "slide": index, "name": "body-panel", "bbox": [85, 210, 1110, 360]})
        rows.append({"kind": "textbox", "slide": index, "name": "footer-course", "text": spec.get("course_title", ""), "bbox": [82, 670, 520, 28]})
        rows.append({"kind": "textbox", "slide": index, "name": "footer-number", "text": f"{index:02d}", "bbox": [1180, 670, 45, 28]})
        (layout_dir / f"slide-{index:02d}.layout.json").write_text(
            json.dumps({"slide": {"slide": index}, "elements": [row for row in rows if row.get("slide") == index]}, indent=2),
            encoding="utf-8",
        )
    deck_path.with_suffix(deck_path.suffix + ".inspect.ndjson").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def render_fallback_pptx(spec_path: Path, spec: dict[str, Any]) -> Path:
    run_folder = run_folder_from_spec(spec)
    output = run_folder / spec["output"]["pptx"]
    output.parent.mkdir(parents=True, exist_ok=True)
    slides = spec.get("slides") or []
    slide_count = len(slides)
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
    ]
    content_types.extend(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, slide_count + 1)
    )
    content_types.append("</Types>")
    slide_ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, slide_count + 1))
    pres_rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, slide_count + 1)
    )
    pres_rels += f'<Relationship Id="rId{slide_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "\n".join(content_types))
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>""")
        zf.writestr("ppt/presentation.xml", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId{slide_count + 1}"/></p:sldMasterIdLst><p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="wide"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>""")
        zf.writestr("ppt/_rels/presentation.xml.rels", f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{pres_rels}</Relationships>""")
        zf.writestr("ppt/slideMasters/slideMaster1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>""")
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>""")
        zf.writestr("ppt/slideLayouts/slideLayout1.xml", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld></p:sldLayout>""")
        for i, slide in enumerate(slides, start=1):
            zf.writestr(f"ppt/slides/slide{i}.xml", slide_xml(slide, i, spec.get("course_title", "")))
            zf.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>""")
    write_inspect(output, spec)
    return output


def render(spec_path: Path, skip_setup: bool = False) -> Path:
    spec_path = resolve_under_root(spec_path)
    validate_spec(spec_path)
    spec = read_json(spec_path)
    workspace = workspace_for_spec(spec_path, spec)
    if not skip_setup:
        setup_workspace(workspace)
    renderer = copy_renderer(workspace)
    try:
        subprocess.run(
            [str(node_path()), str(renderer), "--spec", str(spec_path)],
            cwd=ROOT,
            check=True,
        )
        return run_folder_from_spec(spec) / spec["output"]["pptx"]
    except subprocess.CalledProcessError:
        return render_fallback_pptx(spec_path, spec)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Prof Greg BuildStak deck from a JSON deck spec.")
    parser.add_argument("spec", help="Path to deck spec JSON.")
    parser.add_argument("--skip-setup", action="store_true", help="Skip artifact-tool workspace setup and only copy/run renderer.")
    args = parser.parse_args()

    output = render(Path(args.spec), skip_setup=args.skip_setup)
    print(f"Rendered deck: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
