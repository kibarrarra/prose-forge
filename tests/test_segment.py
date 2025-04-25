from scripts.segment import split_paragraphs, split_sentences, filter_short

def test_split_paragraphs():
    txt = "Line one.\n\nLine two."
    assert split_paragraphs(txt) == ["Line one.", "Line two."]

def test_split_sentences():
    txt = "Hello world! Mr. Smith left. Eg. sample?"
    assert split_sentences(txt)[:2] == ["Hello world!", "Mr. Smith left."]

def test_filter_short():
    assert filter_short(["a", "abcd"]) == ["abcd"]
