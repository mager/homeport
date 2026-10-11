---
name: Homeport
description: A persistent terminal workspace for Codex conversations on the Mini.
colors:
  bg: "#000"
  sidebar: "#08090a"
  surface: "#101214"
  ink: "#d8dce0"
  muted: "#90979e"
  line: "#25292d"
  accent: "#73d9ef"
  accent-soft: "#101e22"
  success: "#87d5a4"
  warning: "#e6bd77"
  danger: "#f09595"
  interrupted: "#c4acf0"
typography:
  body:
    fontFamily: '"Geist Mono", ui-monospace, "SFMono-Regular", Menlo, monospace'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  conversation:
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontSize: "11px"
    fontWeight: 400
  title:
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
  heading:
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.5
  welcome:
    fontSize: "clamp(20px, 2.5vw, 28px)"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "-.03em"
spacing:
  gutter: "clamp(20px, 3vw, 48px)"
  mobile-gutter: "16px"
  message-gap: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#061216"
    padding: "6px 12px"
    typography: "{typography.label}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    padding: "6px 9px"
    typography: "{typography.label}"
  session-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.ink}"
  session-navigation:
    backgroundColor: "{colors.sidebar}"
    width: "272px"
  toolbar:
    height: "54px"
---

# Design System: Homeport

## Overview

**Creative North Star: "Persistent terminal workspace"**

Homeport uses the owner's established black-and-cyan terminal direction. A continuous, left-aligned conversation is the working surface; quiet navigation and a docked prompt keep the next action close. Regular monospace type and visible, labeled state make dense work readable without decorative dashboard furniture.

**Key Characteristics:**
- True black scrollback with charcoal supporting surfaces.
- One self-hosted monospace family, predominantly regular weight.
- Cyan prompts and actions; semantic color paired with state text.
- Flat, square controls and fine separators.

## Colors

Cyan is the primary accent against neutral black and charcoal; green, amber, red, and lavender communicate state.

### Primary
- **Prompt cyan** (`accent`): prompt markers, links, focus, running state, and the send action.
- **Selected charcoal cyan** (`accent-soft`): selected session and menu hover backgrounds.

### Neutral
- **Terminal black** (`bg`): conversation canvas.
- **Navigation charcoal** (`sidebar`): session navigation, code, and file surfaces.
- **Control charcoal** (`surface`): controls and hover surfaces.
- **Reading gray** (`ink`): primary text; **metadata gray** (`muted`): supporting labels.
- **Divider charcoal** (`line`): fine structural borders.

### State
- **Completion green** (`success`): completed work and online connection.
- **Attention amber** (`warning`): queued or uncertain state and notices.
- **Failure red** (`danger`): failed work and offline connection.
- **Interruption lavender** (`interrupted`): interrupted work.

**The Labeled State Rule.** Pair semantic color with readable status text; color alone does not explain a session or command outcome.

## Typography

Use self-hosted Geist Mono from `src/magerbot/static/fonts/geist-mono.ttf`, with the frontmatter fallback stack throughout. This continues the owner's public-site type direction. Body, navigation, controls, and session titles remain regular; restrained medium weight is reserved for Markdown emphasis and headings.

Conversation paragraphs and lists stop at 74ch. Metadata is smaller than prose; command summaries sit between them at 12px. Code keeps whitespace and horizontal scrolling. The welcome heading is the only larger type treatment. Phone search and prompt inputs use 16px text while conversation prose stays at the body size.

## Layout

The desktop shell fills 100dvh: a 272px session column and a flexible workspace, under a 54px toolbar. Conversation scrollback takes the available height above the persistent prompt dock. Keep user and assistant entries on the same left alignment, distinguished by prompt markers, labels, spacing, and fine rules.

Use the responsive gutter token for conversation, session state, and prompt alignment. Desktop message bodies inset 20px from their markers; phones remove this inset. At 700px and below, navigation becomes a full-width overlay beneath the toolbar, gutters become 16px, and primary controls, toolbar actions, overflow menus, tool disclosures, and copy buttons receive 44px minimum targets.

The file pane is 360px wide on desktop; at 1100px and below it overlays the workspace, and at phone width it fills it. Short viewports (580px high or less) compact the prompt and hide its bottom note. Keep long commands and file content contained within their scroll regions.

## Elevation & Depth

Use flat tonal layers and one-pixel borders. The current interface has no decorative shadows, gradients, or blur. Overlays sit above content through positioning and clear edges. Focus uses a one-pixel cyan outline with a three-pixel offset; search and prompt containers also indicate focus through their border.

## Shapes

Controls and surfaces have square edges, fine rules, and compact padding. Status markers are small squares. Conversation entries are unboxed scrollback; bordered containers are reserved for code, controls, menus, and structural panes.

## Components

- **Buttons:** Cyan fill identifies send; quiet toolbar controls use muted text until hover. New task uses a charcoal surface and fine border. Disabled send is visibly muted. Preserve explicit text labels and focus treatment.
- **Session navigation:** Selected rows have a cyan left rule and tinted background. Show regular-weight title, project, task count, last activity, and labeled state. Search highlights matches; active/archived filters use an underline. Keep overflow actions visible for touch alongside keyboard and context-menu access.
- **Prompt dock:** A cyan marker and heading introduce the textarea. Draft feedback, conversation context, submit action, and shortcut hint remain close to the prompt. The dock stays visible while the conversation scrolls.
- **Command disclosures:** Show the command and actual running/completion/exit state on one compact summary row. Expand to reveal the full command and exact output in a scrollable monospace region. Retain plus/minus disclosure marks and textual state.
- **Markdown and code:** Render supported headings, lists, quotes, emphasis, and safe links through the existing text-based renderer. Code blocks have a language header and Copy action with `Copied` or `Select to copy` feedback; never imply success before the clipboard operation succeeds.
- **Scrollback continuity:** Keep the current reading position stable and offer Latest output when the user has moved away from the end. Do not use decorative motion; respect reduced motion.

## Do's and Don'ts

### Do:
- **Do** keep conversation and real work state visually primary.
- **Do** align prose, command output, and the prompt into one continuous terminal surface.
- **Do** use regular monospace session titles and labeled semantic status.
- **Do** preserve exact command/output content, accessible focus, and phone-sized action targets.

### Don't:
- **Don't** introduce decorative dashboards, marketing heroes, fake metrics, or a green garden palette.
- **Don't** turn conversation entries into rounded chat bubbles or floating cards.
- **Don't** present an uncertain submission or failed copy operation as successful.

<!-- Captured from src/magerbot/static/style.css, index.html, app.js, and markdown.js after the October 2026 refresh. Visual references: .impeccable/review/desktop.png (1440×900), mobile.png (390×844), user-viewport.png (1280×720). DESIGN.md owns visual guidance; PRODUCT.md owns product behavior. -->
