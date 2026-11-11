# Latifa El Amrani: character profile card

A 16:9 (1920×1080) character card: portrait on the left, and a dark navy info panel with gold
typography on the right.

| File | What it is |
|------|------------|
| `latifa-card.png` | The rendered card |
| `index.html` | Source: open in a browser and it scales to fit the window |
| `render.js` | Re-renders the PNG with Playwright (`node render.js`) |
| `prompt.md` | Prompt for generating a photorealistic portrait to replace the illustration |

The portrait is an SVG illustration. If a `portrait.jpg` sits next to `index.html`, the card
shows that photo instead. See `prompt.md`.
