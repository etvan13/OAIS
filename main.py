"""Launch OAIS with a connected test terminal, or either terminal alone.

From the project directory (whatever it is named): python main.py
"""

import argparse
from pathlib import Path
from oais.meta_terminal import OAISRuntime



def main(argv=None):
    parser = argparse.ArgumentParser(description="OAIS terminal prototype")
    parser.add_argument("--mode", choices=("connected", "oais", "base"),
                        default="connected", help="Which terminal input loop to run")
    parser.add_argument("--start", default="0 0 0 0 0 0",
                        help='Starting coordinate; e.g. "59 0 0 0 0 0"')
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Isolated OAIS data directory for prototype saves")
    args = parser.parse_args(argv)

    runtime = OAISRuntime(starting_coordinate=args.start, data_dir=args.data_dir)
    if args.mode == "connected":
        runtime.run()
    elif args.mode == "oais":
        runtime.oais.connected = False
        runtime.oais.run()
    else:
        runtime.host.run()
    return runtime


if __name__ == "__main__":
    main()
