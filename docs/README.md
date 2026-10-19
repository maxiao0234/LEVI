# Project website

Static project website for LEVI: paper overview, leaderboard and model comparisons.

Project website: [maxiao0234.github.io/LEVI](https://maxiao0234.github.io/LEVI/). GitHub Pages serves `main/docs`.

Hugging Face downloads are coming soon.

Preview from the repository root:

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory docs
```

- `index.html`, `style.css`, `app.js`: layout and interactions.
- `results.json`: reported leaderboard values.
- `examples.json`: case descriptions and evaluation labels.
- `assets/`: display images, vector schematics, resource badges and paper PDF.

Display images are resized model outputs. The selected cases illustrate identity requirements and model behavior; they are not a sample for estimating failure frequencies.

The layout draws on [Nerfies](https://nerfies.github.io/) and academic project-page conventions. Resource badges use [Shields.io](https://shields.io/badges/static-badge), following the compact entry style used by [T2I-CompBench](https://github.com/Karine-Huang/T2I-CompBench).

The site is self-contained and can be served directly from this directory.
