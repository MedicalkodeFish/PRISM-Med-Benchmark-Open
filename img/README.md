# Figures for README

| File | Use |
|------|-----|
| `flowchart.pdf` | Benchmark / three-pillar pipeline (source) |
| `flowchart.png` | Embedded in root `README.md` (generated) |
| `benchmark_scores.pdf` | Model score leaderboard (source) |
| `benchmark_scores.png` | Embedded in root `README.md` (generated) |

GitHub renders **PNG** in README; PDFs are linked for print-quality viewing.

Regenerate PNGs after editing PDFs:

```powershell
python .\tools\render_readme_figures.py
```

Then re-export the open-source tree if needed (`tools/export_opensource_release.py`).
