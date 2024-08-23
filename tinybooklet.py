from typing import TypedDict

import pypdf
import argparse

Ratio = tuple[int, int]

class Args(TypedDict):
    input: str
    output: str
    scale: Ratio
    last: int

def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="tinybooklet - An extremely imposition tool for making tiny booklets")

    parser.add_argument('-i', '--input', metavar='INPUT', required=True, help='Input file')
    parser.add_argument('-o', '--output', metavar='OUTPUT', required=True, help='Output file')
    parser.add_argument('-s', '--scale', metavar='SCALE', required=True, help='The scale of the output pages compared to the input pages, written as a fraction (e.g. \"1/4\")')
    parser.add_argument('-l', '--last', '--last-pages',
        metavar='LASTPAGES',
        type=int,
        default=0,
        help=
            ('The number of pages at the end of the input PDF to keep as the last pages of the booklet. '
             'Any blank pages needed to pad the page count to a multiple of 4 are inserted before these last pages.')
    )

    args = parser.parse_args()

    # TODO: do a proper error message for this instead of "ValueError: not enough values to unpack (expected 2, got 1)"
    num, denom = args.scale.split("/", 1)

    return {
        'input': args.input,
        'output': args.output,
        'scale': (int(num), int(denom)), # TODO: do a proper error message for this instead of "ValueError: invalid literal for int() with base 10"
        'last': args.last,
    }

def main() -> None:
    args = parse_args()

if __name__ == '__main__':
    main()
