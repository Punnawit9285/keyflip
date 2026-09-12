import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from keyflip.layout import (
    KEYS, EN_TO_TH, TH_TO_EN, convert, detect_direction, normalize_thai,
    TH2EN, EN2TH,
)


def test_table_is_a_bijection():
    assert len(KEYS) == 47
    assert len(EN_TO_TH) == 94, "duplicate US key in the table"
    assert len(TH_TO_EN) == 94, "two US keys produce the same Thai character"


def test_user_examples():
    assert convert("รสนอำันีแสฟีกำ") == "iloveyouclaude"
    assert convert("ggvxgxbh]") == "เเอปเปิ้ล"


def test_direction_detection():
    assert detect_direction("รสนอำ") == TH2EN
    assert detect_direction("ggvxgxbh]") == EN2TH
    assert detect_direction("hello world") == EN2TH
    # majority rules on mixed text
    assert detect_direction("ok สวัสดีครับทุกคน") == TH2EN
    # no letters either way is not evidence of a direction
    assert detect_direction("2026") is None
    assert detect_direction("") is None


def test_round_trip_every_key():
    for us, US, th, TH in KEYS:
        assert convert(us, EN2TH) == th
        assert convert(US, EN2TH) == TH
        assert convert(th, TH2EN) == us
        assert convert(TH, TH2EN) == US


def test_round_trip_sentences():
    for s in ["iloveyouclaude", "The quick brown fox; 42!", "keyflip"]:
        assert convert(convert(s, EN2TH), TH2EN) == s


def test_unmapped_characters_pass_through():
    # whitespace, emoji and anything off the main block survive untouched
    #            a -> FO FAN, b -> SARA I, c -> SARA AE; space/tab/newline unchanged
    assert convert("a b\tc\n", EN2TH) == "\u0e1f \u0e34\t\u0e41\n"
    assert convert("😀 \u200b", EN2TH) == "😀 \u200b"
    assert convert("hi\nthere", EN2TH).count("\n") == 1


def test_real_world_phrases():
    # "สวัสดีครับ" typed while stuck on the US layout
    assert convert("l;ylfu8iy[", EN2TH) == "สวัสดีครับ"
    # and back again
    assert convert("สวัสดีครับ", TH2EN) == "l;ylfu8iy["


def test_shift_states():
    assert convert("Hello", EN2TH) == "็ำสสน"
    assert convert("฿", TH2EN) == "&"


def test_normalize_is_opt_in():
    assert convert("ggvxgxbh]") == "เเอปเปิ้ล"
    assert normalize_thai(convert("ggvxgxbh]")) == "แอปเปิ้ล"
