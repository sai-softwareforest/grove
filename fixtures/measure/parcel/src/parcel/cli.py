"""The `parcel` command."""

import argparse

from .rates import quote


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parcel")
    commands = parser.add_subparsers(dest="command", required=True)
    quote_command = commands.add_parser("quote", help="print the price of one box")
    quote_command.add_argument("weight", type=float)
    quote_command.add_argument("--zone", choices="ABCD", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(quote(args.weight, args.zone))
    return 0
