"""OAIS launcher: choose how OAIS connects without involving a Meta prompt.

  python main.py                          # BASE connected to OAIS
  python main.py --connection counterless # Demo host with no Counter
  python main.py --connection standalone  # OAIS by itself
  python main.py --mode base              # BASE by itself (legacy option)
"""
import argparse
from pathlib import Path
from meta.meta_terminal import MetaTerminal


def main(argv=None):
    parser = argparse.ArgumentParser(description="OAIS terminal prototype")
    parser.add_argument("--connection", default="base",
                        help="Registered connection method chosen by Meta")
    parser.add_argument("--mode", choices=("connected", "oais", "base"),
                        default=None, help="Legacy launch modes")
    parser.add_argument("--start", default="0 0 0 0 0 0",
                        help='Starting coordinate for BASE; e.g. "59 0 0 0 0 0"')
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="OAIS data directory (does not relocate BASE data)")
    parser.add_argument("--base-data-dir", type=Path, default=None,
                        help="Optional isolated BASE data directory")
    parser.add_argument("--alternate-screen", action="store_true",
                        help="Use separate OAIS screen instead of normal scrollback")
    args = parser.parse_args(argv)
    meta = MetaTerminal(starting_coordinate=args.start, data_dir=args.data_dir,
                        base_data_dir=args.base_data_dir, alternate_screen=args.alternate_screen)
    if args.mode == "base":
        from meta.Connections.Base import BaseConnection
        BaseConnection(meta).run_standalone()
    else:
        selected = ("standalone" if args.mode == "oais" else args.connection)
        meta.run(selected)
    return meta


if __name__ == "__main__":
    main()
