"""Retired preparation child entry point. Never consumes input or starts work.

An old launcher cannot execute the former unbounded startup/reap implementation.
No financial context is read or printed.
"""


def main():
    raise SystemExit(2)


if __name__ == "__main__":
    main()
