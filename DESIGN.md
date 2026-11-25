---
name: Aniweb
description: Your anime list as a night sky of connected points, in a compact dark interface
colors:
  polestar-blue: "#4f8cff"
  comet-blue: "#7aa2ff"
  chart-blue: "#3987e5"
  ember: "#ff8a4f"
  nebula: "#c85cff"
  aurora: "#26c6a2"
  sunlight: "#ffd166"
  violet-line: "#7f5af0"
  go-green: "#3ddc84"
  verdict-green: "#4cc38a"
  stop-red: "#ff4f6a"
  nay-red: "#f06a6a"
  danger-red: "#c9364d"
  blush: "#ff7eb6"
  amber: "#f5b642"
  status-completed: "#199e70"
  status-watching: "#3987e5"
  status-on-hold: "#c98500"
  status-plan-to-watch: "#9085e9"
  status-dropped: "#e66767"
  status-none: "#5c6270"
  midnight: "#0f1117"
  dusk-panel: "#171a23"
  nightfall: "#1d2130"
  twilight-control: "#20242f"
  horizon: "#2a2f3d"
  field-edge: "#6d768b"
  haze: "#8d99ae"
  moonlight: "#c9c9c9"
  starlight: "#e6e6e6"
  white: "#ffffff"
typography:
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.1
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    letterSpacing: "0.5px"
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 700
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  reading:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  small:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    letterSpacing: "0.4px"
rounded:
  thumb: "4px"
  control: "6px"
  inner: "8px"
  panel: "10px"
  popover: "12px"
  float: "14px"
  pill: "20px"
spacing:
  xs: "4px"
  sm: "8px"
  gap: "12px"
  page: "20px"
components:
  button:
    backgroundColor: "{colors.twilight-control}"
    textColor: "{colors.starlight}"
    rounded: "{rounded.control}"
    padding: "4px 8px"
  button-primary:
    backgroundColor: "{colors.polestar-blue}"
    textColor: "{colors.midnight}"
    rounded: "{rounded.control}"
    padding: "4px 8px"
  button-danger:
    backgroundColor: "{colors.danger-red}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  chip:
    backgroundColor: "{colors.twilight-control}"
    textColor: "{colors.starlight}"
    rounded: "{rounded.popover}"
    padding: "2px 7px"
  panel:
    backgroundColor: "{colors.dusk-panel}"
    rounded: "{rounded.panel}"
    padding: "12px 14px"
  game-card:
    backgroundColor: "{colors.dusk-panel}"
    textColor: "{colors.starlight}"
    rounded: "{rounded.float}"
    padding: "12px"
  popover:
    backgroundColor: "{colors.nightfall}"
    textColor: "{colors.starlight}"
    rounded: "{rounded.popover}"
    padding: "6px"
  floating-button:
    textColor: "{colors.starlight}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "40px"
  search-box:
    textColor: "{colors.starlight}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "40px"
---

# Design System: Aniweb

## Overview

**Creative North Star: "The Night Sky Chart"**

Aniweb is a chart of a night sky. Anime, characters and people are points of light on a near-black field, and the lines
between them are the constellations. The background stays dark and even so the points can be read, and almost all of the
colour on screen belongs to a node, a connection, a list status or a piece of cover art.

The voice is playful and dark. The interface is compact, and its energy comes from the games, the cards and the covers.
Controls float over the chart in translucent dark panels and leave the middle of the screen to the graph.

The system rejects three looks. It isn't a busy fan site with banners, cluttered sidebars or mascots. It isn't neon
cyberpunk with glowing text, neon gradients or scanlines. It isn't a corporate dashboard with white cards and pale blue.

**Key Characteristics:**
- A single dark theme on a near-black background
- Colour used as a code for kinds of nodes, connections and list statuses
- Cover art and character portraits as the main imagery
- Compact controls in the system typeface
- Translucent, blurred controls floating over a full-screen canvas

## Colors

The palette is a cool, near-black night with one blue for action and a set of bright, coded colours for the data.

### Primary
- **Polestar Blue** (#4f8cff): Links, primary buttons, selected tabs and chips, hovered and focused outlines, and progress
  bars. It's also the colour of anime nodes and related-anime lines.
- **Comet Blue** (#7aa2ff): The trail the Ask agent draws while it works, and what each step found.

### Secondary
Node and connection colours. They identify a kind of thing wherever it appears.
- **Ember** (#ff8a4f): Characters, and lines from anime to their characters.
- **Nebula** (#c85cff): People, and voice lines.
- **Violet Line** (#7f5af0): Staff lines.
- **Aurora** (#26c6a2): Studios, and lines to them.
- **Sunlight** (#ffd166): The user, lines to their list, status messages, and unfetched nodes.

### Tertiary
Colours with a fixed meaning.
- **List statuses:** completed (#199e70), watching (#3987e5), on hold (#c98500), plan to watch (#9085e9), dropped (#e66767)
  and none (#5c6270). They're used for node rings, chips and charts.
- **Chart Blue** (#3987e5): Bars in Insights.
- **Go Green** (#3ddc84): The start of a path, the Golf solution, and list status text.
- **Stop Red** (#ff4f6a): Errors, the end of a path, the Golf hole, and Kill.
- **Verdict Green** (#4cc38a), **Nay Red** (#f06a6a) and **Amber** (#f5b642): Results in the games.
- **Blush** (#ff7eb6): Kiss in Kiss Marry Kill, next to Sunlight for Marry.
- **Danger Red** (#c9364d): Buttons that delete data.

### Neutral
- **Midnight** (#0f1117): The page and canvas background, the outline around node labels, and text on Polestar Blue.
- **Dusk Panel** (#171a23): Panels, cards, page headers and the Ask drawer.
- **Nightfall** (#1d2130): Popovers, menus, tooltips and search results.
- **Twilight Control** (#20242f): Buttons, inputs, chips, and the space behind missing images.
- **Horizon** (#2a2f3d): Borders, dividers, and hovered rows in menus.
- **Field Edge** (#6d768b): Borders of text fields and dropdowns, at 3:1 or more on every surface.
- **Haze** (#8d99ae): Secondary text and labels, and genres.
- **Moonlight** (#c9c9c9): Long supporting text.
- **Starlight** (#e6e6e6): Main text.
- **White** (#ffffff): Text on Danger Red buttons, and the ring of selected nodes and paths.

### Named Rules
**The Coded Colour Rule.** A colour that stands for a kind of node, a connection or a list status keeps that meaning on
every page.

**The Dark Text on Blue Rule.** Text on Polestar Blue is Midnight, at 5.9:1. White on it only reaches 3.2:1.

**The Dark Sky Rule.** Large surfaces use the neutrals. Bright colour appears in points, lines, rings, bars and controls.

## Typography

**Display Font:** system-ui (with -apple-system, Segoe UI, Roboto and sans-serif)
**Body Font:** the same system stack

**Character:** One system typeface at small sizes. It reads as a tool, and size and weight do all the work.

### Hierarchy
- **Display** (600, 30px, 1.1): The large figures in Insights. Taste match shows its score at 44px.
- **Headline** (700, 20px, 0.5px spacing): Page titles in the app. Text pages use 28px.
- **Title** (700, 16px): Section and node card titles.
- **Body** (400, 13px): The default for the interface.
- **Reading** (400, 15px, 1.6): Help and Privacy, in a column up to 600px wide. It's 16px on phones.
- **Small** (400, 12px): Supporting text, tables and card captions. Nothing in the interface is smaller, except
  chart axes at 11px and labels on the canvas, which grow with the zoom.
- **Label** (400, 12px, 0.4px spacing, uppercase): Labels under figures. Small subheadings (bold, 0.6px spacing) use the
  same uppercase style.

### Named Rules
**The Steady Figures Rule.** Numbers that line up in tables, charts and scores use tabular figures.

**The Sixteen Pixel Rule.** Text fields and dropdowns are 16px on touch screens, so iOS doesn't zoom in when they get
focus. Pinch zoom is never turned off.

## Layout

The graph view is a fixed, full-screen canvas with controls pinned 12px from its edges, plus the phone's safe areas.
Search is at the top left, the menu at the top right, Filters at the bottom left, and fit and Ask at the bottom right. The
node card is 340px wide on the right, and the Ask drawer is 420px wide and moves the card and the bottom buttons aside.

Other pages are a single column: 600px for text pages, 900px for games and 1400px for Insights, with 20px side padding. Text
on the game and tour pages is at most 58ch wide, while grids use the full column.
Covers, cards and figures sit in grids that fill the available width. Spacing is tight, mostly in steps of 4, 6, 8, 10, 12
and 14px.

At 700px and below, the node card becomes a bottom sheet, the Ask drawer fills the screen and button labels in the corner
controls are hidden. Page padding drops to 12px. Some grids also change at 900px and 640px.

Controls that stand alone are at least 24px high. On touch screens, chips and plain buttons are at least 36px, and corner
controls, icon buttons and menu rows are 44px. Popovers and the Golf panel scroll rather than run off a short screen.

## Elevation & Depth

The system layers dark tones and lifts whatever floats. Floating controls use a translucent dark fill
(rgba(23, 26, 35, 0.9)) with a 12px blur, a border and a shadow. Panels in the page are flat today, with Dusk Panel on
Midnight and a Horizon border. More layering is welcome, so cards and panels may gain shadows in new work.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45)`): Floating controls, popovers, toasts and the Ask drawer.
- **Menu** (`box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5)`): Search results, context menus and chart tooltips.
- **Selected** (`box-shadow: 0 0 0 2px rgba(79, 140, 255, 0.35)`): The ring around a picked card.

### Named Rules
**The Soft Shadow Rule.** Shadows are dark and soft. They're never coloured and never a glow.

## Shapes

Corners are rounded, and larger things are rounder: 3 to 4px for thumbnails, 6px for controls, 8px for rows and icon
buttons, 10px for panels, 12px for popovers, 14px for floating panels and game cards, and 20px for the pill-shaped search
box and corner buttons. Bottom sheets round only their top corners, at 16px. Borders are 1px, and 2px on game cards.

Covers and portraits keep their upright shape, at 2:3, 3:4 or 225:330, and fill their frame.

On the canvas, shape is a code: rounded rectangles are anime, circles are characters and people, diamonds are studios and
genres, and a star is the user. A dashed outline marks a node that hasn't been fetched or that Ask added while working.

## Components

Components are compact and tactile. They're small, and they respond clearly when touched.

### Buttons
- **Shape:** gently curved (6px).
- **Default:** Twilight Control with a Horizon border and 4px 8px padding.
- **Primary:** Polestar Blue with bold (600) Midnight text. It brightens by 10% on hover.
- **Danger:** Danger Red with white text, 36px high. It darkens by 8% on hover.
- **Hover:** the border turns Polestar Blue. Disabled buttons fade to 40%.
- **Selected:** Polestar Blue border and text.
- **Floating:** 40px high pills with the translucent fill and the Float shadow.
- **Icon buttons:** 32px square with 8px corners. The quiet version has no fill and uses Haze until hovered.

### Chips
- **Style:** 12px text on Twilight Control, a Horizon border, 12px corners, and an 8px dot of the colour they stand for.
- **State:** selected chips have a Polestar Blue border. Unselected ones have no fill, a Horizon border and Haze text, and
  their dot fades to 35%.

### Cards / Containers
- **Corner Style:** 10px, or 14px for game cards.
- **Background:** Dusk Panel.
- **Shadow Strategy:** flat today, with room for layering (see Elevation & Depth).
- **Border:** 1px Horizon, or 2px on game cards.
- **Internal Padding:** 8 to 14px. Cards that lead with a cover let it fill the card's width.

### Inputs / Fields
- **Style:** Twilight Control, a Field Edge border and 6px corners. The search box is a 40px floating pill.
- **Placeholder:** Haze.
- **Focus:** the search box border turns Polestar Blue. Everything else that takes keyboard focus gets a 2px Polestar Blue ring.
- **Picking a path end:** the search box border turns Go Green.

### Navigation
- A popover menu at the top right lists the pages, with rounded rows that turn Horizon on hover.
- Other pages start with a link back to the graph.
- Tabs inside a page are chips or a segmented control whose selected part is filled with Polestar Blue.

### The graph canvas
- Anime nodes are 36 by 48px and show their cover. Characters and people are 28px circles with portraits.
- The ring colour is the list status. Selected nodes, paths and neighbours get a white ring.
- Lines are 1.5px at 60% opacity with a small arrow. On a path they're 3px at full opacity and show their label.
- Anything outside the current focus fades to 15 or 20%.

### Game cards
- A portrait, a bold name up to two lines long and a one-line anime title, with the choices pinned to the bottom.
- Hover turns the border Polestar Blue over 0.15s, and pressing shrinks the card to 98%.
- Results colour the border: Verdict Green for right, Stop Red for wrong, and Nay Red for nay.
- Yay or Nay cards are dragged, show a rotated stamp, and settle back over 0.18s.

### Motion
- Motion is short (0.1 to 0.4s) and shows what changed: a press, a card leaving, a new clue, the graph settling.
- For people who prefer reduced motion, the graph and the scrolling jump into place, a Yay or Nay card fades where it is,
  and new clues fade in. Colours and fades that confirm an action stay.

## Do's and Don'ts

### Do:
- **Do** keep the background Midnight (#0f1117) and let covers, portraits and nodes bring the colour.
- **Do** reuse the colour a kind of node, connection or status already has.
- **Do** give controls over the canvas the translucent fill, 12px blur, border and Float shadow.
- **Do** keep 12px plus the safe area between floating controls and the edge of the screen.
- **Do** make presses visible, as the game cards do.
- **Do** use tabular figures where numbers line up.

### Don't:
- **Don't** make it look like a busy fan site with crowded banners, cluttered sidebars or mascot decoration.
- **Don't** use neon cyberpunk effects such as glowing text, neon gradients or scanlines.
- **Don't** make it look like a corporate dashboard with white cards and pale blue accents.
- **Don't** use a coded colour for decoration.
- **Don't** let controls cover the middle of the canvas while the visitor explores it.
