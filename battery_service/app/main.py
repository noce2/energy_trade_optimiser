from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import boto3
import re

from fastapi import FastAPI, HTTPException
from botocore import errorfactory
from os import getenv

from mypy_boto3_dynamodb.service_resource import _Table

from app.models import BatteryState, ChargeRequest, DischargeRequest

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
    try:

        table = dynamodb.Table(BATTERY_STATE_TABLENAME)
        table.load()

        if not (table.table_status == "ACTIVE"):
            table = createTable()

        if table.item_count == 0:
            ## TODO FIX ME!!! ALWAYS SEDDING DATA!!! NO PERSISTENCe
            seedDataBase(table=table, initialTimeStamp=settlementPeriodStartTime)

        queryResult = table.get_item(
            Key={"settlementPeriodStartTime": settlementPeriodStartTime},
        )
        if queryResult and queryResult.get("Item", None):
            return queryResult["Item"]

        raise HTTPException(
            status_code=404, detail="No state found for settlement period"
        )
    except errorfactory.ClientError as e:
        if re.search(r"ResourceNotFoundException", str(e)):
            # table is empty, create it and set initial state
            table = createTable()

            seedDataBase(table=table, initialTimeStamp=settlementPeriodStartTime)

            response = table.get_item(
                Key={"settlementPeriodStartTime": settlementPeriodStartTime}
            )
            item = response["Item"]
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

    if (request.bidVolume + previousState["sameDayImportTotal"]) > Decimal(
        BATTERY_MAX_CHARGE_CYCLE
    ):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max charge cycle",
        )
    else:
        sameDayImportTotal = (
            previousState["sameDayImportTotal"] + request.bidVolume
            if dateTimeForPreviousState.date() == dateTimeForRequest.date()
            else request.bidVolume
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
            + request.bidVolume,
            "sameDayImportTotal": sameDayImportTotal,
            "sameDayExportTotal": stateAtChargeRequestStart["sameDayExportTotal"],
            "cumulativeImportTotal": stateAtChargeRequestStart["cumulativeImportTotal"]
            + request.bidVolume,
            "cumulativeExportTotal": stateAtChargeRequestStart["cumulativeExportTotal"],
        }

        table.put_item(Item=stateAtChargeRequestStart)
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
        KeySchema=[{"AttributeName": "settlementPeriodStartTime", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "settlementPeriodStartTime", "AttributeType": "S"}
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Wait until the table exists.
    table.meta.client.get_waiter("table_exists").wait(TableName=BATTERY_STATE_TABLENAME)

    return table


def seedDataBase(*, table: _Table, initialTimeStamp: str):
    table.put_item(
        Item={
            "settlementPeriodStartTime": initialTimeStamp,
            "chargeLevelAtPeriodStart": Decimal(5.00),
            "sameDayImportTotal": Decimal(0.00),
            "sameDayExportTotal": Decimal(0.00),
            "cumulativeImportTotal": Decimal(0.00),
            "cumulativeExportTotal": Decimal(0.00),
        }
    )
