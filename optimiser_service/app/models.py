from pydantic import BaseModel
from decimal import Decimal


class BidOfferPair(BaseModel):
    submissionTime: str
    settlementPeriodStartTime: str
    offerPrice: Decimal
    offerVolume: Decimal
    bidPrice: Decimal
    bidVolume: Decimal
