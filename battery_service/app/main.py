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

        if not (table.table_status == "ACTIVE"):
            table = createTable()

        if table.item_count == 0:
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


@app.post("/charge/", response_model=BatteryState)
def charge_battery(request: ChargeRequest):
    dateTimeForRequest = datetime.strptime(
        request.settlementPeriodStartTime, DATE_TIME_FORMAT
    )

    dateTimeForPreviousState = dateTimeForRequest - TIMESTEPS_BETWEEN_BATTERY_STATE

    state = get_battery_state(dateTimeForPreviousState.strftime(DATE_TIME_FORMAT))

    if (request.bidVolume + state["sameDayImportTotal"]) > Decimal(
        BATTERY_MAX_CHARGE_CYCLE
    ):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max charge cycle",
        )
    else:
        newState = {
            "settlementPeriodStartTime": request.settlementPeriodStartTime,
            "chargeLevelAtPeriodStart": state["chargeLevelAtPeriodStart"]
            + request.bidVolume,
            "sameDayImportTotal": state["sameDayImportTotal"] + request.bidVolume,
            "sameDayExportTotal": state["sameDayExportTotal"],
            "cumulativeImportTotal": state["cumulativeImportTotal"] + request.bidVolume,
            "cumulativeExportTotal": state["cumulativeExportTotal"],
        }

        table = dynamodb.Table(BATTERY_STATE_TABLENAME)
        table.put_item(Item=newState)
    return newState


@app.post("/discharge/", response_model=BatteryState)
def discharge_battery(request: DischargeRequest):
    dateTimeForRequest = datetime.strptime(
        request.settlementPeriodStartTime, DATE_TIME_FORMAT
    )

    dateTimeForPreviousState = dateTimeForRequest - TIMESTEPS_BETWEEN_BATTERY_STATE

    state = get_battery_state(dateTimeForPreviousState.strftime(DATE_TIME_FORMAT))

    if (request.offerVolume + state["sameDayExportTotal"]) > Decimal(
        BATTERY_MAX_DISCHARGE_CYCLE
    ):
        raise HTTPException(
            status_code=403,
            detail="Request will cause battery to exceed max discharge cycle",
        )
    else:
        newState = {
            "settlementPeriodStartTime": request.settlementPeriodStartTime,
            "chargeLevelAtPeriodStart": state["chargeLevelAtPeriodStart"]
            - request.offerVolume,
            "sameDayImportTotal": state["sameDayImportTotal"],
            "sameDayExportTotal": state["sameDayExportTotal"] + request.offerVolume,
            "cumulativeImportTotal": state["cumulativeImportTotal"],
            "cumulativeExportTotal": state["cumulativeExportTotal"]
            + request.offerVolume,
        }

        table = dynamodb.Table(BATTERY_STATE_TABLENAME)
        table.put_item(Item=newState)
    return newState


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
