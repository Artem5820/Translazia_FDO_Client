from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import VideoAnalyzer
from .config import AnalyzerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Анализ записи VK-трансляции с сохранением результата в JSON или JSONL.")
    parser.add_argument("--video", required=True, help="Путь к видеофайлу.")
    parser.add_argument("--output", required=True, help="Путь к выходному JSON/JSONL-файлу.")
    parser.add_argument("--sample-interval", type=float, default=2.0, help="Шаг анализа по времени в секундах.")
    parser.add_argument("--device", default=None, help="Устройство для YOLO, например `cpu` или `0`.")
    parser.add_argument("--person-conf", type=float, default=0.25, help="Порог уверенности для детекции человека.")
    parser.add_argument(
        "--person-weights",
        nargs="*",
        default=None,
        help="Необязательный список весов для детектора человека. Если не задано, будут использованы встроенные кандидаты.",
    )
    parser.add_argument("--layout-weights", default=None, help="Необязательные веса YOLO для VK-специфичных классов.")
    parser.add_argument(
        "--mute-templates-dir",
        default=None,
        help="Необязательная папка с PNG-шаблонами белой иконки выключенного микрофона.",
    )
    parser.add_argument(
        "--format",
        choices=("alerts", "full", "events", "live-events"),
        default="alerts",
        help="`alerts` — компактный JSON, `full` — полный JSON, `events` — итоговые события, `live-events` — JSONL-события по ходу анализа.",
    )
    parser.add_argument(
        "--only-on-problem",
        action="store_true",
        help="Не создавать файл, если проблем не было. Для `live-events` файл появляется только после первой подтвержденной проблемы.",
    )
    parser.add_argument("--no-observations", action="store_true", help="Не сохранять покадровые наблюдения в полном JSON.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = AnalyzerConfig(
        sample_interval_sec=args.sample_interval,
        device=args.device,
        person_confidence=args.person_conf,
        person_weights_candidates=tuple(args.person_weights) if args.person_weights else AnalyzerConfig().person_weights_candidates,
        layout_weights=Path(args.layout_weights) if args.layout_weights else None,
        mute_templates_dir=Path(args.mute_templates_dir) if args.mute_templates_dir else None,
        save_observations=not args.no_observations,
    )
    analyzer = VideoAnalyzer(config=config)

    if args.format == "live-events":
        analyzer.analyze_to_live_jsonl(args.video, args.output, only_on_problem=args.only_on_problem)
        return

    analyzer.analyze_to_json(args.video, args.output, output_format=args.format, only_on_problem=args.only_on_problem)


if __name__ == "__main__":
    main()
