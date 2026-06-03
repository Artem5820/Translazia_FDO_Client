from __future__ import annotations

import sys


def main() -> int:
    try:
        from translazia_client.app import run
    except ModuleNotFoundError as exc:
        missing = exc.name or "dependency"
        print(
            "Не хватает зависимости для desktop-клиента: "
            f"{missing}\nУстановите зависимости командой: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
