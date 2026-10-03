import pytest

from factories import make_column, make_table
from quorlo.readiness import Dimension, ScanContext, evaluate_table
from quorlo.readiness.checks import PiiUnclassified, is_classified_as_pii
from quorlo.readiness.names import pii_category

CTX = ScanContext(())


@pytest.mark.parametrize(
    ("column", "table", "category"),
    [
        ("email", "orders", "email address"),
        ("contact_eml", "anything", "email address"),
        ("phoneNumber", "accounts", "phone number"),
        ("phn", "cust_mstr", "phone number"),
        ("ssn", "x", "national identifier"),
        ("date_of_birth", "x", "birth details"),
        ("dob", "x", "date of birth"),
        ("first_name", "orders", "person name"),
        ("lastName", "orders", "person name"),
        ("surname", "x", "person name"),
        ("card_number", "payments", "payment card number"),
        ("ip", "events", "IP address"),
        ("client_ip", "events", "IP address"),
        # Words that only mean personal data in a table about people.
        ("nm", "cust_mstr", "person name"),
        ("name", "customers", "person name"),
        ("addr1", "cust_mstr", "postal address"),
        ("pc", "cust_mstr", "postal address"),
        ("customer_name", "orders", "person name"),
        ("zip", "users", "postal address"),
    ],
)
def test_pii_detected(column, table, category):
    assert pii_category(column, table) == category


@pytest.mark.parametrize(
    ("column", "table"),
    [
        ("product_name", "dim_product"),
        ("name", "warehouses"),
        ("addr1", "warehouses"),
        ("pc", "sales"),
        ("ship_date", "orders"),
        ("vip_flag", "accounts"),
        ("zip_file", "uploads"),
        ("order_id", "customers"),
        ("card_type", "payments"),
    ],
)
def test_not_pii(column, table):
    assert pii_category(column, table) is None


def test_ip_types_are_pii_whatever_the_name():
    assert pii_category("source", "events", "inet") == "IP address"


@pytest.mark.parametrize(
    ("description", "tags", "classified"),
    [
        (None, (), False),
        ("Customer contact address.", (), False),
        ("Email address. PII.", (), True),
        ("Personal data: the customer's phone.", (), True),
        ("Personally identifiable.", (), True),
        (None, ("pii",), True),
        (None, ("PII.contact",), True),
        (None, ("gdpr",), True),
        (None, ("finance",), False),
    ],
)
def test_classification(description, tags, classified):
    col = make_column("email", description).model_copy(update={"tags": tags})
    assert is_classified_as_pii(col) is classified


def test_pii_check_reports_each_unclassified_column():
    table = make_table(
        "cust_mstr",
        columns=[
            make_column("cust_id", "Key."),
            make_column("nm"),
            make_column("eml", "Email address. PII."),
            make_column("phn"),
        ],
    )
    check = PiiUnclassified()
    assert check.dimension is Dimension.GOVERNANCE
    findings = list(check.run(table, CTX))
    assert [f.column for f in findings] == ["nm", "phn"]
    assert "person name" in findings[0].message


def test_pii_check_scores_the_whole_table():
    table = make_table("customers", columns=[make_column(c) for c in ("email", "phone", "notes")])
    result = evaluate_table(table, [PiiUnclassified()])
    (check,) = result.checks
    assert (check.evaluated, check.failed) == (1, 1)
    assert result.dimensions[Dimension.GOVERNANCE] == 0.0
    assert len(result.findings) == 2
