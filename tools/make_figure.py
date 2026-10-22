"""README figure: what by_decade returns, with real answers of the API (saved in tools/sample_answers.json).

    python tools/make_figure.py             # offline, from the saved answers
    python tools/make_figure.py --fetch     # ask the API again and save the answers
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "tools" / "sample_answers.json"
DECADES = ["before_1930", "1930s", "1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s"]
LABELS = ["<1930", "1930s", "1940s", "1950s", "1960s", "1970s", "1980s", "1990s", "2000s"]
INK, MUTED, GRID = "#1f1f1f", "#666666", "#e6e6e6"
COLORS = {"total": "#2a78d6", "F": "#d6452a"}
for family in ("Inter", "DejaVu Sans"):
    try:
        matplotlib.font_manager.findfont(family, fallback_to_default=False)
        plt.rcParams["font.family"] = family
        break
    except ValueError:
        continue


def fetch() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from ibge_nomes import IbgeNomes

    ibge = IbgeNomes()
    names = ["Maria", "Caique"]
    data = {"total": ibge.by_decade(names), "F": ibge.by_decade(names, sex="F")}
    SAMPLE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


TEXT = {
    "en": {"title": "ibge.by_decade(): people alive in 2010, by decade of birth",
           "sub": "Real answers of IBGE's names API (2010 Census). Caique: everyone and women only.",
           "units": ("millions", "thousands"), "all": "all", "note": "no count published\nbefore the 1960s",
           "first": "<1930", "suffix": ""},
    "pt": {"title": "ibge.by_decade(): pessoas vivas em 2010, por década de nascimento",
           "sub": "Respostas reais da API de nomes do IBGE (Censo 2010). Caique: todos e só mulheres.",
           "units": ("milhões", "milhares"), "all": "todos", "note": "sem contagem publicada\nantes dos anos 60",
           "first": "<1930", "suffix": ".pt-BR"},
}


def main() -> None:
    data = fetch() if "--fetch" in sys.argv else json.loads(SAMPLE.read_text(encoding="utf-8"))
    for lang, t in TEXT.items():
        draw(data, t)


def draw(data: dict, t: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=110)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.78, bottom=0.14, wspace=0.18)
    fig.text(0.02, 0.93, t["title"], fontsize=15, weight="bold", color=INK)
    fig.text(0.02, 0.86, t["sub"], fontsize=10.5, color=MUTED)
    for ax, name, scale, unit in ((axes[0], "MARIA", 1e6, t["units"][0]), (axes[1], "CAIQUE", 1e3, t["units"][1])):
        total = [data["total"].get(name, {}).get(d, 0) / scale for d in DECADES]
        women = [data["F"].get(name, {}).get(d, 0) / scale for d in DECADES]
        x = range(len(DECADES))
        if name in data["F"]:
            ax.bar([i - 0.2 for i in x], total, width=0.4, color=COLORS["total"], label=t["all"])
            ax.bar([i + 0.2 for i in x], women, width=0.4, color=COLORS["F"], label='sex="F"')
            ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 0.8))
        else:
            ax.bar(list(x), total, width=0.6, color=COLORS["total"])
        ax.set_xticks(list(x))
        ax.set_xticklabels(LABELS, fontsize=9, color=INK)
        ax.set_title(f"{name.title()}  ({unit})", loc="left", fontsize=12, color=INK)
        ax.grid(axis="y", color=GRID)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.tick_params(left=False, labelsize=9, colors=MUTED)
    axes[1].text(0.02, 0.95, t["note"], transform=axes[1].transAxes, fontsize=9, color=MUTED, va="top")
    out = ROOT / "docs" / "img" / f"by_decade{t['suffix']}.png"
    fig.savefig(out, facecolor="white")
    print(out)


if __name__ == "__main__":
    main()
