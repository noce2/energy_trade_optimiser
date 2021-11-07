from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Union, cast
from os import makedirs, getenv

from fastapi import BackgroundTasks, FastAPI
from loguru import logger
from json import dumps

from app.models import BidOfferPair
from app.utils import log_optimiser_current_state

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


@app.on_event("startup")
def configure_logging():
    logLocation = getenv("SVC_LOG_LOCATION", "./logs")
    logFileName = f"{logLocation}/run_output.log"
    try:
        makedirs(logLocation)
    except OSError:
        logger.info("log directory not made as it already exists")

    logger.add(logFileName, rotation="10 MB", serialize=True)


@app.get("/")
def read_root():
    return {"Hello": "from optimiser"}


@app.get("/strategy/", response_model=List[BidOfferPair])
def optimise_revenue_for_period(
    firstSettlementPeriodStart: str,
    lastSettlementPeriodStart: str,
    background_tasks: BackgroundTasks,
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
            settlementPeriodStart=settlementPeriodAtCurrentStep,
            backgroundTasksHandler=background_tasks,
        )
    return cast(List[BidOfferPair], resultsToReturn)


def evaluate_bid_offer_pair_at_time(
    settlementPeriodStart: datetime, backgroundTasksHandler: BackgroundTasks
) -> BidOfferPair:
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

    backgroundTasksHandler.add_task(
        log_optimiser_current_state,
        simulationTimestamp=convertDateTimeToFormat(settlementPeriodStart),
        batteryStateOfCharge=Decimal(5),
        totalEnergyExportedFromStartToDate=Decimal(5),
        totalEnergyImportedFromStartToDate=Decimal(5),
        totalEnergyExportedOnCurrentDay=Decimal(5),
        totalEnergyImportedOnCurrentDay=Decimal(5),
        bidPricePrediction=Decimal(0),
        offerPricePrediction=Decimal(0),
        submittedBidOfferPair=bidOfferPair,
        bidAccepted=False,
        offerAccepted=False,
    )
    return bidOfferPair
