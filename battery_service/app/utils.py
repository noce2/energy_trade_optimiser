from datetime import datetime
from decimal import Decimal

from mypy_boto3_dynamodb.service_resource import _Table, Table
from boto3.dynamodb.conditions import Key
from fastapi import HTTPException
import logging


def findLastKnownState(dateTimeForRequest: datetime, table: Table):
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
    return lastKnownStateSearch["Items"][0]
