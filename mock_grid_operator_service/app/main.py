from typing import Optional
from random import choices
from fastapi import FastAPI

app = FastAPI()

from pydantic import BaseModel
from decimal import Decimal

BID_OFFER_PAIR_ACCEPTANCE_RATE = 0.8


class BidOfferPair(BaseModel):
    submissionTime: str
    settlementPeriodStartTime: str
    offerPrice: Decimal
    offerVolume: Decimal
    bidPrice: Decimal
    bidVolume: Decimal


class BidOfferPairSubmissionResult(BidOfferPair):
    accepted: bool


@app.get("/")
def read_root():
    return {"Hello": "from mock grid operator"}


@app.post("/submissions", response_model=BidOfferPairSubmissionResult)
def evaluate_offer_or_bid(bidOfferPair: BidOfferPair) -> BidOfferPairSubmissionResult:
    result = BidOfferPairSubmissionResult(
        submissionTime=bidOfferPair.submissionTime,
        settlementPeriodStartTime=bidOfferPair.settlementPeriodStartTime,
        offerPrice=bidOfferPair.offerPrice,
        offerVolume=bidOfferPair.offerVolume,
        bidPrice=bidOfferPair.bidPrice,
        bidVolume=bidOfferPair.bidVolume,
        accepted=choices(
            [True, False], cum_weights=(BID_OFFER_PAIR_ACCEPTANCE_RATE, 1.00), k=1
        )[0],
    )
    return result
