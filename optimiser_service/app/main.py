from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Union, cast
from os import makedirs, getenv

from fastapi import BackgroundTasks, FastAPI
from loguru import logger
from json import dumps

from app.models import BidOfferPair
from app.utils import (
    convertDateTimeToFormat,
    convertFromFormatToDateTime,
    log_optimiser_current_state,
)
from app.services import (
    DischargeRequest,
    MarketPredictions,
    charge_battery,
    discharge_battery,
    get_battery_state,
    get_next_48_market_predictions,
    submit_bid_offer_pair,
    ChargeRequest,
)


BATTERY_MAX_CHARGE_CYCLE = 20
BATTERY_MAX_DISCHARGE_CYCLE = 20
BATTERY_MAX_CAPACITY = 10
SIMULATION_TIMESTEP = timedelta(minutes=30)
TIMESTEP_BEFORE_GATE_CLOSURE = timedelta(hours=1)
OFFER_BID_VOLUME = 5


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


def evaluate_bid_offer_pair_at_time(
    simulationTimeStamp: datetime,
    offerPrice=Decimal(9999),
    offerVolume=Decimal(0),
    bidVolume=Decimal(0),
    bidPrice=Decimal(-9999),
) -> BidOfferPair:
    bidOfferPair = BidOfferPair(
        submissionTime=convertDateTimeToFormat(simulationTimeStamp),
        settlementPeriodStartTime=convertDateTimeToFormat(
            simulationTimeStamp + TIMESTEP_BEFORE_GATE_CLOSURE
        ),
        offerPrice=offerPrice,
        offerVolume=offerVolume,
        bidVolume=bidVolume,
        bidPrice=bidPrice,
    )
    return bidOfferPair


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

    prospectiveOffersAndBids: MarketPredictions = {"offer_prices": {}, "bid_prices": {}}

    for step in range(desiredNumberOfComputations):

        simulationTimestamp = firstSettlementPeriodStartAsDateTime + (
            SIMULATION_TIMESTEP * step
        )

        settlementPeriodDateTime = simulationTimestamp + TIMESTEP_BEFORE_GATE_CLOSURE

        isTimeStepStartOfNewDay = (
            simulationTimestamp.date()
            != (simulationTimestamp - SIMULATION_TIMESTEP).date()
        )

        batteryStateAtSimulationTimestamp = get_battery_state(simulationTimestamp)
        batteryStateAtSettlementPeriodTimestamp = get_battery_state(
            settlementPeriodDateTime
        )
        next48Predictions = get_next_48_market_predictions(simulationTimestamp)
        bidAccepted = False
        offerAccepted = False

        ## get market predictions at start of the day or on first timestep
        if step == 0 or (isTimeStepStartOfNewDay):

            ## as there is no volume demand prediction along with offers and bids
            ## it is assumed that any charge/discharge will be for a volume of 5MWh
            ## this implies a limit of 4 charges and 4 discharges.

            ## an 80% acceptance also means at least 5 possible bids/offers need to be generated.

            lowest5BidTimesAndPrices = sorted(
                next48Predictions["bid_prices"].items(),
                key=lambda timeAndPrice: timeAndPrice[1],
            )[0:5]
            prospectiveOffersAndBids["bid_prices"] = {
                each[0]: each[1] for each in lowest5BidTimesAndPrices
            }

            highest5OfferTimesAndPrices = sorted(
                next48Predictions["offer_prices"].items(),
                key=lambda timeAndPrice: timeAndPrice[1],
            )[-5:]
            prospectiveOffersAndBids["offer_prices"] = {
                each[0]: each[1] for each in highest5OfferTimesAndPrices
            }

        possibleBidOfferPair = None

        if (
            convertDateTimeToFormat(settlementPeriodDateTime)
            in prospectiveOffersAndBids["offer_prices"]
            and (
                batteryStateAtSettlementPeriodTimestamp["chargeLevelAtPeriodStart"]
                - OFFER_BID_VOLUME
                >= 0
            )
            and (
                batteryStateAtSettlementPeriodTimestamp["sameDayExportTotal"]
                + OFFER_BID_VOLUME
                <= BATTERY_MAX_DISCHARGE_CYCLE
            )
        ):
            possibleBidOfferPair = evaluate_bid_offer_pair_at_time(
                simulationTimeStamp=simulationTimestamp,
                offerPrice=prospectiveOffersAndBids["offer_prices"][
                    convertDateTimeToFormat(settlementPeriodDateTime)
                ],
                offerVolume=OFFER_BID_VOLUME,
            )

            submissionResult = submit_bid_offer_pair(possibleBidOfferPair)

            if submissionResult["accepted"]:
                discharge_battery(
                    DischargeRequest(
                        settlementPeriodStartTime=convertDateTimeToFormat(
                            settlementPeriodDateTime
                        ),
                        offerVolume=OFFER_BID_VOLUME,
                    )
                )
                offerAccepted = True
        elif (
            convertDateTimeToFormat(settlementPeriodDateTime)
            in prospectiveOffersAndBids["bid_prices"]
            and (
                batteryStateAtSettlementPeriodTimestamp["chargeLevelAtPeriodStart"]
                + OFFER_BID_VOLUME
                <= BATTERY_MAX_CAPACITY
            )
            and (
                (
                    batteryStateAtSettlementPeriodTimestamp["sameDayImportTotal"]
                    + OFFER_BID_VOLUME
                )
                <= BATTERY_MAX_CHARGE_CYCLE
            )
        ):
            possibleBidOfferPair = evaluate_bid_offer_pair_at_time(
                simulationTimeStamp=simulationTimestamp,
                bidPrice=prospectiveOffersAndBids["bid_prices"][
                    convertDateTimeToFormat(settlementPeriodDateTime)
                ],
                bidVolume=OFFER_BID_VOLUME,
            )

            submissionResult = submit_bid_offer_pair(possibleBidOfferPair)

            if submissionResult["accepted"]:
                charge_battery(
                    ChargeRequest(
                        settlementPeriodStartTime=convertDateTimeToFormat(
                            settlementPeriodDateTime
                        ),
                        bidVolume=OFFER_BID_VOLUME,
                    )
                )
                bidAccepted = True
        else:
            possibleBidOfferPair = evaluate_bid_offer_pair_at_time(
                simulationTimeStamp=simulationTimestamp,
            )

        resultsToReturn[step] = possibleBidOfferPair

        background_tasks.add_task(
            log_optimiser_current_state,
            simulationTimestamp=convertDateTimeToFormat(simulationTimestamp),
            batteryStateOfCharge=batteryStateAtSimulationTimestamp[
                "chargeLevelAtPeriodStart"
            ],
            totalEnergyExportedFromStartToDate=batteryStateAtSimulationTimestamp[
                "cumulativeExportTotal"
            ],
            totalEnergyImportedFromStartToDate=batteryStateAtSimulationTimestamp[
                "cumulativeImportTotal"
            ],
            totalEnergyExportedOnCurrentDay=batteryStateAtSimulationTimestamp[
                "sameDayExportTotal"
            ],
            totalEnergyImportedOnCurrentDay=batteryStateAtSimulationTimestamp[
                "sameDayImportTotal"
            ],
            bidPricePrediction=next48Predictions["bid_prices"][
                convertDateTimeToFormat(settlementPeriodDateTime)
            ],
            offerPricePrediction=next48Predictions["offer_prices"][
                convertDateTimeToFormat(settlementPeriodDateTime)
            ],
            submittedBidOfferPair=resultsToReturn[step],
            bidAccepted=bidAccepted,
            offerAccepted=offerAccepted,
        )
    return cast(List[BidOfferPair], resultsToReturn)
