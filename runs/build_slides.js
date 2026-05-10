// build_slides.js -- 12-slide research presentation for auto_cst NIR project
// Output: D:/Claude/auto_cst/runs/auto_cst_NIR_presentation.pptx
//
// Color palette (committed):
//   Dark navy   #0E1A2B  (title/conclusion backgrounds)
//   Cream       #FAFAF7  (content slide background, dark-slide text)
//   Slate       #2C3E50  (body text on cream)
//   Copper      #C7754A  (single warm accent for emphasis)
//   Muted gray  #6B7B8C  (captions, secondary text)
//
// Hypothesis data colors (match runs/FINAL_REPORT_spectra.png):
//   Hypothesis A  #1F77B4  (blue)
//   Hypothesis B  #FF7F0E  (orange)
//   Hypothesis C  #2CA02C  (green)
//
// Visual motif: 0.12"-wide vertical accent bar on the left of every content
// slide, in the relevant hypothesis color (or copper for non-hypothesis slides).

const pptxgen = require("pptxgenjs");

const COLORS = {
  navy:    "0E1A2B",
  cream:   "FAFAF7",
  slate:   "2C3E50",
  copper:  "C7754A",
  muted:   "6B7B8C",
  divider: "D8D3C5",
  hypA:    "1F77B4",
  hypB:    "FF7F0E",
  hypC:    "2CA02C",
  ok:      "2E7D32",
  partial: "ED6C02",
  fail:    "C62828",
};

const FONT_HEADER = "Georgia";
const FONT_BODY   = "Calibri";

const pres = new pptxgen();
pres.layout  = "LAYOUT_WIDE";          // 13.3" x 7.5"
pres.author  = "auto_cst";
pres.title   = "auto_cst — Autonomous NIR Perfect Absorber Design";
pres.company = "auto_cst";

const W = 13.3;
const H = 7.5;

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function darkSlideBg(slide) {
  slide.background = { color: COLORS.navy };
}

function lightSlideBg(slide) {
  slide.background = { color: COLORS.cream };
}

function accentBar(slide, color) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: H,
    fill: { color }, line: { type: "none" },
  });
}

function slideTitle(slide, text, color = COLORS.navy) {
  slide.addText(text, {
    x: 0.6, y: 0.4, w: W - 1.2, h: 0.6,
    fontSize: 32, fontFace: FONT_HEADER, bold: true,
    color, valign: "top", margin: 0,
  });
}

function slideSubtitle(slide, text, color = COLORS.muted) {
  slide.addText(text, {
    x: 0.6, y: 1.05, w: W - 1.2, h: 0.4,
    fontSize: 14, fontFace: FONT_BODY, italic: true,
    color, valign: "middle", margin: 0,
  });
}

// For slides 7-9 we put a small hypothesis tag ABOVE the title, then push
// the title down to make room.
function slideTaggedTitle(slide, tagRich, titleText, accentColor) {
  slide.addText(tagRich, {
    x: 0.6, y: 0.35, w: W - 1.2, h: 0.35,
    fontFace: FONT_BODY, valign: "middle", margin: 0,
  });
  slide.addText(titleText, {
    x: 0.6, y: 0.75, w: W - 1.2, h: 0.6,
    fontSize: 28, fontFace: FONT_HEADER, bold: true,
    color: COLORS.navy, valign: "top", margin: 0,
  });
}

function pageNumber(slide, n) {
  slide.addText(`${n} / 12`, {
    x: W - 1.0, y: H - 0.45, w: 0.8, h: 0.3,
    fontSize: 9, fontFace: FONT_BODY, color: COLORS.muted, align: "right",
  });
}

function sectionFooter(slide, sectionLabel) {
  slide.addText(sectionLabel, {
    x: 0.6, y: H - 0.45, w: 8, h: 0.3,
    fontSize: 9, fontFace: FONT_BODY, color: COLORS.muted, italic: true,
  });
}

// ============================================================================
// Slide 1 — Title (DARK)
// ============================================================================
{
  const slide = pres.addSlide();
  darkSlideBg(slide);

  // Top tag
  slide.addText("auto_cst", {
    x: 0.8, y: 0.6, w: 4, h: 0.4,
    fontSize: 14, fontFace: FONT_BODY, bold: true,
    color: COLORS.copper, charSpacing: 4,
  });

  // Big headline numbers
  slide.addText([
    { text: "5 nm",       options: { fontSize: 96, bold: true, color: COLORS.cream } },
    { text: "  peak error,  ", options: { fontSize: 36, color: COLORS.cream } },
    { text: "99.94%",     options: { fontSize: 96, bold: true, color: COLORS.copper } },
    { text: "  absorption",   options: { fontSize: 36, color: COLORS.cream } },
  ], {
    x: 0.8, y: 1.7, w: W - 1.6, h: 1.8,
    fontFace: FONT_HEADER, valign: "middle", margin: 0,
  });

  // Subtitle
  slide.addText("Autonomous NIR perfect-absorber design via a three-stage agent pipeline", {
    x: 0.8, y: 3.7, w: W - 1.6, h: 0.6,
    fontSize: 22, fontFace: FONT_HEADER, italic: true, color: COLORS.cream, margin: 0,
  });

  // Pipeline stages strip
  slide.addText([
    { text: "Stage 1  ", options: { fontSize: 13, bold: true, color: COLORS.copper } },
    { text: "Literature review     ", options: { fontSize: 13, color: COLORS.cream } },
    { text: "Stage 2  ", options: { fontSize: 13, bold: true, color: COLORS.copper } },
    { text: "CST geometry build     ", options: { fontSize: 13, color: COLORS.cream } },
    { text: "Stage 3  ", options: { fontSize: 13, bold: true, color: COLORS.copper } },
    { text: "LLM-in-loop fine-tune", options: { fontSize: 13, color: COLORS.cream } },
  ], {
    x: 0.8, y: 4.6, w: W - 1.6, h: 0.5, fontFace: FONT_BODY, margin: 0, charSpacing: 1,
  });

  // Divider
  slide.addShape(pres.shapes.LINE, {
    x: 0.8, y: 5.3, w: 2.5, h: 0,
    line: { color: COLORS.copper, width: 2 },
  });

  // Bottom info
  slide.addText("Target: 1550 nm absorber  ·  TM polarization  ·  CST Studio Suite + OpenAI gpt-4o", {
    x: 0.8, y: 5.5, w: W - 1.6, h: 0.4,
    fontSize: 13, fontFace: FONT_BODY, color: COLORS.cream, italic: true, margin: 0,
  });

  slide.addText("github.com/DaryLu0v0/auto_cst", {
    x: 0.8, y: H - 0.7, w: W - 1.6, h: 0.4,
    fontSize: 11, fontFace: FONT_BODY, color: COLORS.muted, margin: 0,
  });
}

// ============================================================================
// Slide 2 — The problem
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "The problem");

  // Left column: prose
  slide.addText([
    {
      text: "Designing a NIR perfect absorber at 1550 nm",
      options: { bold: true, color: COLORS.slate, breakLine: true },
    },
    {
      text: "(telecom C-band, 193.41 THz) traditionally requires expert manual iteration in a full-wave EM solver — tweaking geometric parameters until the simulated reflection peak lines up with the target wavelength.",
      options: { color: COLORS.slate, breakLine: true },
    },
    { text: " ", options: { breakLine: true, fontSize: 6 } },
    {
      text: "Each candidate design takes 5–15 minutes to simulate. A typical convergence path is 10–50 iterations. Across multiple shape hypotheses, this is hours-to-days of expert time per target.",
      options: { color: COLORS.slate },
    },
  ], {
    x: 0.7, y: 1.5, w: 6.8, h: 4,
    fontSize: 17, fontFace: FONT_BODY, valign: "top", paraSpaceAfter: 6, margin: 0,
  });

  // Right column: stat cards
  const cardX = 8.0;
  const cardW = 4.5;
  const stats = [
    { label: "PER SIMULATION",  value: "5–15 min" },
    { label: "PER DESIGN",      value: "10–50 iters" },
    { label: "PER WAVELENGTH",  value: "3–10 designs" },
  ];
  stats.forEach((s, i) => {
    const yi = 1.6 + i * 1.4;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cardX, y: yi, w: cardW, h: 1.15,
      fill: { color: "FFFFFF" }, line: { color: COLORS.divider, width: 0.75 },
      shadow: { type: "outer", color: "000000", blur: 6, offset: 1, angle: 90, opacity: 0.06 },
    });
    slide.addText(s.label, {
      x: cardX + 0.3, y: yi + 0.18, w: cardW - 0.6, h: 0.28,
      fontSize: 10, fontFace: FONT_BODY, bold: true, color: COLORS.muted,
      charSpacing: 3, margin: 0,
    });
    slide.addText(s.value, {
      x: cardX + 0.3, y: yi + 0.45, w: cardW - 0.6, h: 0.6,
      fontSize: 32, fontFace: FONT_HEADER, bold: true, color: COLORS.navy, margin: 0,
    });
  });

  // Goal banner
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 6.1, w: W - 1.4, h: 0.7,
    fill: { color: COLORS.navy }, line: { type: "none" },
  });
  slide.addText([
    { text: "Goal — ", options: { bold: true, color: COLORS.copper } },
    { text: "automate the loop end-to-end. From a one-line target spec to a converged CST project, no human in the loop.", options: { color: COLORS.cream } },
  ], {
    x: 0.9, y: 6.1, w: W - 1.8, h: 0.7,
    fontSize: 16, fontFace: FONT_BODY, italic: true, valign: "middle", margin: 0,
  });

  pageNumber(slide, 2);
}

// ============================================================================
// Slide 3 — Pipeline overview
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "Three-stage agent pipeline");
  slideSubtitle(slide, "Each stage is an autonomous LLM-driven module that hands off via a JSON contract.");

  const stageY = 2.2;
  const stageH = 3.2;
  const stageW = 3.8;
  const gap    = 0.2;
  const startX = (W - 3 * stageW - 2 * gap) / 2;

  const stages = [
    {
      label: "STAGE 1",
      title: "Literature review",
      bg:    "F2EBE0",
      border: COLORS.muted,
      labelColor: COLORS.muted,
      titleColor: COLORS.slate,
      tag:   "(upstream, prior work)",
      input: "INPUT  Target spec",
      output: "OUTPUT  hypothesis.json — ranked papers + λ-scaled designs",
      tools: "VLM figure extraction · LLM ranking · automated PDF acquisition",
    },
    {
      label: "STAGE 2",
      title: "CST geometry build",
      bg:    "FFFFFF",
      border: COLORS.copper,
      labelColor: COLORS.copper,
      titleColor: COLORS.navy,
      tag:   "(this work)",
      input: "INPUT  hypothesis.json + chosen rank",
      output: "OUTPUT  per-hypothesis CST project (working_X.cst)",
      tools: "VBA injection harness · constraint validation · materials/geometry/ports",
    },
    {
      label: "STAGE 3",
      title: "LLM-in-loop optimizer",
      bg:    "FFFFFF",
      border: COLORS.copper,
      labelColor: COLORS.copper,
      titleColor: COLORS.navy,
      tag:   "(this work)",
      input: "INPUT  working CST project + score function",
      output: "OUTPUT  converged design + iteration history",
      tools: "OpenAI gpt-4o · keep/revert loop · mode-hop detection · constraint retry",
    },
  ];

  stages.forEach((s, i) => {
    const x = startX + i * (stageW + gap);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: stageY, w: stageW, h: stageH,
      fill: { color: s.bg }, line: { color: s.border, width: 1.5 },
      shadow: { type: "outer", color: "000000", blur: 8, offset: 2, angle: 90, opacity: 0.08 },
    });
    slide.addText(s.label, {
      x: x + 0.3, y: stageY + 0.25, w: stageW - 0.6, h: 0.3,
      fontSize: 10, fontFace: FONT_BODY, bold: true, color: s.labelColor, charSpacing: 3, margin: 0,
    });
    slide.addText(s.title, {
      x: x + 0.3, y: stageY + 0.55, w: stageW - 0.6, h: 0.5,
      fontSize: 22, fontFace: FONT_HEADER, bold: true, color: s.titleColor, margin: 0,
    });
    slide.addText(s.tag, {
      x: x + 0.3, y: stageY + 1.1, w: stageW - 0.6, h: 0.3,
      fontSize: 10, fontFace: FONT_BODY, italic: true, color: COLORS.muted, margin: 0,
    });
    slide.addText([
      { text: s.input,  options: { bold: true, color: COLORS.copper, breakLine: true, fontSize: 11 } },
      { text: " ",      options: { breakLine: true, fontSize: 4 } },
      { text: s.output, options: { bold: true, color: COLORS.copper, breakLine: true, fontSize: 11 } },
      { text: " ",      options: { breakLine: true, fontSize: 4 } },
      { text: s.tools,  options: { color: COLORS.slate, fontSize: 11 } },
    ], {
      x: x + 0.3, y: stageY + 1.5, w: stageW - 0.6, h: stageH - 1.7,
      fontFace: FONT_BODY, valign: "top", paraSpaceAfter: 4, margin: 0,
    });

    // Arrows between stages
    if (i < stages.length - 1) {
      const ax = x + stageW + 0.02;
      slide.addShape(pres.shapes.LINE, {
        x: ax, y: stageY + stageH / 2, w: gap - 0.04, h: 0,
        line: { color: COLORS.copper, width: 2, endArrowType: "triangle" },
      });
    }
  });

  // Bottom callout
  slide.addText("This deck covers stages 2 and 3. Stage 1 output is treated as an input contract.", {
    x: 0.7, y: 6.0, w: W - 1.4, h: 0.4,
    fontSize: 13, fontFace: FONT_BODY, italic: true, color: COLORS.muted, align: "center", margin: 0,
  });

  pageNumber(slide, 3);
}

// ============================================================================
// Slide 4 — Stage 1 input recap
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "Stage 1 input — top-3 ranked hypotheses");
  slideSubtitle(slide, "Upstream lit-review agent screened 54 papers; ranked 6; handed off the top 3.");

  const tableData = [
    [
      { text: "Rank", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", fontSize: 12, align: "center" } },
      { text: "DOI",  options: { bold: true, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", fontSize: 12 } },
      { text: "Geometry (lit review)", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", fontSize: 12 } },
      { text: "Score", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", fontSize: 12, align: "center" } },
      { text: "Dimensions extracted?", options: { bold: true, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", fontSize: 12 } },
    ],
    [
      { text: "1", options: { color: COLORS.hypB, bold: true, align: "center", valign: "middle", fontSize: 14 } },
      { text: "10.1364/oe.415960", options: { color: COLORS.slate, valign: "middle", fontSize: 11, fontFace: "Consolas" } },
      { text: "Elliptical disk supercell (4 ellipses)", options: { color: COLORS.slate, valign: "middle", fontSize: 12 } },
      { text: "0.467", options: { color: COLORS.slate, align: "center", valign: "middle", fontSize: 12 } },
      { text: "Shape only — dimensions all null", options: { color: COLORS.fail, italic: true, valign: "middle", fontSize: 11 } },
    ],
    [
      { text: "2", options: { color: COLORS.hypA, bold: true, align: "center", valign: "middle", fontSize: 14, fill: { color: "EEF6FB" } } },
      { text: "10.1039/d2ra05617h", options: { color: COLORS.slate, valign: "middle", fontSize: 11, fontFace: "Consolas", fill: { color: "EEF6FB" } } },
      { text: "Metallic disk MIM on Au/SiO₂/Ag stack", options: { color: COLORS.slate, valign: "middle", bold: true, fontSize: 12, fill: { color: "EEF6FB" } } },
      { text: "0.442", options: { color: COLORS.slate, align: "center", valign: "middle", fontSize: 12, fill: { color: "EEF6FB" } } },
      { text: "Yes — λ-scaled by 1.32× to 1550 nm", options: { color: COLORS.ok, valign: "middle", bold: true, fontSize: 11, fill: { color: "EEF6FB" } } },
    ],
    [
      { text: "3", options: { color: COLORS.hypC, bold: true, align: "center", valign: "middle", fontSize: 14 } },
      { text: "10.1021/acsphotonics.8b00872", options: { color: COLORS.slate, valign: "middle", fontSize: 11, fontFace: "Consolas" } },
      { text: "Lithography-free planar absorber", options: { color: COLORS.slate, valign: "middle", fontSize: 12 } },
      { text: "0.383", options: { color: COLORS.slate, align: "center", valign: "middle", fontSize: 12 } },
      { text: "No shape, no dimensions", options: { color: COLORS.fail, italic: true, valign: "middle", fontSize: 11 } },
    ],
  ];

  slide.addTable(tableData, {
    x: 0.7, y: 1.7, w: W - 1.4, colW: [0.8, 2.7, 4.1, 1.0, 3.3],
    rowH: [0.5, 0.6, 0.6, 0.6],
    border: { type: "solid", color: COLORS.divider, pt: 0.5 },
  });

  // Insight callout
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 4.3, w: W - 1.4, h: 0.08,
    fill: { color: COLORS.copper }, line: { type: "none" },
  });
  slide.addText([
    { text: "Insight  ", options: { bold: true, fontSize: 14, color: COLORS.copper } },
    { text: "Only rank 2 was simulation-ready. Ranks 1 and 3 had figures but no extracted dimensions — for those, stage 2 had to invent reasonable starting geometry. This made convergence harder and produced a real result we couldn't have predicted from the lit review alone.", options: { fontSize: 14, color: COLORS.slate } },
  ], {
    x: 0.7, y: 4.55, w: W - 1.4, h: 1.5, fontFace: FONT_BODY, valign: "top", margin: 0,
  });

  // Target spec strip
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 6.3, w: W - 1.4, h: 0.6,
    fill: { color: COLORS.navy }, line: { type: "none" },
  });
  slide.addText([
    { text: "TARGET   ", options: { bold: true, fontSize: 11, color: COLORS.copper, charSpacing: 3 } },
    { text: "Peak: 1550 nm (193.41 THz)     ", options: { fontSize: 13, color: COLORS.cream, bold: true } },
    { text: "FWHM: 200 nm     ", options: { fontSize: 13, color: COLORS.cream } },
    { text: "Polarization: TM     ", options: { fontSize: 13, color: COLORS.cream } },
    { text: "Score: |f − target| + 0.2 · max(0, 0.90 − abs)", options: { fontSize: 12, color: COLORS.cream, italic: true } },
  ], {
    x: 0.9, y: 6.3, w: W - 1.8, h: 0.6, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });

  pageNumber(slide, 4);
}

// ============================================================================
// Slide 5 — Stage 2: CST geometry build
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "Stage 2 — building the unit cell from VBA");
  slideSubtitle(slide, "Three hypothesis-specific runners share one MIM stack and one VBA-injection pattern.");

  // LEFT: stack diagram
  const sx = 0.9, sy = 2.1, sw = 4.2, lh = 0.7;
  const layers = [
    { label: "Ag resonator (h)",         color: "DCDCE0", textColor: COLORS.slate },
    { label: "SiO₂ spacer (d)",          color: "DCE7F0", textColor: COLORS.slate },
    { label: "Au ground (t_ground)",     color: "F2D788", textColor: COLORS.slate },
  ];
  layers.forEach((L, i) => {
    const yi = sy + i * lh;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: sx, y: yi, w: sw, h: lh - 0.04,
      fill: { color: L.color }, line: { color: COLORS.divider, width: 1 },
    });
    slide.addText(L.label, {
      x: sx + 0.2, y: yi, w: sw - 0.4, h: lh - 0.04,
      fontSize: 14, fontFace: FONT_BODY, color: L.textColor, valign: "middle", bold: true, margin: 0,
    });
  });
  // Substrate label
  slide.addText("← unit cell, period p (square lattice) →", {
    x: sx, y: sy + 3 * lh, w: sw, h: 0.4,
    fontSize: 11, fontFace: FONT_BODY, italic: true, color: COLORS.muted, align: "center", margin: 0,
  });

  // Per-hypothesis variants
  slide.addText("Three resonator shapes, one stack:", {
    x: sx, y: sy + 3.9 * 0.4 + 0.2 + 1.2, w: sw, h: 0.3,
    fontSize: 12, fontFace: FONT_BODY, bold: true, color: COLORS.navy, margin: 0,
  });
  slide.addText([
    { text: "● ", options: { color: COLORS.hypA, fontSize: 16 } },
    { text: "A ", options: { bold: true, color: COLORS.hypA, fontSize: 13 } },
    { text: "circular Ag disk (r)", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: "● ", options: { color: COLORS.hypB, fontSize: 16 } },
    { text: "B ", options: { bold: true, color: COLORS.hypB, fontSize: 13 } },
    { text: "rectangular Ag patch (lx, ly)", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: "● ", options: { color: COLORS.hypC, fontSize: 16 } },
    { text: "C ", options: { bold: true, color: COLORS.hypC, fontSize: 13 } },
    { text: "uniform thin Ag film (no patterning)", options: { color: COLORS.slate, fontSize: 12 } },
  ], {
    x: sx, y: sy + 3.6, w: sw, h: 1.2, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 3,
  });

  // RIGHT: VBA injection step list
  const rx = 6.0, ry = 2.1, rw = W - rx - 0.6;
  slide.addText("VBA injection (one history step per item):", {
    x: rx, y: ry, w: rw, h: 0.4,
    fontSize: 14, fontFace: FONT_BODY, bold: true, color: COLORS.navy, margin: 0,
  });

  const vbaSteps = [
    "1. Delete default PEC box",
    "2. StoreDoubleParameter \"r\", 580   (et al.)",
    "3. Units: nm / THz / fs",
    "4. Frequency range 100–300 THz",
    "5. Boundary: X/Y unit cell, Z expanded open",
    "6. Background: vacuum",
    "7. Materials: Au_lossy, Ag_lossy, SiO2",
    "8. Geometry: ground brick + spacer brick + resonator",
    "9. Floquet ports (Zmax + Zmin, 2 modes each)",
    "10. Solver type + mesh",
  ];
  slide.addText(vbaSteps.map((s, i) => ({
    text: s,
    options: { fontFace: "Consolas", fontSize: 11, color: COLORS.slate, breakLine: i < vbaSteps.length - 1 },
  })), {
    x: rx, y: ry + 0.4, w: rw, h: 3.2, valign: "top", paraSpaceAfter: 2, margin: 0,
  });

  // Solver-mesh decision rule call-out
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: 5.9, w: rw, h: 1.2,
    fill: { color: "FFFFFF" }, line: { color: COLORS.copper, width: 1.5 },
  });
  slide.addText([
    { text: "Solver / mesh decision rule", options: { bold: true, color: COLORS.copper, fontSize: 12, breakLine: true } },
    { text: "● Patterned absorbers (A, B): ", options: { color: COLORS.slate, fontSize: 11 } },
    { text: "HF Time Domain + PBA hex", options: { color: COLORS.slate, fontSize: 11, bold: true, breakLine: true } },
    { text: "● Uniform planar (C): ", options: { color: COLORS.slate, fontSize: 11 } },
    { text: "HF Frequency Domain + Tetrahedral", options: { color: COLORS.slate, fontSize: 11, bold: true, breakLine: true } },
    { text: "TD with periodic Floquet boundaries does NOT excite an absorbing mode in a fully-uniform stack.", options: { color: COLORS.muted, fontSize: 10, italic: true } },
  ], {
    x: rx + 0.2, y: 6.0, w: rw - 0.4, h: 1.0, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 1,
  });

  pageNumber(slide, 5);
}

// ============================================================================
// Slide 6 — Stage 3: LLM-in-loop optimizer
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "Stage 3 — the LLM-in-loop optimizer");
  slideSubtitle(slide, "ChatGPT proposes parameter changes with reasoning. The runner evaluates. Score decides keep or revert.");

  // Loop diagram in a row
  const nodes = [
    { label: "Read history",           color: COLORS.slate },
    { label: "ChatGPT proposes",       color: COLORS.copper },
    { label: "Validate constraints",   color: COLORS.slate },
    { label: "Run CST",                color: COLORS.slate },
    { label: "Score",                  color: COLORS.slate },
    { label: "Keep / revert",          color: COLORS.copper },
  ];
  const ny  = 2.0;
  const nh  = 0.85;
  const nw  = 1.85;
  const ngap = 0.13;
  const nstartX = (W - nodes.length * nw - (nodes.length - 1) * ngap) / 2;

  nodes.forEach((n, i) => {
    const x = nstartX + i * (nw + ngap);
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y: ny, w: nw, h: nh,
      fill: { color: n.color === COLORS.copper ? "F8E5D5" : "FFFFFF" },
      line: { color: n.color, width: 1.5 },
      rectRadius: 0.08,
    });
    slide.addText(n.label, {
      x: x + 0.05, y: ny, w: nw - 0.1, h: nh,
      fontSize: 12, fontFace: FONT_BODY, bold: true, color: n.color,
      align: "center", valign: "middle", margin: 0,
    });
    if (i < nodes.length - 1) {
      slide.addShape(pres.shapes.LINE, {
        x: x + nw + 0.01, y: ny + nh / 2, w: ngap - 0.02, h: 0,
        line: { color: COLORS.muted, width: 1.2, endArrowType: "triangle" },
      });
    }
  });

  // Loop-back arrow underneath
  const loopY = ny + nh + 0.3;
  slide.addText("loop until score < threshold or 5 consecutive no-improve", {
    x: 0.7, y: loopY, w: W - 1.4, h: 0.3,
    fontSize: 10, fontFace: FONT_BODY, italic: true, color: COLORS.muted,
    align: "center", margin: 0,
  });
  slide.addShape(pres.shapes.LINE, {
    x: nstartX + nw / 2, y: loopY + 0.4,
    w: nodes.length * nw + (nodes.length - 1) * ngap - nw, h: 0,
    line: { color: COLORS.muted, width: 1.0, dashType: "dash", endArrowType: "triangle" },
  });

  // Two-column lower section
  const colY = 4.2;
  const colH = 2.7;

  // LEFT: Score formula
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: colY, w: 6.0, h: colH,
    fill: { color: "FFFFFF" }, line: { color: COLORS.divider, width: 1 },
  });
  slide.addText("SCORE FORMULA", {
    x: 0.9, y: colY + 0.15, w: 5.6, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.copper, charSpacing: 3, margin: 0,
  });
  slide.addText("score = |f_peak − f_target| + 0.2 · max(0, 0.90 − peak_abs)", {
    x: 0.9, y: colY + 0.5, w: 5.6, h: 0.5,
    fontSize: 16, fontFace: "Consolas", color: COLORS.navy, margin: 0,
  });
  slide.addText([
    { text: "First term: Hz of frequency error (dominant when peak is off-target).", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: "Second term: penalty if peak amplitude < 0.90 (kicks in for weak resonances).", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Lower is better. ", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: "Convergence threshold: 0.5 THz (≈ 4 nm wavelength accuracy at 1550 nm).", options: { color: COLORS.slate, fontSize: 12 } },
  ], {
    x: 0.9, y: colY + 1.1, w: 5.6, h: 1.5, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 4,
  });

  // RIGHT: Per-iteration what happens
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.0, y: colY, w: W - 7.6, h: colH,
    fill: { color: "FFFFFF" }, line: { color: COLORS.divider, width: 1 },
  });
  slide.addText("PER-ITERATION DETAIL", {
    x: 7.2, y: colY + 0.15, w: W - 8.0, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.copper, charSpacing: 3, margin: 0,
  });
  slide.addText([
    { text: "ChatGPT input: ", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: "system prompt with hypothesis-specific physics; user message with target + last 12 results + last 5 reverts", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "ChatGPT output: ", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: "JSON {changes: {...}, reasoning: \"...\"}", options: { fontFace: "Consolas", fontSize: 11, color: COLORS.slate, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Constraint retry: ", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: "up to 2 retries with the violation message in the prompt", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Subprocess CST: ", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: "isolated runner.py — a CST crash never kills the agent", options: { color: COLORS.slate, fontSize: 12 } },
  ], {
    x: 7.2, y: colY + 0.5, w: W - 8.0, h: 2.1, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 1,
  });

  pageNumber(slide, 6);
}

// ============================================================================
// Slide 7 — Hypothesis A: Disk MIM (CONVERGED)
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.hypA);

  // Tagged title (tag above title)
  slideTaggedTitle(slide, [
    { text: "HYPOTHESIS A   ", options: { bold: true, fontSize: 11, color: COLORS.hypA, charSpacing: 3 } },
    { text: "·   Disk MIM   ·   ", options: { fontSize: 11, color: COLORS.muted } },
    { text: "CONVERGED", options: { bold: true, fontSize: 11, color: COLORS.ok, charSpacing: 2 } },
  ], "Disk MIM — peak landed 5 nm from target", COLORS.hypA);

  // Big stat hero (numbers)
  const sx = 0.7, sy = 1.4;
  slide.addText("FINAL", {
    x: sx, y: sy, w: 5, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  slide.addText("1554.94 nm", {
    x: sx, y: sy + 0.3, w: 6, h: 1.0,
    fontSize: 64, fontFace: FONT_HEADER, bold: true, color: COLORS.hypA, margin: 0,
  });
  slide.addText([
    { text: "5 nm error  ",  options: { bold: true, color: COLORS.ok,  fontSize: 18 } },
    { text: "(0.32 % of λ)", options: { italic: true, color: COLORS.muted, fontSize: 14 } },
  ], {
    x: sx, y: sy + 1.3, w: 6, h: 0.4, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });
  slide.addText([
    { text: "99.94 %", options: { bold: true, color: COLORS.hypA, fontSize: 28 } },
    { text: "  peak absorption", options: { color: COLORS.slate, fontSize: 16 } },
  ], {
    x: sx, y: sy + 1.85, w: 6, h: 0.5, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });
  slide.addText([
    { text: "8 iterations", options: { bold: true, color: COLORS.slate, fontSize: 14 } },
    { text: "  (4 keeps, 4 reverts)   ", options: { color: COLORS.muted, fontSize: 14 } },
    { text: "·   ", options: { color: COLORS.muted, fontSize: 14 } },
    { text: "~14 min", options: { bold: true, color: COLORS.slate, fontSize: 14 } },
    { text: "  total wall time", options: { color: COLORS.muted, fontSize: 14 } },
  ], {
    x: sx, y: sy + 2.5, w: 6.5, h: 0.4, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });

  // RIGHT: Final design table
  const px = 7.5, py = 1.4, pw = W - px - 0.6;
  slide.addText("FINAL DESIGN  (nm)", {
    x: px, y: py, w: pw, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  const designRows = [
    [
      { text: "param", options: { bold: true, fontSize: 11, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", align: "left" } },
      { text: "baseline", options: { bold: true, fontSize: 11, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", align: "right" } },
      { text: "converged", options: { bold: true, fontSize: 11, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", align: "right" } },
      { text: "Δ", options: { bold: true, fontSize: 11, color: "FFFFFF", fill: { color: COLORS.navy }, valign: "middle", align: "right" } },
    ],
    [
      { text: "p (period)", options: { fontSize: 12, color: COLORS.slate, valign: "middle" } },
      { text: "993.59", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
      { text: "1300", options: { fontSize: 12, bold: true, color: COLORS.hypA, valign: "middle", align: "right" } },
      { text: "+306", options: { fontSize: 12, color: COLORS.slate, valign: "middle", align: "right" } },
    ],
    [
      { text: "r (disk radius)", options: { fontSize: 12, color: COLORS.slate, valign: "middle" } },
      { text: "457.05", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
      { text: "580", options: { fontSize: 12, bold: true, color: COLORS.hypA, valign: "middle", align: "right" } },
      { text: "+123", options: { fontSize: 12, color: COLORS.slate, valign: "middle", align: "right" } },
    ],
    [
      { text: "h (disk thickness)", options: { fontSize: 12, color: COLORS.slate, valign: "middle" } },
      { text: "105.98", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
      { text: "105.98", options: { fontSize: 12, color: COLORS.slate, valign: "middle", align: "right" } },
      { text: "0", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
    ],
    [
      { text: "d (SiO₂ spacer)", options: { fontSize: 12, color: COLORS.slate, valign: "middle" } },
      { text: "112.61", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
      { text: "100", options: { fontSize: 12, bold: true, color: COLORS.hypA, valign: "middle", align: "right" } },
      { text: "−12.6", options: { fontSize: 12, color: COLORS.slate, valign: "middle", align: "right" } },
    ],
    [
      { text: "t_ground (Au)", options: { fontSize: 12, color: COLORS.slate, valign: "middle" } },
      { text: "100", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
      { text: "100", options: { fontSize: 12, color: COLORS.slate, valign: "middle", align: "right" } },
      { text: "0", options: { fontSize: 12, color: COLORS.muted, valign: "middle", align: "right" } },
    ],
  ];
  slide.addTable(designRows, {
    x: px, y: py + 0.35, w: pw,
    colW: [pw * 0.42, pw * 0.20, pw * 0.20, pw * 0.18],
    rowH: [0.4, 0.4, 0.4, 0.4, 0.4, 0.4],
    border: { type: "solid", color: COLORS.divider, pt: 0.5 },
  });

  // Bottom: convergence narrative
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 5.7, w: W - 1.4, h: 1.4,
    fill: { color: "EEF6FB" }, line: { color: COLORS.hypA, width: 1 },
  });
  slide.addText([
    { text: "Convergence story:  ", options: { bold: true, color: COLORS.hypA, fontSize: 13 } },
    { text: "iters 2–5 wasted ~6 min on a ", options: { color: COLORS.slate, fontSize: 13 } },
    { text: "mode hop", options: { bold: true, color: COLORS.slate, fontSize: 13 } },
    { text: " — the LLM proposed shrinking r to lower the frequency, but the peak ", options: { color: COLORS.slate, fontSize: 13 } },
    { text: "jumped 75 THz upward instead", options: { italic: true, color: COLORS.slate, fontSize: 13 } },
    { text: ", because a higher-order LSPR took over near the period boundary. After expanding p from 1200 to 1300 nm at iter 6 (giving the disk room), the score collapsed: ", options: { color: COLORS.slate, fontSize: 13, breakLine: true } },
    { text: "5.21 → 0.61 → 0.19", options: { fontFace: "Consolas", bold: true, color: COLORS.hypA, fontSize: 13 } },
    { text: " in three iterations.  This case directly motivated the mode-hop detector added in retrospective improvements (slide 11).", options: { color: COLORS.slate, fontSize: 13 } },
  ], {
    x: 0.9, y: 5.8, w: W - 1.8, h: 1.2, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 2,
  });

  pageNumber(slide, 7);
}

// ============================================================================
// Slide 8 — Hypothesis B: Rect-patch MIM (PARTIAL)
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.hypB);

  slideTaggedTitle(slide, [
    { text: "HYPOTHESIS B   ", options: { bold: true, fontSize: 11, color: COLORS.hypB, charSpacing: 3 } },
    { text: "·   Rectangular-patch MIM   ·   ", options: { fontSize: 11, color: COLORS.muted } },
    { text: "PARTIAL CONVERGENCE", options: { bold: true, fontSize: 11, color: COLORS.partial, charSpacing: 2 } },
  ], "Rect-patch MIM — landed 7 % off, learned polarization axis", COLORS.hypB);

  // LEFT: stats
  const sx = 0.7, sy = 1.5;
  slide.addText("PEAK", {
    x: sx, y: sy, w: 5, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  slide.addText("1662 nm", {
    x: sx, y: sy + 0.3, w: 6, h: 1.0,
    fontSize: 60, fontFace: FONT_HEADER, bold: true, color: COLORS.hypB, margin: 0,
  });
  slide.addText([
    { text: "112 nm error  ", options: { bold: true, color: COLORS.partial, fontSize: 18 } },
    { text: "(7.2 % of λ)", options: { italic: true, color: COLORS.muted, fontSize: 14 } },
  ], {
    x: sx, y: sy + 1.3, w: 6, h: 0.4, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });
  slide.addText([
    { text: "79.0 %", options: { bold: true, color: COLORS.hypB, fontSize: 26 } },
    { text: "  peak absorption", options: { color: COLORS.slate, fontSize: 16 } },
  ], {
    x: sx, y: sy + 1.85, w: 6, h: 0.5, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });
  slide.addText([
    { text: "10 iterations", options: { bold: true, color: COLORS.slate, fontSize: 14 } },
    { text: "  (5 keeps, capped without convergence)", options: { color: COLORS.muted, fontSize: 14 } },
  ], {
    x: sx, y: sy + 2.5, w: 6.5, h: 0.4, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });

  // RIGHT: Final design + the swap insight
  const px = 7.5, py = 1.5, pw = W - px - 0.6;
  slide.addText("FINAL DESIGN  (nm)", {
    x: px, y: py, w: pw, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  const designB = [
    [{ text: "p", o: COLORS.slate }, { text: "1400", o: COLORS.hypB, b: true }],
    [{ text: "lx (initial long axis)", o: COLORS.slate }, { text: "500", o: COLORS.slate }],
    [{ text: "ly (now long axis)",     o: COLORS.slate }, { text: "1100", o: COLORS.hypB, b: true }],
    [{ text: "h", o: COLORS.slate }, { text: "100", o: COLORS.slate }],
    [{ text: "d (SiO₂ spacer)", o: COLORS.slate }, { text: "200", o: COLORS.hypB, b: true }],
    [{ text: "t_ground", o: COLORS.slate }, { text: "100", o: COLORS.slate }],
  ];
  const dBRows = designB.map(r => [
    { text: r[0].text, options: { fontSize: 12, color: r[0].o, valign: "middle" } },
    { text: r[1].text, options: { fontSize: 12, color: r[1].o, bold: !!r[1].b, valign: "middle", align: "right" } },
  ]);
  slide.addTable(dBRows, {
    x: px, y: py + 0.35, w: pw,
    colW: [pw * 0.65, pw * 0.35],
    rowH: Array(dBRows.length).fill(0.36),
    border: { type: "solid", color: COLORS.divider, pt: 0.5 },
  });

  // Bottom callout — the LLM's empirical swap insight
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 5.7, w: W - 1.4, h: 1.4,
    fill: { color: "FFF1E2" }, line: { color: COLORS.hypB, width: 1 },
  });
  slide.addText([
    { text: "What the LLM figured out empirically:  ", options: { bold: true, color: COLORS.hypB, fontSize: 13 } },
    { text: "the agent started with lx = 1100 nm as the LONG axis — but the dominant peak in the measured S₁₁ responded to ly. By the end of the run the agent had ", options: { color: COLORS.slate, fontSize: 13 } },
    { text: "swapped the role of the two axes", options: { italic: true, color: COLORS.slate, fontSize: 13 } },
    { text: ", growing ly to 1100 nm and shrinking lx to 500 nm. This is genuine empirical inference — not just executing prompted physics. ", options: { color: COLORS.slate, fontSize: 13, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Note  ", options: { bold: true, color: COLORS.muted, fontSize: 12, charSpacing: 3 } },
    { text: "Originally specced as elliptical disk per the rank-1 paper figure; pivoted to rect-patch after both ExtrudeCurve+Translate and Cylinder+Transform.Scale VBA paths failed (CST ActiveX 10091).", options: { italic: true, color: COLORS.muted, fontSize: 11 } },
  ], {
    x: 0.9, y: 5.8, w: W - 1.8, h: 1.2, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 2,
  });

  pageNumber(slide, 8);
}

// ============================================================================
// Slide 9 — Hypothesis C: Planar (FAILED)
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.hypC);

  slideTaggedTitle(slide, [
    { text: "HYPOTHESIS C   ", options: { bold: true, fontSize: 11, color: COLORS.hypC, charSpacing: 3 } },
    { text: "·   Planar Au/SiO₂/Ag stack   ·   ", options: { fontSize: 11, color: COLORS.muted } },
    { text: "DID NOT CONVERGE", options: { bold: true, fontSize: 11, color: COLORS.fail, charSpacing: 2 } },
  ], "Planar Fabry-Perot — a real materials limit, not a bug", COLORS.hypC);

  // LEFT: what happened
  const lx = 0.7, ly = 1.5, lw = 6.0;
  slide.addText("WHAT HAPPENED", {
    x: lx, y: ly, w: lw, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  slide.addText([
    { text: "● ", options: { color: COLORS.hypC, fontSize: 14 } },
    { text: "Time Domain solver: ", options: { bold: true, color: COLORS.slate, fontSize: 13 } },
    { text: "absorptance identically zero across 100–300 THz (|S11|² = 1.0). TD with periodic Floquet boundaries on a fully-uniform structure does not excite an absorbing mode.", options: { color: COLORS.slate, fontSize: 13, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "● ", options: { color: COLORS.hypC, fontSize: 14 } },
    { text: "Frequency Domain solver: ", options: { bold: true, color: COLORS.slate, fontSize: 13 } },
    { text: "tiny absorption (< 5 %) pegged to spectrum edge. Real signal but no resonant peak.", options: { color: COLORS.slate, fontSize: 13, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "● ", options: { color: COLORS.hypC, fontSize: 14 } },
    { text: "Agent loop: ", options: { bold: true, color: COLORS.slate, fontSize: 13 } },
    { text: "8 attempts varying d ∈ {267, 300, 450, 600 nm} and t_top ∈ {8, 12 nm}. Score plateaued at 106.76 (the noise-floor score) for all of them.", options: { color: COLORS.slate, fontSize: 13 } },
  ], {
    x: lx, y: ly + 0.4, w: lw, h: 3.2, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 2,
  });

  // RIGHT: why
  const rx = 7.0, ry = 1.5, rw = W - rx - 0.6;
  slide.addText("WHY  (the physics)", {
    x: rx, y: ry, w: rw, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, bold: true, color: COLORS.muted, charSpacing: 3, margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rx, y: ry + 0.35, w: rw, h: 4.2,
    fill: { color: "FFFFFF" }, line: { color: COLORS.divider, width: 1 },
  });
  slide.addText([
    { text: "The lithography-free planar absorber relies on ", options: { color: COLORS.slate, fontSize: 12 } },
    { text: "impedance matching", options: { italic: true, color: COLORS.slate, fontSize: 12 } },
    { text: " between a thin top metal film and free space at cavity resonance.", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "At 1550 nm, Au has  ε ≈ −95 + 11i  (Johnson & Christy fit) — strongly Drude-dispersive.", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Our materials use a constant-σ model (DC values + CST's high-frequency surface-impedance approximation). This is fine for ", options: { color: COLORS.slate, fontSize: 12 } },
    { text: "patterned LSPR-driven absorbers", options: { bold: true, color: COLORS.slate, fontSize: 12 } },
    { text: " (A and B work because the LC mode is dominant) — but for the impedance-matching cavity, the ratio of real to imaginary ε is wrong by an order of magnitude.", options: { color: COLORS.slate, fontSize: 12, breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 4 } },
    { text: "Result: high reflection across the band. ", options: { bold: true, color: COLORS.fail, fontSize: 12 } },
    { text: "A real physical/materials limitation, not a code bug.", options: { color: COLORS.slate, fontSize: 12 } },
  ], {
    x: rx + 0.2, y: ry + 0.5, w: rw - 0.4, h: 4.0, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 1,
  });

  // Bottom callout: the fix
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.7, y: 6.0, w: W - 1.4, h: 1.0,
    fill: { color: "EEFAEE" }, line: { color: COLORS.hypC, width: 1 },
  });
  slide.addText([
    { text: "The unblock:  ", options: { bold: true, color: COLORS.hypC, fontSize: 13 } },
    { text: "load CST's built-in dispersive Au / Ag from the material library. ", options: { color: COLORS.slate, fontSize: 13 } },
    { text: "nir/probe_drude_vba.py", options: { fontFace: "Consolas", color: COLORS.slate, fontSize: 12 } },
    { text: " automatically tries 9 candidate VBA syntaxes — likely takes one minute to find the right one in any given CST install.", options: { color: COLORS.slate, fontSize: 13 } },
  ], {
    x: 0.9, y: 6.05, w: W - 1.8, h: 0.9, fontFace: FONT_BODY, valign: "middle", margin: 0,
  });

  pageNumber(slide, 9);
}

// ============================================================================
// Slide 10 — Comparison spectra (full image)
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "All three designs — final spectra side by side");
  slideSubtitle(slide, "Vertical red dashed = target 1550 nm / 193.41 THz · vertical dotted = each design's measured peak.");

  // Image (regenerated without internal title): aspect ~1.44.
  // Use most of the slide width for the chart.
  const imgW = 11.0;                  // 11.0" wide (slide is 13.3")
  const imgH = imgW / (1484 / 1031);  // matches aspect, ~7.65" tall — but slide content area only allows ~5.5
  const imgHcap = 5.6;                // cap height; image will scale down to fit
  const imgFinalH = Math.min(imgH, imgHcap);
  const imgFinalW = imgFinalH * (1484 / 1031);
  const imgX = (W - imgFinalW) / 2;
  const imgY = 1.55;

  slide.addImage({
    path: "D:/Claude/auto_cst/runs/FINAL_REPORT_spectra.png",
    x: imgX, y: imgY, w: imgFinalW, h: imgFinalH,
  });

  pageNumber(slide, 10);
}

// ============================================================================
// Slide 11 — Lessons learned: building robust CST automation
// ============================================================================
{
  const slide = pres.addSlide();
  lightSlideBg(slide);
  accentBar(slide, COLORS.copper);
  slideTitle(slide, "Building robust CST automation");
  slideSubtitle(slide, "Five failure modes hit during the run, and the defensive code that now catches each one.");

  const lessons = [
    {
      n: "01",
      problem: "cst.results.ProjectFile silently breaks with relative paths",
      detail: "Result lookup raises “does not exist for run id=N” even though the data is in the file.",
      fix: "Wrapper open_results() always passes Path(...).resolve()",
    },
    {
      n: "02",
      problem: "Parameter injection invalidates run_id=0; API default is run_id=0",
      detail: "Real data lives at run_id=1+. Default get_result_item silently returns nothing.",
      fix: "Wrapper queries get_all_run_ids(), requests highest first",
    },
    {
      n: "03",
      problem: "Solver/mesh combo matters — wrong combo gives zero absorption with no error",
      detail: "TD+PBA hex for patterned absorbers; FD+Tetrahedral for uniform planar.",
      fix: "Hypothesis-specific solver/mesh dispatch in runner.py",
    },
    {
      n: "04",
      problem: "Constant-σ Au/Ag wrong for impedance-matching designs",
      detail: "OK for plasmonic-resonance designs (A, B). Catastrophic for thin-film cavity (C).",
      fix: "probe_drude_vba.py auto-tries 9 dispersive-material syntaxes",
    },
    {
      n: "05",
      problem: "LLM extrapolates trends across mode hops",
      detail: "Iters 2–5 of hypothesis A wasted on a higher-order LSPR masquerading as the fundamental.",
      fix: "Mode-hop detector auto-warns the LLM in the user message",
    },
  ];

  const ly = 1.6;
  const rh = 1.0;
  const rgap = 0.05;
  lessons.forEach((L, i) => {
    const y = ly + i * (rh + rgap);
    // Number column
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y, w: 0.6, h: rh,
      fill: { color: COLORS.navy }, line: { type: "none" },
    });
    slide.addText(L.n, {
      x: 0.6, y, w: 0.6, h: rh,
      fontSize: 22, fontFace: FONT_HEADER, bold: true, color: COLORS.copper,
      align: "center", valign: "middle", margin: 0,
    });
    // Body card
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 1.2, y, w: W - 1.8, h: rh,
      fill: { color: "FFFFFF" }, line: { color: COLORS.divider, width: 0.75 },
    });
    slide.addText([
      { text: L.problem, options: { bold: true, color: COLORS.slate, fontSize: 13, breakLine: true } },
      { text: L.detail,  options: { color: COLORS.muted, fontSize: 11, italic: true, breakLine: true } },
      { text: "FIX  ", options: { bold: true, color: COLORS.copper, fontSize: 11, charSpacing: 2 } },
      { text: L.fix, options: { color: COLORS.slate, fontSize: 12 } },
    ], {
      x: 1.4, y: y + 0.05, w: W - 2.2, h: rh - 0.1,
      fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 1,
    });
  });

  pageNumber(slide, 11);
}

// ============================================================================
// Slide 12 — Conclusions + future work (DARK)
// ============================================================================
{
  const slide = pres.addSlide();
  darkSlideBg(slide);

  slide.addText("CONCLUSIONS", {
    x: 0.8, y: 0.5, w: W - 1.6, h: 0.4,
    fontSize: 12, fontFace: FONT_BODY, bold: true, color: COLORS.copper, charSpacing: 4, margin: 0,
  });

  // Big takeaway
  slide.addText([
    { text: "5 nm peak error in ~14 minutes",  options: { fontSize: 44, fontFace: FONT_HEADER, bold: true, color: COLORS.cream } },
  ], {
    x: 0.8, y: 1.0, w: W - 1.6, h: 1.0, valign: "middle", margin: 0,
  });
  slide.addText("of CST + LLM time, fully autonomous from a one-line target spec.", {
    x: 0.8, y: 2.0, w: W - 1.6, h: 0.5,
    fontSize: 18, fontFace: FONT_HEADER, italic: true, color: COLORS.cream, margin: 0,
  });

  // Three takeaways
  const colY = 3.0, colH = 2.0, colW = (W - 2.2) / 3, colGap = 0.3;
  const takeaways = [
    {
      title: "Hypothesis matters",
      body: "Patterned absorbers worked (A converged, B partial). The lithography-free planar fell out — the materials model couldn't capture impedance matching. A genuinely different problem class.",
    },
    {
      title: "LLM can do empirical inference",
      body: "Hypothesis B's agent swapped the roles of lx and ly mid-run after seeing how the spectrum responded — not just executing prompted physics.",
    },
    {
      title: "Defensive wrappers pay off",
      body: "Every silent CST footgun (relative-path indexing, run_id=0, solver/mesh combos) cost real wall-time the first time. Once wrapped, they're free for everyone after.",
    },
  ];

  takeaways.forEach((t, i) => {
    const x = 0.8 + i * (colW + colGap);
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: colY, w: 0.04, h: colH,
      fill: { color: COLORS.copper }, line: { type: "none" },
    });
    slide.addText(t.title, {
      x: x + 0.2, y: colY, w: colW - 0.2, h: 0.5,
      fontSize: 16, fontFace: FONT_HEADER, bold: true, color: COLORS.cream, margin: 0,
    });
    slide.addText(t.body, {
      x: x + 0.2, y: colY + 0.55, w: colW - 0.2, h: colH - 0.55,
      fontSize: 12, fontFace: FONT_BODY, color: COLORS.cream, valign: "top", margin: 0,
    });
  });

  // Future work
  slide.addText("FUTURE WORK", {
    x: 0.8, y: 5.4, w: W - 1.6, h: 0.4,
    fontSize: 12, fontFace: FONT_BODY, bold: true, color: COLORS.copper, charSpacing: 4, margin: 0,
  });
  slide.addText([
    { text: "● ", options: { color: COLORS.copper, fontSize: 14 } },
    { text: "Run probe_drude_vba.py to fix dispersive Au/Ag and unblock hypothesis C", options: { color: COLORS.cream, fontSize: 14, breakLine: true } },
    { text: "● ", options: { color: COLORS.copper, fontSize: 14 } },
    { text: "Add multi-resonator topology (Salisbury overlay or dual-disk supercell) to broaden the 105 nm FWHM toward the 200 nm target", options: { color: COLORS.cream, fontSize: 14, breakLine: true } },
    { text: "● ", options: { color: COLORS.copper, fontSize: 14 } },
    { text: "Generalize to UV / mid-IR / GHz bands with per-band solver/mesh recipes", options: { color: COLORS.cream, fontSize: 14 } },
  ], {
    x: 0.8, y: 5.85, w: W - 1.6, h: 1.2, fontFace: FONT_BODY, valign: "top", margin: 0, paraSpaceAfter: 1,
  });

  // Footer
  slide.addShape(pres.shapes.LINE, {
    x: 0.8, y: H - 0.6, w: 2.5, h: 0,
    line: { color: COLORS.copper, width: 1.5 },
  });
  slide.addText("github.com/DaryLu0v0/auto_cst   ·   runs/FINAL_REPORT.md   ·   nir/VBA_COOKBOOK.md", {
    x: 0.8, y: H - 0.45, w: W - 1.6, h: 0.3,
    fontSize: 11, fontFace: FONT_BODY, color: COLORS.muted, margin: 0,
  });
}

// ----------------------------------------------------------------------------
// Save
// ----------------------------------------------------------------------------
pres.writeFile({ fileName: "auto_cst_NIR_presentation.pptx" }).then((fname) => {
  console.log(`Saved: ${fname}`);
});
