from proseway.anchoring import BlockText, make_anchor, resolve

TEXT = "It was a bright cold day in the valley, and the river ran fast under the old stone bridge."


def blocks(*texts, page=1):
    return [BlockText(f"b{i}", t, page + i, i) for i, t in enumerate(texts)]


def test_exact_anchor():
    a = make_anchor("b0", TEXT, 9, 23)
    assert a.exact == "bright cold day"[:14] or a.exact == TEXT[9:23]
    r = resolve(a, blocks(TEXT))
    assert (r.block_id, r.start, r.end, r.method) == ("b0", 9, 23, "exact")


def test_text_shift_inside_block():
    a = make_anchor("b0", TEXT, TEXT.index("river"), TEXT.index("river") + len("river ran fast"))
    shifted = "Prologue. " + TEXT
    r = resolve(a, blocks(shifted))
    assert r.method == "quote_in_block"
    assert shifted[r.start:r.end] == "river ran fast"


def test_block_id_changed_after_reconversion():
    a = make_anchor("old-id", TEXT, TEXT.index("stone"), TEXT.index("stone") + 12)
    new = [BlockText("x1", "Something else entirely.", 1, 0), BlockText("x2", TEXT, 2, 1)]
    r = resolve(a, new, page_hint=2)
    assert r.block_id == "x2" and r.method == "quote_in_book"
    assert TEXT[r.start:r.end] == "stone bridge"


def test_repeated_quote_uses_context():
    t1 = "The cat sat. And then the dog barked loudly at night."
    t2 = "Later the dog barked loudly at dawn, waking everyone."
    a = make_anchor("gone", t2, t2.index("the dog"), t2.index("the dog") + len("the dog barked loudly"))
    r = resolve(a, blocks(t1, t2), page_hint=2)
    assert r.block_id == "b1"


def test_fuzzy_match_after_small_text_change():
    old = "the extra- ordinary light that came off the surface before the mist lifted"
    a = make_anchor("gone", old, 0, len(old))
    new = "She watched the extraordinary light that came off the surface before the mist lifted from the fields."
    r = resolve(a, blocks(new), page_hint=1)
    assert r.method == "fuzzy"
    assert "extraordinary light" in new[r.start:r.end]


def test_orphaned_when_text_is_gone():
    a = make_anchor("gone", TEXT, 0, 30)
    r = resolve(a, blocks("Completely different words in a different book entirely."), page_hint=1)
    assert r.method == "orphaned"


def test_bookmark_anchor_falls_back_to_page():
    a = make_anchor("gone", TEXT, 0, 0)
    a.exact = ""
    r = resolve(a, blocks("one", "two", "three"), page_hint=2)
    assert r.block_id == "b1"
