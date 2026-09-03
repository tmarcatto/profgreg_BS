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
  requestRed: "#B91C1C",
  requestPale: "#FEF2F2",
};

const inspectRows = [];
let currentSlide = 0;
let currentSpec = null;
const ROOT = process.cwd();

function localizedLabels() {
  if (currentSpec?.locale === "pt_br") {
    return {
      lesson: "LIÇÃO",
      topics: "Principais tópicos abordados",
      takeaway: "CONCLUSÃO DA LIÇÃO",
      baselineSchedule: "CRONOGRAMA-BASE",
      lookaheadPlan: "PLANO DE CURTO PRAZO",
      condition: "Condição",
      planned: "Planejado",
      actual: "Realizado",
      decisionAction: "Decisão / ação",
      variance: "Variação",
      decisionReadyUpdate: "Atualização para decisão",
    };
  }
  if (currentSpec?.locale === "es") {
    return {
      lesson: "LECCIÓN",
      topics: "Temas principales",
      takeaway: "CONCLUSIÓN DE LA LECCIÓN",
      baselineSchedule: "CRONOGRAMA BASE",
      lookaheadPlan: "PLAN DE CORTO PLAZO",
      condition: "Condición",
      planned: "Planificado",
      actual: "Real",
      decisionAction: "Decisión / acción",
      variance: "Variación",
      decisionReadyUpdate: "Actualización para decidir",
    };
  }
  return {
    lesson: "LESSON",
    topics: "Main topics covered",
    takeaway: "LESSON TAKEAWAY",
    baselineSchedule: "BASELINE SCHEDULE",
    lookaheadPlan: "LOOKAHEAD PLAN",
    condition: "Condition",
    planned: "Planned",
    actual: "Actual",
    decisionAction: "Decision / action",
    variance: "Variance",
    decisionReadyUpdate: "Decision-ready update",
  };
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
  shape.text = String(text ?? "");
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
    // QA must evaluate the actual text box the renderer created.  Omitting
    // the resolved size made the fit check silently skip every live deck.
    resolvedFontSize: style.fontSize ?? 22,
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
  const shallow = h < 180;
  const longTitle = String(title || "").length > (shallow ? 24 : 18);
  const titleHeight = shallow ? (longTitle ? 52 : 34) : compact ? (longTitle ? 64 : 48) : 34;
  const bodyTop = shallow ? (longTitle ? 78 : 56) : compact ? (longTitle ? 92 : 76) : 72;
  addShape(slide, `${key}-card`, "roundRect", x, y, w, h, fill, C.line, 1.4);
  addText(slide, `${key}-title`, title, x + 20, y + 18, w - 40, titleHeight, {
    fontSize: shallow ? (longTitle ? 15 : 16) : compact ? (longTitle ? 15 : 18) : 21,
    bold: true,
    color: accent,
    alignment: "center",
  });
  addText(slide, `${key}-body`, body, x + 22, y + bodyTop, w - 44, h - bodyTop - 14, {
    fontSize: shallow ? (longTitle ? 11 : 12) : compact ? (longTitle ? 12 : 14) : 18,
    color: C.gray,
    alignment: "center",
  });
}

function addImageRequestBox(slide, request, x, y, w, h) {
  addShape(slide, "operator-image-request", "roundRect", x, y, w, h, C.requestPale, C.requestRed, 3);
  addText(slide, "operator-image-request-label", "IMAGE REQUIRED", x + 24, y + 22, w - 48, 34, {
    fontSize: 20, bold: true, color: C.requestRed, alignment: "center",
  });
  addText(slide, "operator-image-description", `Description: ${request.image_description || "Required teaching image"}`, x + 30, y + 74, w - 60, 76, {
    fontSize: 16, color: C.requestRed,
  });
  addText(slide, "operator-image-pedagogy", `Pedagogical reason: ${request.pedagogical_reason || "This image is required for the planned learning task."}`, x + 30, y + 156, w - 60, 88, {
    fontSize: 16, color: C.requestRed,
  });
  addText(slide, "operator-image-search", `Suggested search: ${request.search_phrase || ""}`, x + 30, y + 252, w - 60, 50, {
    fontSize: 14, italic: true, color: C.requestRed,
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
    if (image.request) addImageRequestBox(slide, image, imageX, imageY, imageW, imageH);
    else await addImage(slide, image.name || "teaching-image", imagePath, imageX, imageY, imageW, imageH, image.alt, "cover");
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
    if (image.request) addImageRequestBox(slide, image, imageX, imageY, imageW, imageH);
    else await addImage(slide, image.name || "teaching-image", imagePath, imageX, imageY, imageW, imageH, image.alt, "cover");
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
  if (slideSpec.image?.request) {
    addImageRequestBox(slide, slideSpec.image, imageX, 236, 540, 330);
  } else {
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
}

async function renderCardSequence(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const items = slideSpec.items || [];
  if (items.length > 4) {
    const cols = 3;
    const w = 360;
    const h = 132;
    const gapX = 28;
    const gapY = 22;
    const x0 = 72;
    const y0 = 232;
    items.slice(0, 6).forEach((item, i) => {
      const x = x0 + (i % cols) * (w + gapX);
      const y = y0 + Math.floor(i / cols) * (h + gapY);
      card(slide, `${slideSpec.key || "sequence"}-${i + 1}`, item.title, item.body, x, y, w, h, C.navy, C.light);
    });
  } else {
    const x0 = 70;
    const w = 260;
    items.forEach((item, i) => {
      const x = x0 + i * 282;
      card(slide, `${slideSpec.key || "sequence"}-${i + 1}`, item.title, item.body, x, 270, w, 230, C.navy, C.light);
      if (i < items.length - 1) addLine(slide, `${slideSpec.key || "sequence"}-arrow-${i + 1}`, x + w, 385, x + 282, 385);
    });
  }
  addText(slide, "takeaway", slideSpec.bottom_line || slideSpec.takeaway || "", 150, 548, 980, 44, {
    fontSize: 22,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderProcessFlow(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const items = (slideSpec.items || []).slice(0, 6);
  const gap = 24;
  const totalW = 1136;
  const w = (totalW - gap * (items.length - 1)) / Math.max(items.length, 1);
  const x0 = 72;
  items.forEach((item, i) => {
    const x = x0 + i * (w + gap);
    if (i < items.length - 1) addLine(slide, `process-arrow-${i + 1}`, x + w, 386, x + w + gap, 386, C.orange, 3);
  });
  items.forEach((item, i) => {
    const x = x0 + i * (w + gap);
    card(slide, `process-${i + 1}`, item.title, item.body, x, 278, w, 216, C.navy, C.light);
  });
  addText(slide, "bottom-line", slideSpec.bottom_line || slideSpec.takeaway || "", 150, 536, 980, 52, {
    fontSize: 22, bold: true, color: C.navy, alignment: "center",
  });
}

async function renderScheduleBarChart(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const rows = (slideSpec.schedule_rows || []).slice(0, 7);
  const maxEnd = Math.max(1, ...rows.map((row) => Number(row.start || 0) + Number(row.duration || 1)));
  const labelX = 82;
  const chartX = 352;
  const chartW = 822;
  const rowH = 52;
  const startY = 232;
  for (let tick = 0; tick <= maxEnd; tick += 1) {
    const x = chartX + (tick / maxEnd) * chartW;
    addShape(slide, `schedule-grid-${tick}`, "rect", x, startY - 20, 1, rows.length * rowH + 20, C.line, C.line, 0);
    if (tick < maxEnd) addText(slide, `schedule-tick-${tick}`, String(tick + 1), x + 4, startY - 24, 32, 20, { fontSize: 11, color: C.muted });
  }
  rows.forEach((row, i) => {
    const y = startY + i * rowH;
    addText(slide, `schedule-label-${i + 1}`, row.activity, labelX, y + 7, 246, 34, { fontSize: 16, bold: true, color: C.navy });
    const x = chartX + (Number(row.start || 0) / maxEnd) * chartW;
    const w = Math.max(20, (Number(row.duration || 1) / maxEnd) * chartW);
    const fill = row.status === "delayed" ? C.orange : row.status === "complete" ? C.navy : C.softBlue;
    addShape(slide, `schedule-bar-${i + 1}`, "roundRect", x, y + 8, w, 30, fill, fill, 0);
  });
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 150, 594, 980, 34, { fontSize: 20, bold: true, color: C.navy, alignment: "center" });
}

async function renderActivityNetwork(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const paths = (slideSpec.network_paths || []).slice(0, 2);
  paths.forEach((networkPath, pathIndex) => {
    const activities = (networkPath.activities || []).slice(0, 4);
    const y = 254 + pathIndex * 170;
    addText(slide, `network-path-${pathIndex + 1}-label`, networkPath.label || `Path ${pathIndex + 1}`, 70, y + 28, 142, 70, {
      fontSize: 16, bold: true, color: networkPath.critical ? C.orange : C.navy,
    });
    const x0 = 224;
    const w = 196;
    const gap = 54;
    activities.forEach((activity, i) => {
      const x = x0 + i * (w + gap);
      if (i < activities.length - 1) addLine(slide, `network-${pathIndex + 1}-arrow-${i + 1}`, x + w, y + 58, x + w + gap, y + 58, networkPath.critical ? C.orange : C.slate, 3);
    });
    activities.forEach((activity, i) => {
      const x = x0 + i * (w + gap);
      addShape(slide, `network-${pathIndex + 1}-node-${i + 1}`, "roundRect", x, y, w, 116, networkPath.critical ? C.paleOrange : C.light, networkPath.critical ? C.orange : C.line, 1.4);
      addText(slide, `network-${pathIndex + 1}-title-${i + 1}`, activity.title, x + 14, y + 18, w - 28, 44, { fontSize: 16, bold: true, color: C.navy, alignment: "center" });
      addText(slide, `network-${pathIndex + 1}-duration-${i + 1}`, activity.duration || "", x + 18, y + 72, w - 36, 24, { fontSize: 15, color: C.gray, alignment: "center" });
    });
  });
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 150, 582, 980, 42, { fontSize: 20, bold: true, color: C.navy, alignment: "center" });
}

async function renderComparison(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  if (slideSpec.left && slideSpec.right) {
    card(slide, "weak", slideSpec.left.title, slideSpec.left.body, 122, 270, 430, 210, C.gray, C.light);
    card(slide, "strong", slideSpec.right.title, slideSpec.right.body, 728, 270, 430, 210, C.navy, C.softBlue);
    addLine(slide, "compare-arrow", 574, 376, 706, 376, C.orange, 4);
  } else {
    const columns = (slideSpec.comparison_columns || []).slice(0, 4);
    const rows = (slideSpec.comparison_rows || []).slice(0, 5);
    const x0 = 70;
    const tableW = 1140;
    const firstW = 190;
    const otherW = (tableW - firstW) / Math.max(columns.length - 1, 1);
    const widths = columns.map((_, i) => i === 0 ? firstW : otherW);
    let x = x0;
    columns.forEach((column, i) => {
      addShape(slide, `comparison-header-${i + 1}`, "rect", x, 216, widths[i], 48, i === 0 ? C.slate : C.navy, C.white, 1);
      addText(slide, `comparison-header-text-${i + 1}`, column, x + 8, 226, widths[i] - 16, 28, { fontSize: 14, bold: true, color: C.white, alignment: "center" });
      x += widths[i];
    });
    rows.forEach((row, rowIndex) => {
      const cells = Array.isArray(row.cells) ? row.cells : Object.values(row);
      let cellX = x0;
      widths.forEach((width, columnIndex) => {
        const y = 264 + rowIndex * 58;
        addShape(slide, `comparison-${rowIndex + 1}-${columnIndex + 1}`, "rect", cellX, y, width, 58, rowIndex % 2 ? C.white : C.light, C.line, 1);
        addText(slide, `comparison-text-${rowIndex + 1}-${columnIndex + 1}`, cells[columnIndex] || "", cellX + 8, y + 9, width - 16, 40, { fontSize: columnIndex === 0 ? 13 : 12, bold: columnIndex === 0, color: columnIndex === 0 ? C.navy : C.gray, alignment: "center" });
        cellX += width;
      });
    });
  }
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 154, 568, 972, 42, {
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
  const rows = (slideSpec.planned_actual_rows || []).slice(0, 5);
  if (rows.length) {
    const labels = localizedLabels();
    const columns = [labels.condition, labels.planned, labels.actual, labels.decisionAction];
    const x0 = 58;
    const widths = [160, 286, 286, 432];
    let x = x0;
    columns.forEach((column, index) => {
      addShape(slide, `variance-header-${index + 1}`, "rect", x, 210, widths[index], 46, index === 0 ? C.slate : C.navy, C.white, 1);
      addText(slide, `variance-header-text-${index + 1}`, column, x + 8, 220, widths[index] - 16, 26, { fontSize: 14, bold: true, color: C.white, alignment: "center" });
      x += widths[index];
    });
    const rowHeight = rows.length > 3 ? 61 : 82;
    rows.forEach((row, rowIndex) => {
      const action = [...new Set([row.variance, row.action, row.decision].filter(Boolean))].join(" — ");
      const cells = [row.item || row.title || labels.condition, row.planned || "", row.actual || "", action];
      let cellX = x0;
      widths.forEach((width, columnIndex) => {
        const y = 256 + rowIndex * rowHeight;
        addShape(slide, `variance-${rowIndex + 1}-${columnIndex + 1}`, "rect", cellX, y, width, rowHeight, rowIndex % 2 ? C.white : C.light, C.line, 1);
        addText(slide, `variance-text-${rowIndex + 1}-${columnIndex + 1}`, cells[columnIndex], cellX + 8, y + 7, width - 16, rowHeight - 14, {
          fontSize: rows.length > 3 ? (columnIndex === 0 ? 12 : 11) : (columnIndex === 0 ? 14 : 13),
          bold: columnIndex === 0,
          color: columnIndex === 0 ? C.navy : C.gray,
          alignment: "center",
        });
        cellX += width;
      });
    });
    addText(slide, "bottom-line", slideSpec.bottom_line || "", 168, 576, 944, 38, {
      fontSize: 17, bold: true, color: C.navy, alignment: "center",
    });
    return;
  }
  // Comparison copy varies substantially by lesson.  Allocate enough room
  // for a normal four-line explanation instead of relying on a short model
  // response to stay inside the lane.
  const planned = slideSpec.left || slideSpec.planned || {};
  const actual = slideSpec.right || slideSpec.actual || {};
  addShape(slide, "planned-lane", "roundRect", 106, 232, 458, 154, C.light, C.line, 1.4);
  addShape(slide, "actual-lane", "roundRect", 716, 232, 458, 154, C.light, C.line, 1.4);
  addText(slide, "planned-title", planned.title || planned.label || localizedLabels().planned, 138, 252, 386, 34, { fontSize: 21, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "planned-body", planned.body || "", 146, 298, 370, 70, { fontSize: 16, color: C.gray, alignment: "center" });
  addText(slide, "actual-title", actual.title || actual.label || localizedLabels().actual, 748, 252, 386, 34, { fontSize: 21, bold: true, color: C.navy, alignment: "center" });
  addText(slide, "actual-body", actual.body || "", 756, 298, 370, 70, { fontSize: 16, color: C.gray, alignment: "center" });
  addLine(slide, "variance-arrow", 586, 312, 694, 312, C.orange, 4);
  addText(slide, "variance-label", slideSpec.bridge_label || localizedLabels().variance, 576, 266, 128, 34, { fontSize: 14, bold: true, color: C.orange, alignment: "center" });
  if (slideSpec.decision_ready_update) {
    const update = slideSpec.decision_ready_update;
    card(slide, "decision-ready", update.title || update.label || localizedLabels().decisionReadyUpdate, update.body || "", 238, 410, 804, 112, C.orange, C.paleOrange);
  }
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 168, 548, 944, 42, {
    fontSize: 20,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderRowList(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const items = (slideSpec.items || []).slice(0, 6);
  const dense = items.length > 5;
  items.forEach((item, i) => {
    const yy = (dense ? 210 : 224) + i * (dense ? 60 : 76);
    const rowHeight = dense ? 54 : 68;
    addShape(slide, `row-${i + 1}-bar`, "roundRect", 104, yy, 1068, rowHeight, i % 2 === 0 ? C.light : C.white, C.line, 1);
    addText(slide, `row-${i + 1}-title`, item.title, 128, yy + (dense ? 9 : 12), 260, dense ? 36 : 44, { fontSize: dense ? 15 : 18, bold: true, color: C.navy });
    addText(slide, `row-${i + 1}-body`, item.body, 432, yy + (dense ? 7 : 10), 704, dense ? 40 : 48, { fontSize: dense ? 14 : 17, color: C.gray });
  });
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 164, dense ? 580 : 602, 952, 34, {
    fontSize: dense ? 16 : 17,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
}

async function renderChecklistRows(deck, slideSpec) {
  const slide = addSlide(deck);
  await addChrome(slide, currentSlide);
  addTitle(slide, slideSpec.title, slideSpec.subtitle);
  const items = (slideSpec.items || []).slice(0, 6);
  const dense = items.length > 5;
  items.forEach((item, i) => {
    const y = (dense ? 208 : 220) + i * (dense ? 60 : 76);
    const rowHeight = dense ? 54 : 68;
    const circleSize = dense ? 34 : 40;
    addShape(slide, `check-${i + 1}-row`, "roundRect", 132, y, 1012, rowHeight, i % 2 === 0 ? C.light : C.white, C.line, 1);
    addShape(slide, `check-${i + 1}-circle`, "ellipse", 90, y + (dense ? 10 : 14), circleSize, circleSize, C.orange, C.orange, 0);
    addText(slide, `check-${i + 1}-num`, String(i + 1), 98, y + (dense ? 15 : 21), 18, 22, { fontSize: dense ? 15 : 18, bold: true, color: C.white, alignment: "center" });
    addText(slide, `check-${i + 1}-title`, item.title, 160, y + (dense ? 8 : 12), 240, dense ? 38 : 44, { fontSize: dense ? 15 : 18, bold: true, color: C.navy });
    addText(slide, `check-${i + 1}-body`, item.body, 430, y + (dense ? 7 : 10), 680, dense ? 40 : 48, { fontSize: dense ? 14 : 17, color: C.gray });
  });
  addText(slide, "bottom-line", slideSpec.bottom_line || "", 166, dense ? 580 : 598, 948, 34, {
    fontSize: dense ? 16 : 17,
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
  // Localized takeaway copy often needs one additional line.  Give the copy
  // a deliberate, readable fit rather than allowing the final line to cross
  // the panel border.
  addShape(slide, "takeaway-box", "roundRect", 96, 306, 1088, 216, C.light, C.line, 1.4);
  addText(slide, "takeaway-copy", slideSpec.body, 142, 344, 996, 146, {
    fontSize: 24,
    color: C.gray,
    alignment: "center",
  });
  addText(slide, "final-line", slideSpec.final_line, 214, 554, 852, 42, {
    fontSize: 24,
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
    process_flow: renderProcessFlow,
    schedule_bar_chart: renderScheduleBarChart,
    activity_network: renderActivityNetwork,
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
