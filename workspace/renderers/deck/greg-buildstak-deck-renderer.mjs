import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const C = {
  navy: "#1f3a5f",
  orange: "#f97316",
  ink: "#172033",
  gray: "#3f4652",
  slate: "#475569",
  muted: "#8A8A8A",
  light: "#F5F7FA",
  paleOrange: "#FFF3EA",
  white: "#FFFFFF",
  line: "#CBD3DF",
  softBlue: "#EEF4FA",
};

const inspectRows = [];
let currentSlide = 0;
let currentSpec = null;
const ROOT = process.cwd();

function localizedLabels() {
  if (currentSpec?.locale === "pt_br") {
    return { lesson: "LIÇÃO", topics: "Principais tópicos abordados", takeaway: "CONCLUSÃO DA LIÇÃO" };
  }
  if (currentSpec?.locale === "es") {
    return { lesson: "LECCIÓN", topics: "Temas principales", takeaway: "CONCLUSIÓN DE LA LECCIÓN" };
  }
  return { lesson: "LESSON", topics: "Main topics covered", takeaway: "LESSON TAKEAWAY" };
}

function assertInsideRoot(resolvedPath, originalValue) {
  const relative = path.relative(ROOT, resolvedPath);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return resolvedPath;
  }
  throw new Error(`Path escapes Prof Greg workspace: ${originalValue}`);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--spec") {
      args.spec = argv[i + 1];
      i += 1;
    }
  }
  if (!args.spec) {
    throw new Error("Missing --spec path.");
  }
  return args;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf-8"));
}

function rootPath(relativeOrAbsolute) {
  if (!relativeOrAbsolute) return "";
  const resolved = path.isAbsolute(relativeOrAbsolute)
    ? relativeOrAbsolute
    : path.resolve(process.cwd(), relativeOrAbsolute);
  return assertInsideRoot(resolved, relativeOrAbsolute);
}

function runPath(relativeOrAbsolute) {
  if (!relativeOrAbsolute) return "";
  const resolved = path.isAbsolute(relativeOrAbsolute)
    ? relativeOrAbsolute
    : path.resolve(process.cwd(), currentSpec.run_folder, relativeOrAbsolute);
  return assertInsideRoot(resolved, relativeOrAbsolute);
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function readImageBlob(filePath) {
  const bytes = await fs.readFile(filePath);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function bbox(x, y, w, h) {
  return [x, y, w, h];
}

function log(kind, data) {
  inspectRows.push({ kind, ...data });
}

function addSlide(deck, title = "") {
  const slide = deck.slides.add();
  slide.background.fill = C.white;
  currentSlide += 1;
  log("slide", { slide: currentSlide, title: title || `Slide ${currentSlide}`, textShapes: 0 });
  return slide;
}

function addShape(slide, name, geometry, x, y, w, h, fill = C.white, line = C.line, width = 1) {
  const shape = slide.shapes.add({
    geometry,
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width },
  });
  log("shape", { slide: currentSlide, name, bbox: bbox(x, y, w, h) });
  return shape;
}

function addText(slide, name, text, x, y, w, h, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontFace: "Arial",
    fontSize: style.fontSize ?? 22,
    bold: style.bold ?? false,
    italic: style.italic ?? false,
    color: style.color ?? C.gray,
    alignment: style.alignment ?? "left",
  };
  log("textbox", {
    slide: currentSlide,
    name,
    text,
    textPreview: String(text).replace(/\n/g, " ").slice(0, 120),
    textChars: String(text).length,
    textLines: String(text).split("\n").length,
    bbox: bbox(x, y, w, h),
  });
  return shape;
}

async function addImage(slide, name, imagePath, x, y, w, h, alt, fit = "cover") {
  const imageBytes = await readImageBlob(imagePath);
  slide.images.add({
    blob: imageBytes,
    contentType: "image/png",
    alt,
    fit,
    position: { left: x, top: y, width: w, height: h },
  });
  log("image", { slide: currentSlide, name, alt, bbox: bbox(x, y, w, h) });
}

function addLine(slide, name, x1, y1, x2, y2, color = C.orange, width = 3) {
  slide.shapes.add({
    geometry: "line",
    name,
    position: { left: x1, top: y1, width: x2 - x1, height: y2 - y1 },
    fill: "none",
    line: { style: "solid", fill: color, width, endArrowType: "triangle" },
  });
  log("shape", { slide: currentSlide, name, bbox: bbox(x1, y1, x2 - x1, y2 - y1) });
}

async function addFooter(slide, n, startX = 68) {
  const icon = rootPath(currentSpec.assets.brand_icon);
  try {
    await addImage(slide, "brand-icon", icon, startX, 664, 26, 26, "BuildStak icon", "contain");
  } catch {}
  addText(slide, "footer-course", currentSpec.course_title, startX + 40, 668, 520, 22, {
    fontSize: 13,
    color: C.slate,
  });
  addText(slide, "footer-number", String(n).padStart(2, "0"), 1164, 668, 46, 22, {
    fontSize: 13,
    color: C.muted,
    alignment: "right",
  });
}

function addEyebrow(slide) {
  addText(slide, "eyebrow", `${localizedLabels().lesson} ${currentSpec.lesson_number}`, 72, 44, 300, 26, {
    fontSize: 16,
    bold: true,
    color: C.orange,
  });
}

async function addChrome(slide, n) {
  addEyebrow(slide);
  await addFooter(slide, n);
}

function addTitle(slide, title, subtitle = "") {
  addText(slide, "slide-title", title, 72, 82, 1030, 94, {
    fontSize: 37,
    bold: true,
    color: C.navy,
  });
  if (subtitle) {
    addText(slide, "slide-subtitle", subtitle, 74, 168, 980, 52, {
      fontSize: 21,
      color: C.gray,
    });
  }
}

function addBullet(slide, text, x, y, w, idx, size = 22) {
  addText(slide, `bullet-dot-${idx}`, "-", x, y, 24, 30, {
    fontSize: size + 1,
    bold: true,
    color: C.orange,
  });
  addText(slide, `bullet-${idx}`, text, x + 34, y, w - 34, 58, {
    fontSize: size,
    color: C.gray,
  });
}

function card(slide, key, title, body, x, y, w, h, accent = C.navy, fill = C.white) {
  const compact = w < 300;
  const titleHeight = compact ? 48 : 34;
  const bodyTop = compact ? 76 : 72;
  addShape(slide, `${key}-card`, "roundRect", x, y, w, h, fill, C.line, 1.4);
  addText(slide, `${key}-title`, title, x + 20, y + 18, w - 40, titleHeight, {
    fontSize: compact ? 18 : 21,
    bold: true,
    color: accent,
    alignment: "center",
  });
  addText(slide, `${key}-body`, body, x + 22, y + bodyTop, w - 44, h - bodyTop - 14, {
    fontSize: compact ? 14 : 18,
    color: C.gray,
    alignment: "center",
  });
}

async function renderCover(deck, slideSpec) {
  const slide = addSlide(deck, "BuildStak");
  addShape(slide, "left-navy", "rect", 0, 0, 150, 720, C.navy, C.navy, 0);
  addShape(slide, "orange-rule", "rect", 150, 0, 8, 720, C.orange, C.orange, 0);
  try {
    await addImage(
      slide,
      "brand-negative",
      rootPath(currentSpec.assets.negative_wordmark),
      24,
      46,
      104,
      104,
      "BuildStak negative wordmark",
      "contain"
    );
  } catch {}
  addText(slide, "course", currentSpec.course_title, 218, 88, 830, 64, {
    fontSize: 22,
    color: C.slate,
  });
  addText(slide, "lesson", `${localizedLabels().lesson} ${currentSpec.lesson_number}`, 218, 156, 220, 28, {
    fontSize: 18,
    bold: true,
    color: C.orange,
  });
  addText(slide, "title", slideSpec.title, 218, 198, 900, 132, {
    fontSize: 42,
    bold: true,
    color: C.navy,
  });
  addText(slide, "subtitle", slideSpec.subtitle, 220, 338, 900, 58, {
    fontSize: 24,
    bold: true,
    color: C.ink,
  });
  addText(slide, "topics", localizedLabels().topics, 222, 410, 620, 32, {
    fontSize: 21,
    bold: true,
    color: C.navy,
  });
  slideSpec.topics.forEach((item, idx) => addBullet(slide, item, 222, 454 + idx * 43, 850, idx + 1, 19));
  await addFooter(slide, currentSlide, 198);
}

async function renderImageBullets(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const image = slideSpec.image || {};
  const imagePath = runPath(image.path);
  const imageLeft = slideSpec.image_side === "left";
  const textX = imageLeft ? 650 : 72;
  const textW = 558;
  const imageX = imageLeft ? 72 : 668;
  const imageW = 540;
  const imageH = 330;
  const imageY = 236;

  if (imageLeft) {
    await addImage(slide, image.name || "teaching-image", imagePath, imageX, imageY, imageW, imageH, image.alt, "cover");
  }

  addText(slide, "intro", slideSpec.intro, textX, 236, textW, 76, {
    fontSize: 22,
    color: C.gray,
  });
  (slideSpec.bullets || []).forEach((item, idx) => {
    addBullet(slide, item, textX, 338 + idx * 62, textW, idx + 1, 21);
  });
  if (slideSpec.bottom_line) {
    addText(slide, "bottom-line", slideSpec.bottom_line, textX, 548, textW, 42, { fontSize: 23, bold: true, color: C.navy });
  }
  if (!imageLeft) {
    await addImage(slide, image.name || "teaching-image", imagePath, imageX, imageY, imageW, imageH, image.alt, "cover");
  }
}

async function renderIntroImageBullets(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const imageLeft = slideSpec.image_side === "left";
  const textX = imageLeft ? 650 : 72;
  const imageX = imageLeft ? 72 : 668;
  addText(slide, "intro", slideSpec.intro, textX, 236, 558, 76, { fontSize: 22, color: C.gray });
  (slideSpec.bullets || []).forEach((item, idx) => addBullet(slide, item, textX, 338 + idx * 66, 558, idx + 1, 21));
  await addImage(
    slide,
    slideSpec.image.name || "teaching-image",
    runPath(slideSpec.image.path),
    imageX,
    236,
    540,
    330,
    slideSpec.image.alt,
    "cover"
  );
}

async function renderCardSequence(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const x0 = 70;
  const w = 260;
  slideSpec.items.forEach((item, i) => {
    const x = x0 + i * 282;
    card(slide, `${slideSpec.key || "sequence"}-${i + 1}`, item.title, item.body, x, 270, w, 230, C.navy, C.light);
    if (i < slideSpec.items.length - 1) addLine(slide, `${slideSpec.key || "sequence"}-arrow-${i + 1}`, x + w, 385, x + 282, 385);
  });
  addText(slide, "takeaway", slideSpec.takeaway, 150, 528, 980, 58, {
    fontSize: 22,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderComparison(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  card(slide, "weak", slideSpec.left.title, slideSpec.left.body, 122, 270, 430, 210, C.gray, C.light);
  card(slide, "strong", slideSpec.right.title, slideSpec.right.body, 728, 270, 430, 210, C.navy, C.softBlue);
  addLine(slide, "compare-arrow", 574, 376, 706, 376, C.orange, 4);
  addText(slide, "bottom-line", slideSpec.bottom_line, 154, 540, 972, 42, {
    fontSize: 24,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderPlannedActual(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  addShape(slide, "planned-lane", "roundRect", 106, 268, 458, 178, C.light, C.line, 1.4);
  addShape(slide, "actual-lane", "roundRect", 716, 268, 458, 178, C.light, C.line, 1.4);
  addText(slide, "planned-title", slideSpec.left.title, 138, 294, 386, 34, { fontSize: 24, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "planned-body", slideSpec.left.body, 146, 346, 370, 70, { fontSize: 21, color: C.gray, alignment: "center" });
  addText(slide, "actual-title", slideSpec.right.title, 748, 294, 386, 34, { fontSize: 24, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "actual-body", slideSpec.right.body, 756, 346, 370, 70, { fontSize: 21, color: C.gray, alignment: "center" });
  addLine(slide, "variance-arrow", 586, 357, 694, 357, C.orange, 4);
  addText(slide, "variance-label", slideSpec.bridge_label || "Variance", 582, 300, 116, 30, { fontSize: 20, bold: true, color: C.orange, alignment: "center" });
  addText(slide, "bottom-line", slideSpec.bottom_line, 168, 532, 944, 54, {
    fontSize: 24,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderRowList(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  slideSpec.items.forEach((item, i) => {
    const yy = 236 + i * 72;
    addShape(slide, `row-${i + 1}-bar`, "roundRect", 104, yy, 1068, 52, i % 2 === 0 ? C.light : C.white, C.line, 1);
    addText(slide, `row-${i + 1}-title`, item.title, 128, yy + 12, 260, 26, { fontSize: 20, bold: true, color: C.navy });
    addText(slide, `row-${i + 1}-body`, item.body, 432, yy + 12, 704, 26, { fontSize: 19, color: C.gray });
  });
  addText(slide, "bottom-line", slideSpec.bottom_line, 164, 614, 952, 34, {
    fontSize: 23,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderChecklistRows(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  slideSpec.items.forEach((item, i) => {
    const y = 232 + i * 70;
    addShape(slide, `check-${i + 1}-row`, "roundRect", 132, y, 1012, 54, i % 2 === 0 ? C.light : C.white, C.line, 1);
    addShape(slide, `check-${i + 1}-circle`, "ellipse", 86, y + 7, 40, 40, C.orange, C.orange, 0);
    addText(slide, `check-${i + 1}-num`, String(i + 1), 96, y + 14, 20, 24, { fontSize: 18, bold: true, color: C.white, alignment: "center" });
    addText(slide, `check-${i + 1}-title`, item.title, 160, y + 14, 240, 26, { fontSize: 20, bold: true, color: C.navy });
    addText(slide, `check-${i + 1}-body`, item.body, 430, y + 14, 680, 28, { fontSize: 18, color: C.gray });
  });
  addText(slide, "bottom-line", slideSpec.bottom_line, 166, 604, 948, 36, {
    fontSize: 21,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderTakeaway(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addText(slide, "lesson-label", `${localizedLabels().takeaway} ${currentSpec.lesson_number}`, 78, 98, 520, 28, { fontSize: 17, bold: true, color: C.orange });
  addText(slide, "takeaway-title", slideSpec.title, 78, 150, 1044, 100, {
    fontSize: 44,
    bold: true,
    color: C.navy,
  });
  addShape(slide, "takeaway-box", "roundRect", 96, 306, 1088, 186, C.light, C.line, 1.4);
  addText(slide, "takeaway-copy", slideSpec.body, 142, 348, 996, 96, {
    fontSize: 27,
    color: C.gray,
    alignment: "center",
  });
  addText(slide, "final-line", slideSpec.final_line, 214, 548, 852, 42, {
    fontSize: 28,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderSlide(deck, slideSpec) {
  const renderers = {
    cover: renderCover,
    intro_image_bullets: renderIntroImageBullets,
    image_bullets: renderImageBullets,
    card_sequence: renderCardSequence,
    comparison: renderComparison,
    planned_actual: renderPlannedActual,
    row_list: renderRowList,
    checklist_rows: renderChecklistRows,
    takeaway: renderTakeaway,
  };
  const renderer = renderers[slideSpec.layout];
  if (!renderer) {
    throw new Error(`Unsupported slide layout: ${slideSpec.layout}`);
  }
  await renderer(deck, slideSpec);
}

function deckQaText(spec) {
  const checks = spec.qa_checks || [];
  return `# Lesson ${String(spec.lesson_number).padStart(2, "0")} Deck QA

Course slug: ${spec.course_slug}
Approved baseline artifact: ${spec.approved_baseline_artifact || spec.output.pptx}
Latest revision artifact: ${spec.output.pptx}
Created: ${spec.created}
Revision: ${spec.revision}

## Revision Reason

${(spec.revision_reason || []).map((item) => `- ${item}`).join("\n")}

## Build Checks

${checks.map((item) => `- ${item}`).join("\n")}

## Inspection

${(spec.inspection_notes || []).map((item) => `- ${item}`).join("\n")}
`;
}

async function build(spec) {
  currentSpec = spec;
  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  log("deck", { name: `${spec.course_title} - Lesson ${spec.lesson_number}` });

  for (const slideSpec of spec.slides) {
    await renderSlide(deck, slideSpec);
  }

  const outDir = runPath(spec.output.rendered_dir);
  const pptxPath = runPath(spec.output.pptx);
  const inspectPath = `${pptxPath}.inspect.ndjson`;
  const qaPath = runPath(spec.output.qa);
  await fs.mkdir(outDir, { recursive: true });
  await fs.mkdir(path.dirname(pptxPath), { recursive: true });

  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(path.join(outDir, `${stem}.png`), await deck.export({ slide, format: "png", scale: 1 }));
    await fs.writeFile(path.join(outDir, `${stem}.layout.json`), await (await slide.export({ format: "layout" })).text());
    log("notes", { slide: index + 1, text: "" });
  }

  await writeBlob(path.join(outDir, "deck-montage.webp"), await deck.export({ format: "webp", montage: true, scale: 1 }));

  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(pptxPath);
  await fs.writeFile(inspectPath, inspectRows.map((row) => JSON.stringify(row)).join("\n") + "\n");
  await fs.writeFile(qaPath, deckQaText(spec));
}

const args = parseArgs(process.argv);
const spec = await readJson(rootPath(args.spec));
await build(spec);
