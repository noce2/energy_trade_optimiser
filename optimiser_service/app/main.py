from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Union

from fastapi import FastAPI
from pydantic.main import BaseModel

DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
BATTERY_MAX_CHARGE_CYCLE = 20
BATTERY_MAX_DISCHARGE_CYCLE = 20
SIMULATION_TIMESTEP = timedelta(minutes=30)


def convertDateTimeToFormat(dateTime: datetime, format: str = DATE_TIME_FORMAT) -> str:
    return dateTime.strftime(format)


def convertFromFormatToDateTime(
    dateTimeString: str, format: str = DATE_TIME_FORMAT
) -> datetime:
    return datetime.strptime(dateTimeString, format)


app = FastAPI()


class BidOfferPair(BaseModel):
    submissionTime: str
    settlementPeriodStartTime: str
    offerPrice: Decimal
    offerVolume: Decimal
    bidPrice: Decimal
    bidVolume: Decimal


@app.get("/")
def read_root():
    return {"Hello": "from optimiser"}


@app.get("/strategy/", response_model=List[BidOfferPair])
def optimise_revenue_for_period(
    firstSettlementPeriodStart: str, lastSettlementPeriodStart: str
) -> List[BidOfferPair]:
    firstSettlementPeriodStartAsDateTime = convertFromFormatToDateTime(
        firstSettlementPeriodStart
    )
    lastSettlementPeriodStartAsDateTime = convertFromFormatToDateTime(
        lastSettlementPeriodStart
    )

    desiredNumberOfComputations = (
        int(
            (lastSettlementPeriodStartAsDateTime - firstSettlementPeriodStartAsDateTime)
            / SIMULATION_TIMESTEP
        )
        + 1
    )

    resultsToReturn: List[Union[BidOfferPair, None]] = [
        None
    ] * desiredNumberOfComputations
    for step in range(desiredNumberOfComputations):
        settlementPeriodAtCurrentStep = firstSettlementPeriodStartAsDateTime + (
            SIMULATION_TIMESTEP * step
        )
        resultsToReturn[step] = evaluate_bid_offer_pair_at_time(
            settlementPeriodStart=settlementPeriodAtCurrentStep
        )
    return resultsToReturn


def evaluate_bid_offer_pair_at_time(settlementPeriodStart: datetime) -> BidOfferPair:
    bidOfferPair = BidOfferPair(
        submissionTime=convertDateTimeToFormat(
            settlementPeriodStart - SIMULATION_TIMESTEP
        ),
        settlementPeriodStartTime=convertDateTimeToFormat(settlementPeriodStart),
        offerPrice=Decimal(9999),
        offerVolume=Decimal(0),
        bidVolume=Decimal(0),
        bidPrice=Decimal(-9999),
    )
    return bidOfferPair
