from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def money_positive():
    return Field(gt=0, max_digits=14, decimal_places=2)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationRead(BaseModel):
    id: int
    name: str
    created_by_user_id: int | None = None
    pool_available: Decimal | None = None
    pool_total_contributed: Decimal | None = None
    pool_total_expenses: Decimal | None = None

    model_config = {"from_attributes": True}


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class EventRead(BaseModel):
    id: int
    organization_id: int
    name: str
    created_by_user_id: int | None = None
    organization_pool_available: Decimal | None = None

    model_config = {"from_attributes": True}


class EventUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrgMemberSuggestion(BaseModel):
    user_id: int
    full_name: str
    mobile: str


class MemberCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    mobile: Optional[str] = None
    from_org_user_id: Optional[int] = Field(
        default=None,
        description="Add this organization member by user id (from suggestions).",
    )

    @model_validator(mode="after")
    def require_identity(self):
        if self.from_org_user_id is not None:
            return self
        if (self.name or "").strip() or (self.mobile or "").strip():
            return self
        raise ValueError(
            "Provide a name, a registered mobile number, or select someone from the organization."
        )


class MemberRead(BaseModel):
    id: int
    event_id: int
    name: str
    user_id: Optional[int] = None
    created_by_user_id: Optional[int] = None

    model_config = {"from_attributes": True}


class MemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    mobile: Optional[str] = None


class OrgPoolContributionCreate(BaseModel):
    user_id: int
    amount: Decimal = money_positive()
    note: Optional[str] = None


class OrgPoolContributionRead(BaseModel):
    id: int
    organization_id: int
    user_id: int
    amount: Decimal
    note: Optional[str]
    created_at: str
    created_by_user_id: Optional[int] = None
    expense_id: Optional[int] = None
    event_id: Optional[int] = None


class OrgPoolContributionUpdate(BaseModel):
    amount: Decimal = money_positive()
    note: Optional[str] = None


class ExpenseSplitInput(BaseModel):
    member_id: int
    amount: Optional[Decimal] = None
    percent: Optional[Decimal] = Field(
        default=None, ge=0, le=100, max_digits=7, decimal_places=4
    )

    @field_validator("percent", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class ExpenseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    amount_total: Decimal = money_positive()
    expense_date: date
    splits: list[ExpenseSplitInput]
    pool_creditor_member_id: int | None = Field(
        default=None,
        description="Event member who receives org pool credit for the full bill; takes precedence over pool_credit_user_id.",
    )
    pool_credit_user_id: int | None = Field(
        default=None,
        description="Org pool credits this user instead of the person logging the expense (API); ignored if pool_creditor_member_id is set.",
    )


class ExpenseSplitRead(BaseModel):
    member_id: int
    member_name: str
    amount: Decimal


class ExpenseRead(BaseModel):
    id: int
    event_id: int
    title: str
    category: str
    amount_total: Decimal
    expense_date: date
    splits: list[ExpenseSplitRead] = Field(default_factory=list)
    created_by_user_id: Optional[int] = None
    pool_credit_user_id: Optional[int] = None

    model_config = {"from_attributes": True}


class MemberBalance(BaseModel):
    member_id: int
    user_id: int | None = None
    name: str
    contributed: Decimal
    expended: Decimal
    remaining: Decimal


class UserRegister(BaseModel):
    mobile: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class UserLogin(BaseModel):
    mobile: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrgMemberInvite(BaseModel):
    mobile: str = Field(min_length=10, max_length=20)


class ActivityRead(BaseModel):
    id: int
    organization_id: Optional[int] = None
    event_id: Optional[int] = None
    actor_user_id: Optional[int] = None
    kind: str
    summary: str
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
