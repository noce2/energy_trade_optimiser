from datetime import datetime
from decimal import Decimal
from os import getenv
from typing import Dict, TypedDict
from pydantic.main import BaseModel
import requests
from app.models import BidOfferPair

from app.utils import convertDateTimeToFormat

MARKET_SERVICE_HOST_ADDRESS = getenv("SVC_MARKET_HOST", "http://localhost:5002")
BATTERY_SERVICE_HOST_ADDRESS = getenv("SVC_BATTERY_HOST", "http://localhost:5003")
GRID_OPERATOR_HOST_ADDRESS = getenv(
    "SVC_MOCK_GRID_OPERATOR_HOST", "http://localhost:5001"
)


class MarketPredictions(TypedDict):
    offer_prices: Dict[str, Decimal]
    bid_prices: Dict[str, Decimal]


class BatteryState(TypedDict):
    settlementPeriodStartTime: str
    chargeLevelAtPeriodStart: Decimal
    sameDayImportTotal: Decimal
    sameDayExportTotal: Decimal
    cumulativeImportTotal: Decimal
    cumulativeExportTotal: Decimal


class BidOfferPairSubmissionResult(TypedDict):
    submissionTime: str
    settlementPeriodStartTime: str
    offerPrice: Decimal
    offerVolume: Decimal
    bidPrice: Decimal
    bidVolume: Decimal
    accepted: bool


class ChargeRequest(BaseModel):
    settlementPeriodStartTime: str
    bidVolume: Decimal


class DischargeRequest(BaseModel):
    settlementPeriodStartTime: str
    offerVolume: Decimal


def get_next_48_market_predictions(dateTime: datetime) -> MarketPredictions:
    response = requests.get(
        f"{MARKET_SERVICE_HOST_ADDRESS}/predictions",
        params={"timeOfPredictionRequest": convertDateTimeToFormat(dateTime)},
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to get market predictions, cause: {str(e)}")


def get_battery_state(dateTime: datetime) -> BatteryState:
    response = requests.get(
        f"{BATTERY_SERVICE_HOST_ADDRESS}/state",
        params={"settlementPeriodStartTime": convertDateTimeToFormat(dateTime)},
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to get battery state, cause: {str(e)}")


def submit_bid_offer_pair(bidOfferPair: BidOfferPair) -> BidOfferPairSubmissionResult:
    response = requests.post(
        f"{GRID_OPERATOR_HOST_ADDRESS}/submissions",
        data=bidOfferPair.dict(),
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to submit bid-offer pair, cause: {str(e)}")


## TODO Add calls for charge and discharge
def charge_battery(chargeRequest: ChargeRequest) -> BatteryState:
    response = requests.post(
        f"{BATTERY_SERVICE_HOST_ADDRESS}/charge",
        data=chargeRequest.dict(),
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to charge battery, cause: {str(e)}")


def discharge_battery(dischargeRequest: DischargeRequest) -> BatteryState:
    response = requests.post(
        f"{BATTERY_SERVICE_HOST_ADDRESS}/discharge",
        data=dischargeRequest.dict(),
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to discharge battery, cause: {str(e)}")
