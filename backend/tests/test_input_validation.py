import pytest
from pydantic import ValidationError

from app.routers.auth import OTPRequest, OTPVerification
from app.routers.complaints import (
    AssignRequest,
    CategoryRequest,
    CreateComplaintRequest,
    RateComplaintRequest,
    StatusRequest,
)
from app.routers.accounts import ResolveRequest


@pytest.mark.parametrize("phone", ["123", "abcdefghij", "1" * 16])
def test_otp_phone_format_is_validated(phone):
    with pytest.raises(ValidationError):
        OTPRequest(phone=phone)


@pytest.mark.parametrize("text", ["four", "   ", "x" * 1001])
def test_complaint_text_length_is_validated(text):
    with pytest.raises(ValidationError):
        CreateComplaintRequest(text=text)


@pytest.mark.parametrize("rating", [0, 6, True, 3.5])
def test_rating_is_an_integer_from_one_to_five(rating):
    with pytest.raises(ValidationError):
        RateComplaintRequest(rating=rating)


def test_complaint_category_and_status_use_allowlists():
    with pytest.raises(ValidationError):
        CategoryRequest(category="not-a-category")
    with pytest.raises(ValidationError):
        StatusRequest(status="not-a-status")


def test_assignment_and_flat_ids_must_be_positive():
    with pytest.raises(ValidationError):
        AssignRequest(assignee_id=0)
    with pytest.raises(ValidationError):
        ResolveRequest(flat_id=-1)


def test_otp_code_must_be_six_digits():
    with pytest.raises(ValidationError):
        OTPVerification(phone="9000012345", otp="12345")
