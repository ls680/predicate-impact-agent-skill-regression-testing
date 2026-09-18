"""Create the 50 mm x 60 mm STVR graphical table-of-contents image."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parent
MM_PER_INCH = 25.4


def box(axis, x, y, width, height, color, text, text_color="#17212b", size=8.0):
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=1.1,
        edgecolor=color,
        facecolor="white",
    )
    axis.add_patch(patch)
    axis.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        color=text_color,
        fontsize=size,
        weight="bold",
        linespacing=1.08,
    )


def main():
    figure = plt.figure(figsize=(50 / MM_PER_INCH, 60 / MM_PER_INCH))
    axis = figure.add_axes([0, 0, 1, 1])
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    navy = "#17324d"
    teal = "#087e8b"
    green = "#238636"
    orange = "#c7522a"
    gray = "#5f6b76"

    axis.add_patch(FancyBboxPatch(
        (0.035, 0.855), 0.93, 0.115,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=0,
        facecolor=navy,
    ))
    axis.text(
        0.5, 0.913, "Changed Agent Skill\npredicate  p",
        ha="center", va="center", color="white", fontsize=9.2,
        weight="bold", linespacing=1.0,
    )

    axis.annotate("", xy=(0.5, 0.775), xytext=(0.5, 0.855),
                  arrowprops={"arrowstyle": "-|>", "color": navy, "lw": 1.6})
    box(axis, 0.09, 0.64, 0.82, 0.135, teal,
        "Historical passing traces\nrecord predicate coverage", size=8.0)

    axis.annotate("", xy=(0.5, 0.565), xytext=(0.5, 0.64),
                  arrowprops={"arrowstyle": "-|>", "color": teal, "lw": 1.6})
    box(axis, 0.09, 0.43, 0.82, 0.135, green,
        "Run predicate-covered\ntests first", size=8.6)

    axis.text(0.5, 0.385, "THREE-TEST BUDGET", ha="center", va="center",
              fontsize=7.3, color=gray, weight="bold")
    box(axis, 0.055, 0.205, 0.42, 0.14, green,
        "100%\nmutations\ndetected", text_color=green, size=7.3)
    box(axis, 0.525, 0.205, 0.42, 0.14, orange,
        "55.6%\nexpected for\nfamily random", text_color=orange, size=7.3)

    axis.text(0.5, 0.15, "179 killable mutations", ha="center", va="center",
              fontsize=7.0, color=gray)
    axis.add_patch(FancyBboxPatch(
        (0.055, 0.035), 0.89, 0.075,
        boxstyle="round,pad=0.01,rounding_size=0.02",
        linewidth=0,
        facecolor="#eaf4f1",
    ))
    axis.text(0.5, 0.073, "71-75% fewer full-family replays",
              ha="center", va="center", fontsize=7.5,
              color=navy, weight="bold")

    for suffix in ("pdf", "png"):
        figure.savefig(
            ROOT / f"graphical_toc_image.{suffix}",
            dpi=600,
            facecolor="white",
            bbox_inches=None,
            pad_inches=0,
        )
    plt.close(figure)


if __name__ == "__main__":
    main()
