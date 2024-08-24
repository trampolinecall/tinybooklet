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
    mark_cut_lines: bool
    mark_width: float
    mark_color: tuple[int, int, int]

def parse_args() -> Args:
    """Parse command-line arguments"""

    parser = argparse.ArgumentParser(description="tinybooklet - An extremely imposition tool for making tiny booklets")

    parser.add_argument('-i', '--input', required=True, help='Input file')
    parser.add_argument('-o', '--output', required=True, help='Output file')
    parser.add_argument('-s', '--scale', required=True, help='The scale of the booklet\'s pages compared to the input pages, written as a fraction (e.g. \"1/4\")')
    parser.add_argument('-l', '--last', '--last-pages',
        type=int,
        default=0,
        dest='last_pages',
        help=
            ('The number of pages at the end of the input PDF to keep as the last pages of the booklet. '
             'Any blank pages needed to pad the page count to a multiple of 4 are inserted before these last pages.'),
    )
    parser.add_argument('-k', '--mark-cut-lines', action='store_true', help='Whether or not to mark the lines to cut along after the sheet is printed')
    parser.add_argument('--mark-width', type=int, default=0.01, help='The line width of the cut lines in inches')
    parser.add_argument('--mark-color', default='bbbbbb', help='The color of the cut lines')

    args = parser.parse_args()

    # TODO: do a proper error message for this instead of "ValueError: not enough values to unpack (expected 2, got 1)"
    num, denom = args.scale.split("/", 1)

    mark_color_int = int(args.mark_color, 16)
    mark_color = (0xff & (mark_color_int >> 16), 0xff & (mark_color_int >> 8), 0xff & mark_color_int)

    return Args(
        input=args.input,
        output=args.output,
        scale=int(num) / int(denom), # TODO: do a proper error message for this instead of "ValueError: invalid literal for int() with base 10"
        last_pages=args.last_pages,
        mark_cut_lines=args.mark_cut_lines,
        mark_width=args.mark_width,
        mark_color=mark_color,
    )

def impose(input: pypdf.PdfReader, output: pypdf.PdfWriter, scale: float, num_last_pages: int, mark_cut_lines: bool, mark_color: tuple[int, int, int], mark_width: float) -> None:
    """Run imposition on a PDF

    Arguments:
    - input: The input file
    - output: The output file
    - scale: The size of the booklet's pages compared to the size of the input pages. This is the same as the argument to the `--scale` command line argument
    - num_last_pages: The number of pages at the end of the input PDF to keep as the last pages of the booklet. This is the same as the argument to the `--last` command line argument
    - mark_cut_lines: Whether or not to mark the lines to cut along
    - mark_color: The color of the lines enabled by the `mark_cut_lines` option. The tuple should contain RGB values in the range 0 to 255
    - mark_width: The width of the lines enabled by the `mark_cut_lines` option. This is measured in inches
    """

    # input_page_size, input_page_sizes, and spread_size are measured in inches

    # Get the size of the pages in the input PDF, erroring if different pages have different sizes in the PDF
    input_page_sizes = set(map(lambda page: (page.mediabox.width * page.user_unit / 72, page.mediabox.height * page.user_unit / 72), input.pages))
    if len(input_page_sizes) != 1:
        raise Exception('pdf has multiple different page sizes')
    input_page_size: tuple[float, float] = input_page_sizes.pop()

    spread_size = (input_page_size[0] * scale * 2, input_page_size[1] * scale)

    @dataclass
    class OriginalPage:
        """A page taken from the input PDF"""
        page_number: int
    class BlankPage:
        """A blank page inserted into the booklet to pad the page count to a multiple of 4"""
        pass
    Page = OriginalPage | BlankPage

    @dataclass
    class Spread:
        """A spread that contains 4 pages: two on the front and two on the back. Every spread, when turned into a booklet, should have a vertical fold in the middle of it.

        If you imagine looking at a spread from the front, the page on the left side of the front is front_left and likewise with front_right. The backside is also defined based on the directions looking from the front side, so the back_left is the backside of front_left and back_right is the backside of front_right.

        For another example, if you imagine a booklet with only 4 pages, it would only have one spread. Page 1 would be on the back_left, page 2 would be on the front_left, page 3 would be on the front_right, and page 4 would be on the back_right.
        """
        front_left: Page
        front_right: Page
        back_left: Page
        back_right: Page

    @dataclass
    class OutputSheet:
        """A sheet of paper that the output is printed on. It will contain many spreads on it."""
        # paper_size is also measured in inches
        paper_size: tuple[float, float]
        spreads: list[Spread] = dataclasses.field(default_factory=lambda: [])

        @property
        def spread_grid_rows(self) -> int:
            """The number of rows of spreads that can fit on this output sheet."""
            return int(self.paper_size[1] // spread_size[1])
        @property
        def spread_grid_cols(self) -> int:
            """The number of columns of spreads that can fit on this output sheet."""
            return int(self.paper_size[0] // spread_size[0])

        @property
        def max_spreads(self) -> int:
            """The total number of spreads that can fit on this output sheet."""
            return self.spread_grid_rows * self.spread_grid_cols

        def is_full(self) -> bool:
            """Return whether or not this output sheet is fully filled up."""
            return len(self.spreads) >= self.max_spreads

        def add_spread(self, spread: Spread) -> None:
            """Add a new spread to this output sheet.

            This will throw an exception if the sheet is full
            """
            if self.is_full():
                raise Exception('cannot add spread to an output sheet that is already full')

            self.spreads.append(spread)

        def iter_spreads(self) -> Iterable[tuple[int, int, Spread]]:
            """Iterate through all of the spreads on this page with the coordinates of where they are.

            Note that the coordinates are for the spreads and not for the pages, so they always increment by 1.
            """
            x = 0
            y = 0
            for i, spread in enumerate(self.spreads):
                yield (x, y, spread)
                x += 1
                if x >= self.spread_grid_cols:
                    x = 0
                    y += 1

    def pad_pages(pages: list[OriginalPage]) -> list[Page]:
        """Pad the list of pages to a multiple of 4, taking num_last_pages into account"""
        if len(pages) % 4 != 0:
            pages_to_add = 4 - len(pages) % 4

            first_pages = pages[:len(pages) - num_last_pages]
            last_pages = cast(list[Page], pages[len(pages) - num_last_pages:])
            blank_pages = [BlankPage() for _ in range(pages_to_add)]

            return first_pages + blank_pages + last_pages
        else:
            return cast(list[Page], pages)

    def make_spreads(pages: list[Page]) -> list[Spread]:
        """Group a list of pages into spreads.

        The input list of pages should have a length that is a multiple of 4.
        """

        # This works as a recursive algorithm.
        # First, we take the first two pages and last two pages and make a spread out of that, with the first page going on the back_left, the second going on the front_left, the second to last going on the front_right, and the last going on the back_right.
        # From there, we can imagine taking off those first two pages and last two pages and making a booklet out of the inner pages, which is where we can recurse on the inner pages.

        if len(pages) == 0:
            return []
        else:
            spread = Spread(back_left=pages[0], front_left=pages[1], back_right=pages[-1], front_right=pages[-2])
            pages_left = pages[2:-2]
            return [spread] + make_spreads(pages_left)

    def lay_out_spreads(spreads: list[Spread]) -> list[OutputSheet]:
        """Lay out spreads onto output sheets."""

        sheets = [OutputSheet(input_page_size)]

        for spread in spreads:
            if sheets[-1].is_full():
                sheets.append(OutputSheet(input_page_size))

            sheets[-1].add_spread(spread)

        return sheets

    def write_sheets(sheets: list[OutputSheet]) -> None:
        """Write output sheets to the output pdf"""

        def add_page(drawing_commands: list[str], output_page: pypdf.PageObject, input_page: Page, x: float, y: float) -> None:
            """Write a page of the input pdf to an output page at a certain location

            Arguments:
            - drawing_commands: Any drawing commands that are used to make the cut lines are added to this list
            - output_page: The output page to put a page on
            - input_page: THe input page to put onto the output page
            - x, y: The coordinates of where the input_page should appear on the output page, measured in inches. Note that this follows the PDF coordinate space, so y=0 is at the bottom of the page
            """

            if mark_cut_lines:
                left = x * 72
                bottom = y * 72
                drawing_commands.append(f'{left} {bottom} {input_page_size[0] * scale * 72} {input_page_size[1] * scale * 72} re s')

            if isinstance(input_page, BlankPage):
                pass
            else:
                transform = pypdf.Transformation().scale(scale, scale).translate(x * 72, y * 72)
                output_page.merge_transformed_page(input.get_page(input_page.page_number), transform)

        # This is also measured in inches
        # Right now, we just take the page size of the input PDF, but in the future, this might take the size from a command-line argument
        output_sheet_width = input_page_size[0]
        output_sheet_height = input_page_size[1]

        for sheet in sheets:
            front_side = output.add_blank_page(output_sheet_width * 72, output_sheet_height * 72)
            back_side = output.add_blank_page(output_sheet_width * 72, output_sheet_height * 72)

            # These first 2 commands set the stroke color and the stroke width of the drawing contex
            front_drawing_commands: list[str] = [f'{mark_color[0] / 255} {mark_color[1] / 255} {mark_color[2] / 255} RG {mark_width * 72 / front_side.user_unit} w']
            back_drawing_commands: list[str] = [f'{mark_color[0] / 255} {mark_color[1] / 255} {mark_color[2] / 255} RG {mark_width * 72 / back_side.user_unit} w']

            for (spread_x, spread_y, spread) in sheet.iter_spreads():
                add_page(front_drawing_commands, front_side, spread.front_left, spread_size[0] * spread_x, spread_size[1] * spread_y)
                add_page(front_drawing_commands, front_side, spread.front_right, spread_size[0] * (spread_x + 0.5), spread_size[1] * spread_y)
                add_page(back_drawing_commands, back_side, spread.back_left, output_sheet_width - spread_size[0] * (spread_x + 1 - 0.5), spread_size[1] * spread_y)
                add_page(back_drawing_commands, back_side, spread.back_right, output_sheet_width - spread_size[0] * (spread_x + 1), spread_size[1] * spread_y)

            front_contents = front_side.get_contents()
            assert front_contents is not None # TODO: not sure what to do if this happens
            new_front_contents = front_contents.clone(output)
            new_front_contents.set_data(new_front_contents.get_data() + ' '.join(front_drawing_commands).encode('ascii'))
            front_side.replace_contents(new_front_contents)

            back_contents = back_side.get_contents()
            assert back_contents is not None # TODO: not sure what to do if this happens
            new_back_contents = back_contents.clone(output)
            new_back_contents.set_data(new_back_contents.get_data() + ' '.join(back_drawing_commands).encode('ascii'))
            back_side.replace_contents(new_back_contents)

    pages = pad_pages([OriginalPage(n) for n in range(input.get_num_pages())])
    spreads = make_spreads(pages)
    sheets = lay_out_spreads(spreads)
    write_sheets(sheets)

def main() -> None:
    args = parse_args()

    input_pdf = pypdf.PdfReader(args.input)
    output_pdf = pypdf.PdfWriter()

    impose(input_pdf, output_pdf, args.scale, args.last_pages, args.mark_cut_lines, args.mark_color, args.mark_width)

    with open(args.output, 'wb') as f:
        output_pdf.write(f)

    output_pdf.close()

if __name__ == '__main__':
    main()
