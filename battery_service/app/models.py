from decimal import Decimal
from pydantic import BaseModel


class ChargeRequest(BaseModel):
    settlementPeriodStartTime: str
    bidVolume: Decimal


class DischargeRequest(BaseModel):
    settlementPeriodStartTime: str
    offerVolume: Decimal


class BatteryState(BaseModel):
    settlementPeriodStartTime: str
    chargeLevelAtPeriodStart: Decimal
    sameDayImportTotal: Decimal
    sameDayExportTotal: Decimal
    cumulativeImportTotal: Decimal
    cumulativeExportTotal: Decimal
