---
name: OUTMAX Cut
description: A quiet local video workbench for product footage on Windows.
colors:
  ink: "#202720"
  muted: "#62695f"
  accent: "#335a32"
  canvas: "#f4f4ef"
  surface: "#fff"
  line: "#dbdfd6"
  focus: "#729d5d"
  accent-hover: "#264725"
  secondary: "#eef1e8"
  secondary-hover: "#e0e8d7"
  disabled-bg: "#e3e7dc"
  disabled-text: "#727a68"
  drop-bg: "#f4f5f0"
  drop-hover: "#e8eee0"
  stage: "#e5e5df"
  error-bg: "#fff0ed"
  error-text: "#922d26"
  workflow-idle: "#e7ebe1"
  folder-drop: "#eef2e7"
  queue-row: "#f5f6f2"
  queue-selected: "#eaf0e2"
  detail-panel: "#e7eddf"
  queue-attention: "#9a432e"
typography:
  headline:
    fontFamily: 'Manrope, "Segoe UI", sans-serif'
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-.035em"
  title:
    fontFamily: 'Manrope, "Segoe UI", sans-serif'
    fontSize: "16px"
    fontWeight: 700
    letterSpacing: "-.02em"
  body:
    fontFamily: 'Manrope, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 400
  label:
    fontFamily: 'Manrope, "Segoe UI", sans-serif'
    fontSize: "12px"
    fontWeight: 600
rounded:
  panel: "16px"
  drop: "10px"
  thumbnail: "8px"
  control: "7px"
  tab: "5px"
  stage: "4px"
  queue-row: "9px"
  detail: "12px"
spacing:
  compact: "8px"
  control: "12px"
  small: "16px"
  inset-small: "20px"
  section: "24px"
  panel: "26px"
  heading: "32px"
  page-horizontal: "42px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "12px 18px"
    width: "100%"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-primary-disabled:
    backgroundColor: "{colors.disabled-bg}"
    textColor: "{colors.disabled-text}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    padding: "6px 0"
  select:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "42px"
    width: "100%"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "26px"
  dropzone:
    backgroundColor: "{colors.drop-bg}"
    rounded: "{rounded.drop}"
    padding: "20px"
---

# Design System: OUTMAX Cut

## Overview

The implemented interface is a light, neutral photo and video workbench: white working panels on a warm pale canvas, compact Russian labels, and restrained olive actions. Footage is the principal visual material. This is a Windows desktop editor with a locally served interface, not a marketing page.

This document records the current implementation in `ui/index.html`, `ui/style.css`, `ui/app.js`, and `ui/batch.js`; descriptive language is an implementation observation, not a claim of user approval. Fonts, icons, media, and API requests resolve locally. The packaged Manrope font and inline SVG symbols require no external calls.

Skill adaptations: the requested taste-skill is marketing-focused, so only its restraint principles apply to this application screen. Emil design engineering informs small interaction feedback and reduced-motion support; Impeccable informs usability and consistent states. Playwright checks belong to verification of the implemented flows and responsive behavior; this document itself does not assert a test result.

Version 1.1 extends the same visual world with a batch queue, product-specific editing, and a shared output destination. The requested extension retains existing typography, spacing, color hierarchy, and single-video editing controls. Role suggestions are a local heuristic; thumbnails and explicit Model/Hands labels support manual review, not a claim of guaranteed recognition.

## Colors

Olive provides the single action accent. The secondary button is a pale neutral green surface, not a second brand accent. Ink and muted text establish hierarchy; white panels separate work from the canvas without ornamental borders. Focus uses a distinct lighter green outline. Errors have pale warm backgrounds and dark red copy; successful export uses the action accent with a check icon and text.

**Action and state rule.** Use the accent for actions, range controls, progress, and success feedback. Keep footage surfaces neutral so displayed products retain their visual prominence. Status must also have explanatory text.

## Typography

Manrope is bundled at `/ui/Manrope.ttf` as a variable face with weights (200–800), followed by Segoe UI and sans-serif. No remote font service is used. The headline is compact and balanced; section titles are stronger than metadata. Most field text, explanations, tabs, statuses, and timeline labels use (12px). The introductory supporting line uses the body role. Source headings use (13px, weight 650); action labels use (13px, weight 650). Progress and numerical metadata use tabular numerals.

Headline size changes to (25px) at the intermediate breakpoint and (28px) on narrow screens. Explanatory field copy uses line-height (1.65); errors use (1.6). Long filenames and output paths wrap rather than disappearing.

## Layout

The centered work area has a maximum width of (1440px), with desktop padding (36px 42px 30px). The top bar is (80px) high. A two-column workspace places sources and settings on the left, preview and export on the right, with a gap of (24px). The base columns are `minmax(320px,.84fr) minmax(430px,1.4fr)`.

At widths of at least (1400px), the controls column is (430px). At widths up to (1050px), the columns become `330px minmax(0,1fr)`, the gap becomes (16px), and page side padding becomes (24px). At widths up to (760px), the workspace stacks vertically, page side padding becomes (16px), panels use (20px) padding, and the header becomes (64px) high. Secondary header metadata is hidden to preserve room for the working controls.

The preview remains square and centered. Its desktop width uses `min(100%,clamp(280px,calc(100vh - 560px),520px))`, capped at (480px), or (520px) on wide screens. On narrow screens it uses full available width with the (480px) cap. Timeline segments express the fixed reference proportions (277:354:26), with labels and duration metadata.

In batch mode, a full-width queue panel precedes the selected product detail strip and existing editor. The workflow switch sits above the heading. Queue rows use six desktop columns (`18px minmax(150px,1fr) 150px 140px 155px 45px`) for selection, identity, paired thumbnails, swap, status, and removal. Rows have (16px) padding and gaps. Each role thumbnail is square (70px) with a text label below.

At widths up to (1100px), queue rows use four columns and move secondary actions onto a second row. At widths up to (760px), rows use two columns with the product, pair, status, swap, and removal vertically aligned after the checkbox column. The folder chooser wraps, output path input occupies its own line, batch actions stack, and per-product source selectors become vertical. The selected detail strip uses (24px 26px) padding on desktop and (20px) on narrow screens.

## Elevation & Depth

The interface has no box shadows. White panels, muted preview surfaces, and spacing establish depth. A native help dialog uses an opaque white surface and a dark translucent backdrop (`#20272080`). Selected preview tabs become white within their pale rail. Avoid adding decorative elevation to routine controls.

## Shapes

Panels and the dialog use broad rounded corners; controls use smaller corners. Upload targets have dashed borders, making their drop behavior distinguishable from normal cards. Video thumbnails and the stage clip their content. The olive geometric brand mark is the sole custom decorative silhouette; icons use simple outlined SVG strokes.

## Components

- **Primary buttons:** full-width olive action, white label, minimum height (45px), darkened hover, and pale disabled state. Press feedback scales enabled buttons to (.98). Render remains unavailable until both sources are loaded and no upload or export is active.
- **Secondary and text buttons:** pale fill for opening the result folder; underlined text for help, replacement, and cancellation. Their visual rank follows their place in the workflow.
- **Upload targets:** minimum height (104px), dashed border, visible upload icon, title, and supporting text. Hover and drag-over share the highlighted surface. Enter and Space activate file selection. Busy targets use opacity (.6) and stop accepting pointer interaction.
- **Fields:** native selects and ranges keep familiar desktop behavior. Selects have a (1px) border and the documented control radius. Contextual help changes with the chosen editing mode or transition. Smart-mode sensitivity appears only when relevant.
- **Preview navigation:** two compact tabs expose reference and result. Result is disabled until export succeeds. Arrow keys switch available tabs. The player exposes native video controls and an accessible label.
- **Progress and results:** rendering overlays the square stage, shows a textual stage, percentage, progress bar, and cancel action. Errors use an alert; uploads use status regions. Changing source or settings marks a previous result stale and hides its save actions until a new export completes.
- **Help dialog:** native modal dialog with a clear close button and backdrop dismissal. Its explanations remain readable at narrow widths.

- **Workflow switch:** “Один ролик” and “Пакетная сборка” use pressed-state buttons. Active mode is olive with white text; inactive mode uses the pale workflow surface. The single-editor snapshot is preserved when switching modes. Mode switches are disabled during import, source upload, collection, or export.
- **Folder import:** a wide dashed target combines a folder icon, explanatory copy, and a white chooser button. Enter and Space activate it. Drag-over gains a stronger pale green fill; locked state uses opacity (.65). Windows uses a native folder picker; browser mode accepts directory selection or dropped directory entries. Import has textual counts, cancellation, errors, and a notice when recognized OUTMAX exports are skipped.
- **Queue rows:** each item has a selection checkbox, product name, heuristic explanation, Model/Hands thumbnails, swap, status, and removal. The active editor item uses the selected row surface; checkbox selection independently controls export. Thumbnail and product buttons open the shared editor for that item. Missing roles show “Выбрать” placeholders. “Выбрать все готовые” selects only complete pairs of distinct files.
- **Product detail:** a pale green strip names the active item, explains its role suggestion, exposes two source selects, swaps roles, and offers explicit settings propagation to all items. Each item retains independent sources, crops, mode, transition, sensitivity, and result. Selecting a source already assigned to the other role clears that other assignment. Swapping sources keeps crop positions attached to roles. Propagating settings preserves source order.
- **Output chooser:** labeled text input (42px high) with native chooser and open-folder actions. Browser fallback asks for an absolute local path. Export is enabled only with at least one selected complete pair and a nonempty destination. Each product uses its own subfolder; the interface explicitly promises preservation of existing exports.
- **Queue states:** incomplete or ambiguous pairing says “Нужно выбрать пару” and uses attention color; these items cannot enter export until two distinct sources are assigned. Ready, changed, queued, running, saved, error, and cancelled states have explicit text. Running rows show percentage and a thin progress bar; the queue also shows aggregate progress and counts. Errors remain attached to their item and allow retry. A completed result becomes stale after relevant edits, with status “Настройки изменены”; old output is excluded from the up-to-date saved count. Cancellation preserves completed files. Temporary polling failures announce retry. Import and queue processing lock editing mutations; status stays visible.

Opening a queue item scrolls its detail strip into view smoothly, or instantly when reduced motion is requested. Queue selection and focus are separate states: selection has a pale fill; keyboard focus retains the common outline.

Focus is a (3px) outline with (4px) offset on buttons, links, focusable drop targets, inputs, and selects. Button transitions last (160ms); drop feedback lasts (150ms). The rendering mark pulses using scale and opacity over (1.2s) with staggered bars. `prefers-reduced-motion: reduce` removes animations and transitions and restores automatic scroll behavior.

## Do's and Don'ts

- **Do** preserve the calm local workbench, Russian action labels, and footage-first hierarchy.
- **Do** retain keyboard access, visible focus, native controls, explanatory disabled states, and reduced-motion support.
- **Do** keep asset loading and app requests local; preserve the bundled font and inline icons.
- **Do** verify empty, loaded, rendering, failure, cancelled, finished, and stale-result states, plus narrow-screen layout. For batch mode, include ambiguous pairing, role swaps, per-item persistence, output selection, skipped existing exports, partial failure, and cancellation.
- **Don't** turn this tool into a marketing layout with oversized hero typography or decorative content sections.
- **Don't** add ornamental shadows or competing accent colors to the existing flat system.
- **Don't** communicate upload, export, or failure state by color or animation alone.
- **Don't** present local heuristic role suggestions as AI certainty or guaranteed classification.

