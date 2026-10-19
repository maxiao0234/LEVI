# Project website

Static project website for LEVI: paper overview, leaderboard and model comparisons.

Project address: `https://maxiao0234.github.io/LEVI/`. Deployment is not enabled.

Preview from the repository root:

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory docs
```

- `index.html`, `style.css`, `app.js`: layout and interactions.
- `results.json`: reported leaderboard values.
- `examples.json`: case descriptions and original outcome labels.
- `assets/`: display images, vector schematics, resource badges and paper PDF.

The website uses English. Display images are derivatives of archived outputs; the source files and result labels are preserved. Case selections illustrate identity requirements and model differences rather than estimate failure frequencies.

The layout draws on [Nerfies](https://nerfies.github.io/) and academic project-page conventions. Resource badges use [Shields.io](https://shields.io/badges/static-badge), following the compact entry style used by [T2I-CompBench](https://github.com/Karine-Huang/T2I-CompBench). No reference project's research content, images or results are copied.

The site is self-contained and can be served directly from this directory.
