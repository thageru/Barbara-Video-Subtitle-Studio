# Barbara Video Subtitle Studio Design System

## Product Direction

Barbara Video Subtitle Studio is a local production workspace, not a marketing page. The interface keeps generation, translation, preview, export, editing, and job status in one focused screen while making local-only processing explicit.

## Visual Language

- Base background: `#0b1114`; fallback surface: `#10191c`.
- Main panels use dark translucent glass with restrained blur, thin white borders, and high-contrast text.
- Accent: `#a9f0df`; destructive and failure states use red, while shutdown confirmation uses amber.
- Standard controls use 12px radius; repeated rows remain unframed and separated by borders.
- Spacing follows a 4px rhythm. Controls have stable dimensions so loading and status changes do not move the layout.
- Geist is requested from Google Fonts. Apple system fonts and Segoe UI are the offline fallback when the font request is unavailable.
- The background video is decorative. If it cannot load, the application keeps the same hierarchy on a static dark background.

## Interaction Rules

- Interactive controls have a minimum height of 44px and visible keyboard focus.
- Buttons use Lucide icons for recognizable actions such as power, play, pause, folders, video, and subtitles.
- Long-running actions disable their trigger and show a loading indicator without changing the control size.
- Completion and failure notices use live regions; errors use `role="alert"`.
- Manual shutdown requires an in-app confirmation and ends on a non-interactive stopped state.
- Closing the final workbench page stops the local service after a grace period. Refreshes, internal navigation, other open tabs, and active jobs must not cause accidental shutdown.
- Motion is limited to short state transitions and loading indicators, and respects `prefers-reduced-motion`.

## Responsive Rules

- Desktop uses a two-column composition with the workflow context beside the active tool panel.
- At smaller widths, navigation moves into a menu and form fields stack without horizontal page overflow.
- Fixed-format media previews keep a 16:9 aspect ratio; job rows and subtitle editor tables scroll within their own containers when necessary.
- Text must wrap within controls and panels. Font sizes remain breakpoint-based rather than scaling continuously with viewport width.
- Letter spacing is zero across body, interface, and display copy.

## Workflow Structure

1. Generate timing-accurate English subtitles.
2. Copy a translation prompt and import a complete translated SRT.
3. Preview timing and placement, then export sidecar or hard-burned subtitles.
4. Remove embedded soft-subtitle streams when required.
5. Edit an existing subtitle while preserving indexes and timecodes.
6. Review job progress, completion, and errors.

The standalone subtitle editor keeps source timing beside editable text, with output settings above and a persistent save action below.
