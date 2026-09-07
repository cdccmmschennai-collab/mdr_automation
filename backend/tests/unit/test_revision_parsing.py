"""Revision parsing and sequencing."""

import pytest

from app.engine.revision.parsing import (
    Revision, RevisionBand, compare, parse_revision,
)


class TestNumeric:
    @pytest.mark.parametrize("raw,expected", [
        ("0", 0), ("1", 1), ("2", 2), ("9", 9), ("10", 10), ("18", 18),
    ])
    def test_numeric_ordinals(self, raw, expected):
        r = parse_revision(raw)
        assert r.band is RevisionBand.NUMERIC
        assert r.ordinal == expected
        assert r.normalised == str(expected)

    def test_numeric_sequence_orders_naturally(self):
        revs = [parse_revision(x) for x in ["0", "1", "2", "10"]]
        assert [r.ordinal for r in sorted(revs, key=lambda r: r.sort_key)] == [0, 1, 2, 10]

    def test_multi_digit_beats_single_digit(self):
        """'10' must outrank '9' - lexical sorting would get this wrong."""
        assert compare(parse_revision("10"), parse_revision("9")) == 1

    def test_excel_float_is_normalised(self):
        assert parse_revision("3.0").normalised == "3"
        assert parse_revision(3).ordinal == 3


class TestAlphabetic:
    @pytest.mark.parametrize("raw,expected", [
        ("A", 0), ("B", 1), ("C", 2), ("D", 3), ("E", 4), ("Y", 24),
    ])
    def test_alpha_ordinals(self, raw, expected):
        r = parse_revision(raw)
        assert r.band is RevisionBand.ALPHABETIC
        assert r.ordinal == expected

    def test_lowercase_is_accepted(self):
        assert parse_revision("b").band is RevisionBand.ALPHABETIC
        assert parse_revision("b").normalised == "B"


class TestBandOrdering:
    """The core business rule: alphabetic ranks LATER than numeric."""

    def test_alpha_outranks_numeric(self):
        assert compare(parse_revision("A"), parse_revision("4")) == 1
        assert compare(parse_revision("A"), parse_revision("99")) == 1

    def test_full_documented_sequence(self):
        """REV 0,1,2,A,B -> latest is B (the brief's worked example)."""
        revs = [parse_revision(x) for x in ["0", "1", "2", "A", "B"]]
        latest = max(revs, key=lambda r: r.sort_key)
        assert latest.normalised == "B"

    def test_numeric_never_beats_alpha(self):
        assert compare(parse_revision("7"), parse_revision("A")) == -1


class TestAsBuilt:
    """'Z' is the as-built/brown-field marker, not the 26th sequence letter.

    All 68 'Z' rows in the source workbook carry issue code ASB and none is
    ever marked latest.
    """

    def test_z_is_its_own_band(self):
        assert parse_revision("Z").band is RevisionBand.AS_BUILT

    def test_z_is_not_eligible_to_be_latest(self):
        assert parse_revision("Z").eligible_for_latest is False

    def test_z_does_not_outrank_letters_as_a_sequence_value(self):
        """Z must not win latest over C just by being a later letter."""
        assert parse_revision("Z").eligible_for_latest is False
        assert parse_revision("C").eligible_for_latest is True


class TestUnparseable:
    @pytest.mark.parametrize("raw", ["", "-", None, "REV 1", "1A", "??", "AB"])
    def test_unparseable_values(self, raw):
        r = parse_revision(raw)
        assert r.band is RevisionBand.UNPARSEABLE
        assert not r.is_parseable
        assert r.eligible_for_latest is False

    def test_unparseable_carries_a_reason(self):
        assert parse_revision("??").reason == "REV_UNRECOGNISED_FORMAT"
        assert parse_revision("").reason == "REV_EMPTY"

    def test_revision_is_never_inferred_from_a_document_number(self):
        """A document number is not a revision, even though it holds digits."""
        assert not parse_revision("4391-MTY-1-19-0051").is_parseable
