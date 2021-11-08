from decimal import Decimal
from datetime import datetime, timedelta
import json
from typing import Optional, cast
import boto3
import re
from boto3.dynamodb.conditions import Key

from fastapi import FastAPI, HTTPException
from botocore import errorfactory
from os import getenv
import logging

from mypy_boto3_dynamodb.service_resource import _Table

from app.models import BatteryState, ChargeRequest, DischargeRequest

BATTERY_MAX_CAPACITY = 10

app = FastAPI()
dynamodb = boto3.resource(
    "dynamodb", endpoint_url=getenv("SVC_DYNAMODB_HOST"), region_name="eu-west-2"
)
BATTERY_STATE_TABLENAME = "BATTERY_STATE"
DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
BATTERY_MAX_CHARGE_CYCLE = 20
BATTERY_MAX_DISCHARGE_CYCLE = 20
TIMESTEPS_BETWEEN_BATTERY_STATE = timedelta(minutes=30)


@app.get("/")
def read_root():
    return {"Hello": "from battery service"}


@app.get("/state/", response_model=BatteryState)
def get_battery_state(settlementPeriodStartTime: str):
    queryResult = {}
    settlementPeriodStartTimeAsDateTime = datetime.strptime(
        settlementPeriodStartTime, DATE_TIME_FORMAT
    )
    try:

        table = dynamodb.Table(BATTERY_STATE_TABLENAME)
        table.load()

        if not (table.table_status == "ACTIVE"):
            table = createTable()

        if table.item_count == 0:
            ## TODO FIX ME!!! ALWAYS SEDDING DATA!!! NO PERSISTENCe
            seedDataBase(
                table=table, initialTimeStamp=settlementPeriodStartTimeAsDateTime
            )

        queryResult = table.get_item(
            Key={
                "settlementPeriodStartTimeEpoch": Decimal(
                    settlementPeriodStartTimeAsDateTime.timestamp()
                ),
                "settlementPeriodDay": settlementPeriodStartTimeAsDateTime.date().isoformat(),
            },
        )
        if queryResult and queryResult.get("Item", None):
            queryResult["Item"]["settlementPeriodStartTime"] = settlementPeriodStartTime
            return queryResult["Item"]

        raise HTTPException(
            status_code=404, detail="No state found for settlement period"
        )
    except errorfactory.ClientError as e:
        if re.search(r"ResourceNotFoundException", str(e)):
            # table is empty, create it and set initial state
            table = createTable()

            seedDataBase(
                table=table, initialTimeStamp=settlementPeriodStartTimeAsDateTime
            )

            response = table.get_item(
                Key={
                    "settlementPeriodStartTimeEpoch": Decimal(
                        settlementPeriodStartTimeAsDateTime.timestamp()
                    ),
                    "settlementPeriodDay": settlementPeriodStartTimeAsDateTime.date().isoformat(),
                },
            )
            item = response["Item"]

            item["settlementPeriodStartTime"] = settlementPeriodStartTime
            return item
        else:
            raise e


## TODO Change to a POST on /state
@app.post("/charge/", response_model=BatteryState)
def charge_battery(request: ChargeRequest):
    """
    Start charging the battery at the datetime specified.

    Returns the battery state at end of current period
    (i.e. beginning of next period).
    """
    dateTimeForRequest = datetime.strptime(
        request.settlementPeriodStartTime, DATE_TIME_FORMAT
    )

    dateTimeForNextState = dateTimeForRequest + TIMESTEPS_BETWEEN_BATTERY_STATE

    table = dynamodb.Table(BATTERY_STATE_TABLENAME)

    currentState = table.get_item(
        Key={
            "settlementPeriodDay": dateTimeForRequest.date().isoformat(),
            "settlementPeriodStartTimeEpoch": Decimal(dateTimeForRequest.timestamp()),
        },
    ).get("Item", {})

    if not currentState:
        ## Create a new current state from last known state on same day
        lastKnownStateSearch = table.query(
            KeyConditionExpression=(
                Key("settlementPeriodStartTimeEpoch").lt(
                    Decimal(dateTimeForRequest.timestamp())
                )
                & Key("settlementPeriodDay").eq(
                    dateTimeForRequest.date().isoformat()  ## state from at least the same day
                )
            ),
            ScanIndexForward=False,  ## query in descending time order
            Limit=1,
        )

        logging.info(
            f"queried for last known battery state, output was: {lastKnownStateSearch}"
        )

        if len(lastKnownStateSearch["Items"]) == 0:
            raise HTTPException(
                status_code=500,
                detail="no previous state found for the battery",
            )

        currentState = lastKnownStateSearch["Items"][0]

        currentState["settlementPeriodDay"] = dateTimeForRequest.date().isoformat()
        currentState["settlementPeriodStartTimeEpoch"] = Decimal(
            dateTimeForRequest.timestamp()
        )

        table.put_item(Item=currentState)

    if (
        request.bidVolume + cast(Decimal, currentState["sameDayImportTotal"])
    ) > Decimal(BATTERY_MAX_CHARGE_CYCLE):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max charge cycle",
        )
    elif (
        request.bidVolume + cast(Decimal, currentState["chargeLevelAtPeriodStart"])
    ) > Decimal(BATTERY_MAX_CAPACITY):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max charge capacity",
        )
    else:
        sameDayImportTotal = (
            cast(Decimal, currentState["sameDayImportTotal"]) + request.bidVolume
            if datetime.fromtimestamp(
                float(cast(Decimal, currentState["settlementPeriodStartTimeEpoch"]))
            ).date()
            == dateTimeForRequest.date()
            else request.bidVolume
        )

        stateAtChargeRequestEnd = {
            "settlementPeriodDay": dateTimeForNextState.date().isoformat(),
            "settlementPeriodStartTimeEpoch": Decimal(dateTimeForNextState.timestamp()),
            "settlementPeriodStartTime": dateTimeForNextState.strftime(
                DATE_TIME_FORMAT
            ),
            "chargeLevelAtPeriodStart": cast(
                Decimal, currentState["chargeLevelAtPeriodStart"]
            )
            + request.bidVolume,
            "sameDayImportTotal": sameDayImportTotal,
            "sameDayExportTotal": currentState["sameDayExportTotal"],
            "cumulativeImportTotal": cast(
                Decimal, currentState["cumulativeImportTotal"]
            )
            + request.bidVolume,
            "cumulativeExportTotal": currentState["cumulativeExportTotal"],
        }

        table.put_item(Item=stateAtChargeRequestEnd)
    return stateAtChargeRequestEnd


## TODO Change to a POST on /state
@app.post("/discharge/", response_model=BatteryState)
def discharge_battery(request: DischargeRequest):
    """
    Start discharging the battery at the datetime specified.

    Returns the battery state at end of current period
    (i.e. beginning of next period).
    """
    dateTimeForRequest = datetime.strptime(
        request.settlementPeriodStartTime, DATE_TIME_FORMAT
    )

    table = dynamodb.Table(BATTERY_STATE_TABLENAME)

    dateTimeForPreviousState = dateTimeForRequest - TIMESTEPS_BETWEEN_BATTERY_STATE
    dateTimeForNextState = dateTimeForRequest + TIMESTEPS_BETWEEN_BATTERY_STATE

    previousState = table.get_item(
        Key={
            "settlementPeriodStartTime": dateTimeForPreviousState.strftime(
                DATE_TIME_FORMAT
            )
        },
    )["Item"]

    if (request.offerVolume + previousState["sameDayExportTotal"]) > Decimal(
        BATTERY_MAX_DISCHARGE_CYCLE
    ):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max discharge cycle",
        )
    else:
        sameDayExportTotal = (
            previousState["sameDayExportTotal"] + request.offerVolume
            if dateTimeForPreviousState.date() == dateTimeForRequest.date()
            else request.offerVolume
        )

        stateAtChargeRequestStart = previousState
        stateAtChargeRequestStart[
            "settlementPeriodStartTime"
        ] = request.settlementPeriodStartTime
        stateAtChargeRequestEnd = {
            "settlementPeriodStartTime": dateTimeForNextState.strftime(
                DATE_TIME_FORMAT
            ),
            "chargeLevelAtPeriodStart": stateAtChargeRequestStart[
                "chargeLevelAtPeriodStart"
            ]
            - request.offerVolume,
            "sameDayImportTotal": stateAtChargeRequestStart["sameDayImportTotal"],
            "sameDayExportTotal": sameDayExportTotal,
            "cumulativeImportTotal": stateAtChargeRequestStart["cumulativeImportTotal"],
            "cumulativeExportTotal": stateAtChargeRequestStart["cumulativeExportTotal"]
            + request.offerVolume,
        }

        table.put_item(Item=stateAtChargeRequestStart)
        table.put_item(Item=stateAtChargeRequestEnd)
    return stateAtChargeRequestEnd


def createTable():
    table = dynamodb.create_table(
        TableName=BATTERY_STATE_TABLENAME,
        KeySchema=[
            {"AttributeName": "settlementPeriodDay", "KeyType": "HASH"},
            {"AttributeName": "settlementPeriodStartTimeEpoch", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "settlementPeriodDay", "AttributeType": "S"},
            {"AttributeName": "settlementPeriodStartTimeEpoch", "AttributeType": "N"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Wait until the table exists.
    table.meta.client.get_waiter("table_exists").wait(TableName=BATTERY_STATE_TABLENAME)

    return table


def seedDataBase(*, table: _Table, initialTimeStamp: datetime):
    table.put_item(
        Item={
            "settlementPeriodDay": initialTimeStamp.date().isoformat(),
            "settlementPeriodStartTimeEpoch": Decimal(initialTimeStamp.timestamp()),
            "chargeLevelAtPeriodStart": Decimal(5.00),
            "sameDayImportTotal": Decimal(0.00),
            "sameDayExportTotal": Decimal(0.00),
            "cumulativeImportTotal": Decimal(0.00),
            "cumulativeExportTotal": Decimal(0.00),
        }
    )
