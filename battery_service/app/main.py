from decimal import Decimal
from typing import Optional
import boto3
import re

from fastapi import FastAPI, HTTPException
from botocore import errorfactory
from os import getenv

from mypy_boto3_dynamodb.service_resource import _Table

app = FastAPI()
dynamodb = boto3.resource(
    "dynamodb", endpoint_url=getenv("SVC_DYNAMODB_HOST"), region_name="eu-west-2"
)
BATTERY_STATE_TABLENAME = "BATTERY_STATE"


@app.get("/")
def read_root():
    return {"Hello": "from battery service"}


@app.get("/state/")
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
            "currentChargeLevel": Decimal(5.00),
            "sameDayImportTotal": Decimal(0.00),
            "sameDayExportTotal": Decimal(0.00),
            "cumulativeImportTotal": Decimal(0.00),
            "cumulativeExportTotal": Decimal(0.00),
        }
    )
