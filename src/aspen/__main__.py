"""
The main entry point for the application.
"""

import logging
import sys
import traceback

from .cli import CLI_ERRORS
from .utils.log import configure_logging
from .utils.parser import get_parser


def main() -> None:
    """
    Run the main function.
    """
    parser = get_parser()
    args = parser.parse_args()
    configure_logging(sys.stderr, args.log, sys.stderr.isatty())

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except CLI_ERRORS as exc:
        if args.log <= logging.DEBUG:
            traceback.print_exc()
        else:
            print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
