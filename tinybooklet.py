from typing import cast, Iterable

from dataclasses import dataclass
import dataclasses

import pypdf
import argparse

@dataclass
class Args:
    input: str
    output: str
    scale: float
    last_pages: int

def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="tinybooklet - An extremely imposition tool for making tiny booklets")

    parser.add_argument('-i', '--input', metavar='INPUT', required=True, help='Input file')
    parser.add_argument('-o', '--output', metavar='OUTPUT', required=True, help='Output file')
    parser.add_argument('-s', '--scale', metavar='SCALE', required=True, help='The scale of the booklet\'s pages compared to the input pages, written as a fraction (e.g. \"1/4\")')
    parser.add_argument('-l', '--last', '--last-pages',
        metavar='LASTPAGES',
        type=int,
        default=0,
        dest='last_pages',
        help=
            ('The number of pages at the end of the input PDF to keep as the last pages of the booklet. '
             'Any blank pages needed to pad the page count to a multiple of 4 are inserted before these last pages.')
    )

    args = parser.parse_args()

    # TODO: do a proper error message for this instead of "ValueError: not enough values to unpack (expected 2, got 1)"
    num, denom = args.scale.split("/", 1)

    return Args(
        input=args.input,
        output=args.output,
        scale=int(num) / int(denom), # TODO: do a proper error message for this instead of "ValueError: invalid literal for int() with base 10"
        last_pages=args.last_pages,
    )

def impose(input: pypdf.PdfReader, output: pypdf.PdfWriter, scale: float, num_last_pages: int) -> None:
    # this is measured in inches
    input_page_sizes = set(map(lambda page: (page.mediabox.width * page.user_unit, page.mediabox.height * page.user_unit), input.pages))
    if len(input_page_sizes) != 1:
        raise Exception('pdf has multiple different page sizes')
    input_page_size: tuple[float, float] = input_page_sizes.pop()

    spread_size = (input_page_size[0] * scale * 2, input_page_size[1] * scale)

    @dataclass
    # TODO: write actual documentation for this but this is an actual page taken from the input pdf
    class OriginalPage:
        page_number: int
    class BlankPage:
        pass

    Page = OriginalPage | BlankPage

    @dataclass
    class Spread:
        # TODO: write actual documentation for this but the gist of it is imagine looking at a spread from the front so the page on the left side of the front is front_left and likewise with front_right but the backside is also defined based on looking at the front side so the back_left is the backside of front_left
        front_left: Page
        front_right: Page
        back_left: Page
        back_right: Page

    @dataclass
    class OutputSheet:
        # this is also measured in inches
        paper_size: tuple[float, float]
        spreads: list[Spread] = dataclasses.field(default_factory=lambda: [])

        @property
        def spread_grid_rows(self) -> int:
            return int(self.paper_size[1] // spread_size[1])
        @property
        def spread_grid_cols(self) -> int:
            return int(self.paper_size[0] // spread_size[0])

        @property
        def max_spreads(self) -> int:
            return self.spread_grid_rows * self.spread_grid_cols

        def is_full(self) -> bool:
            return len(self.spreads) >= self.max_spreads

        def add_spread(self, spread: Spread) -> None:
            if self.is_full():
                raise Exception('cannot add spread to an output sheet that is already full')

            self.spreads.append(spread)

        def iter_spreads(self) -> Iterable[tuple[int, int, Spread]]:
            x = 0
            y = 0
            for i, spread in enumerate(self.spreads):
                yield (x, y, spread)
                x += 1
                if x >= self.spread_grid_cols:
                    x = 0
                    y += 1

    def pad_pages(pages: list[OriginalPage]) -> list[Page]:
        if len(pages) % 4 != 0:
            pages_to_add = 4 - len(pages) % 4

            first_pages = pages[:len(pages) - num_last_pages]
            last_pages = cast(list[Page], pages[len(pages) - num_last_pages:])
            blank_pages = [BlankPage() for _ in range(pages_to_add)]

            return first_pages + blank_pages + last_pages
        else:
            return cast(list[Page], pages)

    def make_spreads(pages: list[Page]) -> list[Spread]:
        if len(pages) == 0:
            return []
        else:
            spread = Spread(back_left=pages[0], front_left=pages[1], back_right=pages[-1], front_right=pages[-2])
            pages_left = pages[2:-2]
            return [spread] + make_spreads(pages_left)

    def lay_out_spreads(spreads: list[Spread]) -> list[OutputSheet]:
        sheets = [OutputSheet(input_page_size)]

        for spread in spreads:
            if sheets[-1].is_full():
                sheets.append(OutputSheet(input_page_size))

            sheets[-1].add_spread(spread)

        return sheets

    def write_sheets(sheets: list[OutputSheet]) -> None:
        def add_page(transformation: pypdf.Transformation, output_page: pypdf.PageObject, input_page: Page) -> None:
            if isinstance(input_page, BlankPage):
                print('blank')
                pass
            else:
                output_page.merge_transformed_page(input.get_page(input_page.page_number), transformation)

        output_sheet_width = input_page_size[0]
        output_sheet_height = input_page_size[1]

        for sheet in sheets:
            front_side = output.add_blank_page(output_sheet_width, output_sheet_height)
            back_side = output.add_blank_page(output_sheet_width, output_sheet_height)

            for (spread_x, spread_y, spread) in sheet.iter_spreads():
                add_page(pypdf.Transformation().scale(scale, scale).translate(spread_size[0] * spread_x, spread_size[1] * spread_y), front_side, spread.front_left)
                add_page(pypdf.Transformation().scale(scale, scale).translate(spread_size[0] * (spread_x + 0.5), spread_size[1] * spread_y), front_side, spread.front_right)
                add_page(pypdf.Transformation().scale(scale, scale).translate(output_sheet_width - spread_size[0] * (spread_x + 1 - 0.5), spread_size[1] * spread_y), back_side, spread.back_left)
                add_page(pypdf.Transformation().scale(scale, scale).translate(output_sheet_width - spread_size[0] * (spread_x + 1), spread_size[1] * spread_y), back_side, spread.back_right)

    pages = pad_pages([OriginalPage(n) for n in range(input.get_num_pages())])
    spreads = make_spreads(pages)
    sheets = lay_out_spreads(spreads)
    write_sheets(sheets)

def main() -> None:
    args = parse_args()

    input_pdf = pypdf.PdfReader(args.input)
    output_pdf = pypdf.PdfWriter()

    impose(input_pdf, output_pdf, args.scale, args.last_pages)

    with open(args.output, 'wb') as f:
        output_pdf.write(f)

    output_pdf.close()

if __name__ == '__main__':
    main()
