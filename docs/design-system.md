# Barbara-Video-Subtitle-Studio Design System

## Product Direction

Barbara-Video-Subtitle-Studio is a local production tool, not a marketing site. The interface favors clear workflow order, compact forms, predictable feedback, and long-session readability.

## Visual Language

- Background: `#f2f4f7`
- Surface: `#ffffff`
- Primary text: `#17202a`
- Secondary text: `#66717f`
- Primary action: `#176b66`
- Secondary action: `#25384a`
- Warning: `#a65f00`
- Destructive: `#b42318`
- Border: `#dce1e7`; control border: `#c7ced7`
- Radius: 6px for controls, 8px for major surfaces
- Spacing follows a 4px/8px rhythm, with 14-22px section padding

Use the system font stack so the local UI has no font download or network dependency.

## Interaction Rules

- Interactive controls have a minimum height of 44px.
- Keyboard focus uses a visible teal focus ring.
- Primary, secondary, ghost, and destructive actions remain visually distinct.
- Long-running form submissions immediately disable the submit button and show a working state.
- Completion and failure messages use `aria-live="polite"`; errors use `role="alert"`.
- Motion is limited to 150ms state transitions and respects `prefers-reduced-motion`.

## Responsive Rules

- Desktop content width is capped at 1240px on the main workspace and 1400px in the subtitle editor.
- At 760px and below, forms become single-column and inputs use a 16px font size.
- Workflow navigation stays reachable as a horizontally scrollable strip on narrow screens.
- Wide job and subtitle tables scroll inside their own containers; the page itself must not overflow horizontally.

## Page Structure

1. Generate English subtitles.
2. Translate subtitles.
3. Preview and export.
4. Edit an existing subtitle.
5. Review job history and status.

The subtitle editor keeps source timing visible beside the editable text, with output settings above and a persistent save action below.
