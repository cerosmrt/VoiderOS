"""F9 (the prose editor) used to always open at the top of the file, no matter
where you were in F1/F2/F5. Federico: "f9 should also [respect current index]
... i mean this that while changing positions, i remain on the same spot" —
then, asked how precise it needed to be: "that it lands in the same paragraph
is enough".

lines_to_paragraphs (reading_page.py) doesn't split 1:1 with F5's paragraph
ordinals: it also breaks a paragraph into several blocks when a line doesn't
end in ,.?!… (scriptio continua, one fragment per line). So the target isn't
"paragraph ordinal N" in that list — it's "the first prose block belonging to
the F5 paragraph containing line_idx", found by matching the block that starts
with that paragraph's first raw line.
"""
from f5_reorder_mixin import F5ReorderMixin
from reading_page import lines_to_paragraphs


def _app():
    class A(F5ReorderMixin):
        pass
    return A()


def test_offset_lands_on_the_right_paragraph_block():
    lines = ['.', 'Primero.', '.', 'Segundo.', '.', 'Tercero.']
    a = _app()
    off = a._f9_entry_offset(lines, 3)             # F2 on 'Segundo.'
    paras = lines_to_paragraphs(lines)
    text = '\n\n'.join(paras)
    assert text[off:].startswith('Segundo.')


def test_offset_on_a_dot_lands_on_the_paragraph_it_opens():
    lines = ['.', 'Primero.', '.', 'Segundo.', '.', 'Tercero.']
    a = _app()
    off = a._f9_entry_offset(lines, 2)             # F2 parked on the dot before 'Segundo.'
    text = '\n\n'.join(lines_to_paragraphs(lines))
    assert text[off:].startswith('Segundo.')


def test_offset_within_a_split_paragraph_lands_on_its_first_block():
    # No trailing punctuation: lines_to_paragraphs keeps them as separate
    # blocks even though _f5_tokens treats them as ONE paragraph.
    lines = ['.', 'fragmento uno', 'fragmento dos', 'fragmento tres', '.', 'Otro.']
    a = _app()
    paras = lines_to_paragraphs(lines)
    assert paras[:3] == ['fragmento uno', 'fragmento dos', 'fragmento tres']
    off = a._f9_entry_offset(lines, 3)              # F2 on 'fragmento tres'
    text = '\n\n'.join(paras)
    assert text[off:].startswith('fragmento uno')   # lands at the paragraph's start


def test_offset_at_the_start_when_line_not_found():
    a = _app()
    assert a._f9_entry_offset([], 0) == 0
