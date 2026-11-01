COMING SOON PAGE
================

Files:
  index.html        - the page (pure black, white text, ASCII status line)
  logo.png          - your logo, trimmed to its artwork with a little padding (white on transparency)
  logo-source.png   - the original uploaded file, untouched

Open index.html in any browser. No build step, no dependencies.

To swap the logo:
  Replace logo.png with another image of the same name (transparent PNG or SVG
  works best on black). If the new logo is wide rather than tall, change
  "height" to "width" in the .logo rule in index.html.

Tweaks inside index.html:
  --bg / --fg        background and text colors
  --font             the typeface stack (Google Sans, loaded from Google Fonts)
  .logo height       logo size
  h1                 size, weight, and letter-spacing of "COMING SOON"
  .ascii             the terminal line: size, color, spacing

The ASCII status line:
  A spinner ([|] [/] [-] [\]) ticks every 170ms while the message types
  itself out, pauses, deletes, and moves to the next one, with a blinking "_"
  cursor. Edit the "messages" array inside the <script> tag to change the
  wording - keep lines roughly the same length so the layout stays balanced.
  Visitors who prefer reduced motion get a static line and no cursor.
  A small ASCII banner also prints in the browser console.

About the font:
  Google Sans is loaded from Google's Fonts CDN, but it is not listed on
  fonts.google.com, so it only works through the <link> in index.html.
  Weights available: 400, 500, 700 (there is no light 300 weight).
  The page currently uses 400 with modest tracking.
  If the CDN ever stops serving it, the page falls back to Roboto /
  Helvetica / Arial, so nothing breaks.

Deploying:
  Upload this folder as-is to Netlify, Vercel, GitHub Pages, or any static host.
