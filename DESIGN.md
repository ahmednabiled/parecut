# Parecut Design Direction

Owner-supplied direction, formatted for implementation. The owner is the author;
this file only records it.

## Identity

Parecut is a professional audio and rough-cut tool for editors who work in dark
suites for long sessions. The interface should read like a precision instrument:
monochrome, dense where it matters, and quiet everywhere else. Material Design 3
supplies the role system; the palette is deliberately black and white.

## Dials

- **ENERGY 2** — confident, not loud. One focal point per screen.
- **RHYTHM 3** — vary composition: split auth, asymmetric summary band, list-based
  job detail. Never three identical cards.
- **MOTION 2** — state transitions only, short and physical. No ambient animation.

## Color roles (M3, monochrome)

| Role | Value | Use |
|---|---|---|
| `surface` | `#0A0A0A` | Page ground |
| `surface-container-lowest` | `#050505` | Wells, inactive tracks |
| `surface-container-low` | `#101010` | Sidebar, secondary panels |
| `surface-container` | `#151515` | Cards, list containers |
| `surface-container-high` | `#1E1E1E` | Hover, active nav indicator |
| `surface-container-highest` | `#282828` | Pressed, strongest container |
| `on-surface` | `#EDEDED` | Primary text |
| `on-surface-variant` | `#B5B5B5` | Secondary text |
| `outline` | `#8A8A8A` | Input borders, strong dividers |
| `outline-variant` | `#333333` | Hairlines |
| `primary` | `#F5F5F5` | Filled buttons, selected state |
| `on-primary` | `#0B0B0B` | Text on filled buttons |
| `error` | `#FFB4AB` | Error text/icon |
| `error-container` | `#3A0A0A` | Error surface |
| `on-error-container` | `#FFDAD6` | Error text on container |

Red is reserved for genuine failure and destructive states. Success is communicated
by a filled white chip and the word, not by green.

## Typography

- **Sans:** Google Sans (400/500/600). **Mono:** IBM Plex Mono.
- Mono is for timecodes, frame numbers, credits, counts, and the wordmark. Never for
  body copy.
- M3-inspired scale:
  - Display/statement: 40/44, weight 600, tracking −0.02em
  - Page title: 32/40, weight 600, tracking −0.02em
  - Section title: 22/28, weight 550
  - Body: 16/26
  - Label: 14/20, weight 500
  - Caption: 12/16
- Line length caps at 65ch for prose.
- One tracked-caps role only: the `PARECUT` wordmark. Everything else is sentence case.

## Shape

| Element | Radius |
|---|---|
| Text field, small control | 4px |
| Chip, status pill | 8px |
| Card, panel, list container | 12px |
| Sheet, large surface | 16px |
| Filled/outlined button | 20px |
| Navigation active indicator | full pill |

## Elevation and state

No decorative shadows. Depth comes from M3 tonal surface steps. Hover/pressed states
use a white state layer at 6–10% over the current surface. Focus is a 2px
`on-surface` outline with a 2px offset.

## Motion

- Standard: `cubic-bezier(0.2, 0, 0, 1)` — state changes, 150–200ms.
- Emphasized decelerate: `cubic-bezier(0.05, 0.7, 0.1, 1)` — entrances, 250ms.
- Animate only color, background, border, opacity, transform.
- Respect `prefers-reduced-motion`.

## Icons

Material Symbols Rounded, self-hosted. Use an icon only when it adds meaning; lists,
metrics, and settings sections do not need decoration.

## Brand assets

Owner-supplied profile assets, self-hosted in `web/public/brand/`:

- `login-logo.png` — the full Pare Cut script mark, used on auth pages and in the
  app sidebar with no separate wordmark beside it.
- `cover.webp` — the profile cover in its original colors, used once as the
  dashboard banner above the page content.
- `favicon.png` — the P mark on a surface-colored square.

The cover is never used as a page background and never tinted. The logo is never
recreated or redrawn.

## Constraints

- No gradients, glass, glow, or mesh backgrounds.
- No purple/amber accent. Monochrome plus error red.
- No invented logos, avatars, testimonials, or statistics.
- Placeholder surfaces say "Coming soon" rather than pretending to be finished.
