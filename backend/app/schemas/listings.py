from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.schemas.common import PhoneE164, StrictModel, clean_text

Fuel = Literal["gasoline", "diesel", "cng", "gasoline_cng", "hybrid", "plugin_hybrid", "electric", "other"]
ColorFamily = Literal["white", "black", "gray", "silver", "red", "blue", "green", "yellow", "orange", "brown", "beige", "gold", "violet", "other"]
YOUTUBE = r"^https://(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[A-Za-z0-9_-]{6,}"


class ListingFields(StrictModel):
    version_id: UUID | None = None
    engine_id: UUID | None = None
    year: Annotated[int, Field(ge=1900, le=2100)] | None = None
    color: Annotated[str, StringConstraints(max_length=40)] | None = None
    color_family: ColorFamily | None = None
    fuel_override: Fuel | None = None
    km: Annotated[int, Field(ge=0, le=2_000_000)] | None = None
    price_amount: Annotated[Decimal, Field(gt=0, lt=Decimal("100000000000"), max_digits=14, decimal_places=2)] | None = None
    currency: Literal["ARS", "USD"] | None = None
    condition: Literal["new", "used"] | None = None
    geo_area_id: UUID | None = None
    title: Annotated[str, StringConstraints(max_length=90)] | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    is_financeable: bool | None = None
    accepts_trade_in: bool | None = None
    video_url: Annotated[str, StringConstraints(max_length=200, pattern=YOUTUBE)] | None = None

    @field_validator("title", "description", "color")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)


class ListingCreate(ListingFields):
    agency_id: UUID | None = None


class ListingPatch(ListingFields):
    pass


class TransitionIn(StrictModel):
    to: Literal["pending", "draft", "paused", "deleted"]


class SaleIn(StrictModel):
    sold_on: date
    final_price: Annotated[Decimal, Field(gt=0, lt=Decimal("100000000000"), max_digits=14, decimal_places=2)]
    currency: Literal["ARS", "USD"]
    channel: Literal["girando", "buyer_from_girando", "other_channel"]
    is_financed: bool = False
    financing_type: Literal["bank_loan", "pledge_loan", "dealer_financing", "savings_plan", "other"] | None = None
    financed_amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)] | None = None
    installments: Annotated[int, Field(ge=1, le=120)] | None = None
    plate: Annotated[str, StringConstraints(max_length=12)] | None = None
    notes: Annotated[str, StringConstraints(max_length=1000)] | None = None

    @field_validator("notes")
    @classmethod
    def _clean(cls, v):
        return clean_text(v)

    @model_validator(mode="after")
    def _fin(self):
        if self.is_financed and not self.financing_type:
            raise ValueError("Indicá el tipo de financiación")
        if not self.is_financed:
            self.financing_type = self.financed_amount = self.installments = None
        if self.financed_amount and self.financed_amount > self.final_price:
            raise ValueError("El monto financiado no puede superar el precio final")
        return self


class ImagePatch(StrictModel):
    kind: Literal["front", "rear", "left", "right", "interior", "additional"] | None = None
    is_cover: Literal[True] | None = None


class ReorderIn(StrictModel):
    image_ids: Annotated[list[UUID], Field(min_length=1, max_length=6)]


class CloudinaryConfirmIn(StrictModel):
    public_id: Annotated[str, StringConstraints(max_length=200)]
    version: int
    signature: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    kind: Literal["front", "rear", "left", "right", "interior", "additional"] = "additional"


class ContactPatch(StrictModel):
    phone_e164: PhoneE164 | None = None
    show_phone: bool | None = None
    whatsapp_e164: PhoneE164 | None = None
    show_whatsapp: bool | None = None
    show_email: bool | None = None
