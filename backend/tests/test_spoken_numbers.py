import pytest

from app.services.spoken_numbers import extract_numbers, parse_number_list, parse_spoken_number


@pytest.mark.parametrize(
    "text, expected",
    [
        # Hindi (Latin spelling)
        ("teen", 3),
        ("do saal", 2),
        ("paintees saal", 35),
        ("chhabbis", 26),
        ("ek sau", 100),
        ("nabbe", 90),
        # Hindi (Devanagari)
        ("पैंतीस", 35),
        ("मेरे तीन बच्चे हैं", 3),
        ("सौ", 100),
        # Tamil (Latin + script, including "tens + unit" compounds)
        ("moonu", 3),
        ("irupathi anju", 25),
        ("naarpathu", 40),
        ("மூணு", 3),
        ("நாற்பத்தி ரெண்டு", 42),
        # Telugu (Latin + script)
        ("moodu", 3),
        ("iravai aidu", 25),
        ("ముప్పై రెండు", 32),
        ("పదిహేను", 15),
        # English and digits
        ("twenty-five", 25),
        ("I am 35 years old", 35),
        # Native digits
        ("३५", 35),
        ("௩௫", 35),
        ("౩౫", 35),
    ],
)
def test_single_numbers(text, expected):
    assert parse_spoken_number(text) == expected


def test_numbers_pass_through():
    assert parse_spoken_number(42) == 42
    assert parse_spoken_number(4.0) == 4.0


@pytest.mark.parametrize("text", ["do ya teen", "", "pata nahi", None, True])
def test_no_single_number(text):
    # Ambiguous or missing -> None, so the agent re-asks.
    assert parse_spoken_number(text) is None


def test_number_lists():
    assert parse_number_list("paanch aur aath") == [5, 8]
    assert parse_number_list("5, 8, 2") == [5, 8, 2]
    assert parse_number_list([5, "aath"]) == [5, 8]
    assert parse_number_list("moonu, anju") == [3, 5]
    assert parse_number_list("no idea") is None


def test_extract_keeps_order():
    assert extract_numbers("das aur bees") == [10, 20]
