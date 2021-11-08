from datetime import datetime
from decimal import Decimal
import json
from os import getenv
from typing import Dict, TypedDict
from pydantic.main import BaseModel
import requests
from app.models import BidOfferPair

from app.utils import convertDateTimeToFormat
from loguru import logger

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


JSON_HEADERS = {"Content-Type": "application/json"}


class DecimalCompatibleEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return obj.to_eng_string()
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


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
    logger.info(f"submitting bid offer: {bidOfferPair}")
    response = requests.post(
        f"{GRID_OPERATOR_HOST_ADDRESS}/submissions",
        headers=JSON_HEADERS,
        data=json.dumps(bidOfferPair.dict(), cls=DecimalCompatibleEncoder),
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
        headers=JSON_HEADERS,
        data=json.dumps(chargeRequest.dict(), cls=DecimalCompatibleEncoder),
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to charge battery, cause: {str(e)}")


def discharge_battery(dischargeRequest: DischargeRequest) -> BatteryState:
    response = requests.post(
        f"{BATTERY_SERVICE_HOST_ADDRESS}/discharge",
        headers=JSON_HEADERS,
        data=json.dumps(dischargeRequest.dict(), cls=DecimalCompatibleEncoder),
    )

    try:
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise Exception(f"Failed to discharge battery, cause: {str(e)}")
