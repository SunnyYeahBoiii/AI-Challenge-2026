---
name: Lumina Search System
colors:
  surface: '#f9f9fc'
  surface-dim: '#dadadc'
  surface-bright: '#f9f9fc'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f6'
  surface-container: '#eeeef0'
  surface-container-high: '#e8e8ea'
  surface-container-highest: '#e2e2e5'
  on-surface: '#1a1c1e'
  on-surface-variant: '#3f484c'
  inverse-surface: '#2f3133'
  inverse-on-surface: '#f0f0f3'
  outline: '#6f787d'
  outline-variant: '#bfc8cd'
  surface-tint: '#0c6780'
  primary: '#0c6780'
  on-primary: '#ffffff'
  primary-container: '#87ceeb'
  on-primary-container: '#005870'
  inverse-primary: '#89d0ed'
  secondary: '#0058bc'
  on-secondary: '#ffffff'
  secondary-container: '#0070eb'
  on-secondary-container: '#fefcff'
  tertiary: '#5c5f61'
  on-tertiary: '#ffffff'
  tertiary-container: '#c2c5c7'
  on-tertiary-container: '#4e5254'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#baeaff'
  primary-fixed-dim: '#89d0ed'
  on-primary-fixed: '#001f29'
  on-primary-fixed-variant: '#004d62'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a41'
  on-secondary-fixed-variant: '#004493'
  tertiary-fixed: '#e0e3e5'
  tertiary-fixed-dim: '#c4c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#f9f9fc'
  on-background: '#1a1c1e'
  surface-variant: '#e2e2e5'
typography:
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
  mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar-width: 320px
  topbar-height: 64px
  gutter: 16px
  container-padding: 24px
  stack-gap: 12px
---

## Brand & Style

The brand personality for this design system is functional, precise, and unobtrusive. It is designed for power users who need to process vast amounts of visual data quickly. The UI stays out of the way, acting as a high-performance tool rather than a decorative interface.

The design style is **Modern / Corporate**, leaning into heavy functionalism. It utilizes a clean "Application Shell" model with clear containment and systematic information density. It prioritizes clarity through whitespace and consistent alignment, ensuring that the primary focus remains on the video frame results.

## Colors

The palette is anchored by a high-clarity Sky Blue primary color, used exclusively for actionable elements and active states. 

- **Primary (#87CEEB):** Used for primary action buttons, active toggles, and selection indicators.
- **Secondary (#007AFF):** Reserved for links and critical interactive states requiring higher contrast against white backgrounds.
- **Surface Neutrals:** A range of cool-toned grays are used to differentiate the sidebar (#F5F7F9) from the main workspace (#FFFFFF).
- **Semantic Colors:** Standard red for destructive actions (like removing a query card) and green for successful submission status.

## Typography

This design system uses **Inter** for all UI elements to ensure maximum legibility at small sizes. For technical data—such as Frame IDs, Video IDs, and timestamps—**JetBrains Mono** is used to provide clear character differentiation (e.g., distinguishing '0' from 'O').

Typography is intentionally kept small (ranging from 11px to 18px) to maximize information density. Hierarchy is established through font weight (SemiBold for labels/headers) rather than significant jumps in scale.

## Layout & Spacing

The layout follows a strict **Fixed Sidebar / Fluid Main** model. 

1. **Sidebar (A):** A fixed 320px panel on the left. It uses a vertical stack with 12px gaps between query cards.
2. **Top Bar (C):** A fixed 64px header that contains global submission controls and system settings.
3. **Main Content (B):** A fluid, responsive grid area. It uses an 8-column grid on desktop, scaling down to 4 columns on tablet.
4. **Spacing Rhythm:** Based on a 4px baseline. All internal component padding uses 8px or 12px increments to maintain a compact, "pro-tool" feel.

## Elevation & Depth

This design system uses **Tonal Layering** rather than heavy shadows to define depth.

- **Level 0 (Background):** The main canvas uses a pure white (#FFFFFF) background.
- **Level 1 (Panels):** Sidebars and headers use a subtle off-white/light-gray (#F5F7F9) with a 1px border (#E1E4E8) to separate them from the canvas.
- **Level 2 (Cards):** Query cards and input clusters use a white fill with a soft 1px border. A very subtle, diffused shadow (0px 2px 4px rgba(0,0,0,0.05)) is applied only when a card is being dragged or is currently active.
- **Overlays:** Modals and dropdowns use a crisp 1px border and a medium shadow (0px 8px 24px rgba(0,0,0,0.12)).

## Shapes

The shape language is controlled and modern. A standard **8px (rounded-md)** corner radius is applied to all primary containers, including buttons, input fields, and query cards. 

Thumbnails in the results grid use a slightly smaller **4px** radius to maximize the visible area of the video frame. Interactive tags or chips within query cards use a fully pill-shaped (100px) radius to distinguish them from input fields.

## Components

### Query Cards
Cards are the primary unit of work. They feature a header row with a toggle (Enable/Disable), a drag handle, and a delete icon. The body contains a multi-line text area or an image upload preview. Footer sections contain expandable "Tags" and "Keywords" accordions.

### Input Fields
Inputs use a "Flat-Inlay" style: a subtle #F5F7F9 background with a bottom-only border that transitions to a full 1px primary-colored border on focus. Labels are positioned above the input in `label-md` uppercase.

### Buttons
- **Primary:** Solid #87CEEB fill with white text.
- **Secondary/Ghost:** No fill, 1px #E1E4E8 border.
- **Actionable Icons:** 32x32px hit area with icons centered.

### Result Grid
Result thumbnails include a hover state that reveals a "Play" icon overlay and a "Select" checkbox in the top-right corner. Metadata (Frame ID) appears below the thumbnail in `mono-sm` font.