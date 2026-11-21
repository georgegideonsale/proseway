"""PDF to reflowable-blocks conversion pipeline.

Stage 1 (extract): one page at a time, pull positioned text lines, images and tables out of
the PDF. The result for each page is a small JSON document, which doubles as the checkpoint
that makes conversions resumable.

Stage 2 (layout): look at the whole book at once to remove running headers/footers and page
numbers, order columns, rejoin hyphenated words, detect headings, footnotes, lists, code,
equations, figures and tables, and emit a flat list of blocks with stable ids.
"""
