"""Tests for importing user-provided directory CSV files."""

from __future__ import annotations

from io import StringIO

import pytest

from fishops.collectors.csv_import import load_candidates_from_csv


def test_import_maps_common_directory_headers_and_preserves_provenance():
    csv_file = StringIO(
        "name,phone,email,lat,lng,url,address,city,state,country\n"
        '"Mwea Fish Farm",0712345678,info@example.org,-0.6,37.3,'
        "https://example.org,Main road,Mwea,Kirinyaga County,Kenya\n"
    )

    [candidate] = load_candidates_from_csv(
        csv_file,
        source_name="Sample register",
        source_url="https://source.example/register",
    )

    assert candidate.business_name == "Mwea Fish Farm"
    assert candidate.phone_normalized == "+254712345678"
    assert candidate.email_raw == "info@example.org"
    assert candidate.website_raw == "https://example.org"
    assert candidate.address_raw == "Main road"
    assert candidate.city_town == "Mwea"
    assert candidate.county_inferred == "Kirinyaga"
    assert candidate.latitude == -0.6
    assert candidate.longitude == 37.3
    assert candidate.source_name == "Sample register"
    assert candidate.source_url == "https://source.example/register"
    assert candidate.raw_payload["state"] == "Kirinyaga County"


def test_import_rejects_malformed_coordinates_with_csv_row_number():
    csv_file = StringIO("business_name,latitude\nExample Farm,north\n")

    with pytest.raises(ValueError, match="CSV row 2: latitude must be a number"):
        load_candidates_from_csv(csv_file)


def test_import_rejects_out_of_range_coordinates():
    csv_file = StringIO("business_name,longitude\nExample Farm,181\n")

    with pytest.raises(
        ValueError, match="CSV row 2: longitude must be between -180 and 180"
    ):
        load_candidates_from_csv(csv_file)


def test_import_rejects_unsupported_country_name():
    csv_file = StringIO("business_name,country\nExample Farm,Uganda\n")

    with pytest.raises(ValueError, match="unsupported country value 'Uganda'"):
        load_candidates_from_csv(csv_file)


def test_import_skips_rows_without_a_business_name():
    csv_file = StringIO("business_name,phone\n,0712345678\n")

    assert load_candidates_from_csv(csv_file) == []


def test_uploaded_file_can_be_parsed_again_after_streamlit_rerun():
    csv_file = StringIO("business_name\nExample Farm\n")

    assert len(load_candidates_from_csv(csv_file)) == 1
    assert len(load_candidates_from_csv(csv_file)) == 1
