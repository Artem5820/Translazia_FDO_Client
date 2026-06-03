from __future__ import annotations

from pathlib import Path
import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


def save_spectrogram(samples: np.ndarray, sample_rate: int, output_path: str | Path) -> Path:
    """Save a logarithmic spectrogram image for visual audio inspection."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 5), dpi=140)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="divide by zero encountered in log10")
        ax.specgram(
            samples,
            NFFT=1024,
            Fs=sample_rate,
            noverlap=768,
            cmap="magma",
            scale="dB",
            mode="magnitude",
        )
    ax.set_title("Audio spectrogram")
    ax.set_xlabel("Time, sec")
    ax.set_ylabel("Frequency, Hz")
    ax.set_ylim(0, min(8000, sample_rate / 2))
    fig.colorbar(ax.images[0], ax=ax, label="Level, dB")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

    return path
