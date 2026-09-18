"""hoofprints の最小CLI。

F1時点では `agentkit.bootstrap()` がアプリ側から実際に使えることを確認する
`doctor` コマンドのみを持つ。scout/run 等は該当するノード実装（P1以降）が
揃ってから追加する。
"""

from __future__ import annotations

import argparse
import sys

from agentkit import Zone, bootstrap


def _doctor(zone: Zone) -> int:
    ctx = bootstrap(zone, app="hoofprints")
    ctx.store.healthcheck()
    print(f"OK: zone={ctx.zone.value} app={ctx.app} — DB接続を確認しました")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hoofprints")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="bootstrap()とDB疎通を確認する（F1動作確認用）"
    )
    doctor_parser.add_argument("--zone", choices=[z.value for z in Zone], default=Zone.DEV.value)

    args = parser.parse_args(argv)

    if args.command == "doctor":
        sys.exit(_doctor(Zone(args.zone)))


if __name__ == "__main__":
    main()
