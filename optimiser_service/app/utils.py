from datetime import datetime
from decimal import Decimal
from loguru import logger
from json import dumps
from fastapi.encoders import jsonable_encoder

from app.models import BidOfferPair


def log_optimiser_current_state(
    *,
    simulationTimestamp: datetime,
    batteryStateOfCharge: Decimal,
    totalEnergyImportedFromStartToDate: Decimal,
    totalEnergyExportedFromStartToDate: Decimal,
    totalEnergyImportedOnCurrentDay: Decimal,
    totalEnergyExportedOnCurrentDay: Decimal,
    bidPricePrediction: Decimal,
    offerPricePrediction: Decimal,
    submittedBidOfferPair: BidOfferPair,
    bidAccepted: bool,
    offerAccepted: bool,
):
    logger.success(
        dumps(
            {
                "simulationTimestamp": simulationTimestamp,
                "batteryStateOfCharge": jsonable_encoder(batteryStateOfCharge),
                "totalEnergyExportedFromStartToDate": jsonable_encoder(
                    totalEnergyExportedFromStartToDate
                ),
                "totalEnergyImportedFromStartToDate": jsonable_encoder(
                    totalEnergyImportedFromStartToDate
                ),
                "totalEnergyExportedOnCurrentDay": jsonable_encoder(
                    totalEnergyExportedOnCurrentDay
                ),
                "totalEnergyImportedOnCurrentDay": jsonable_encoder(
                    totalEnergyImportedOnCurrentDay
                ),
                "bidPricePrediction": jsonable_encoder(bidPricePrediction),
                "offerPricePrediction": jsonable_encoder(offerPricePrediction),
                "submittedBidOfferPair": jsonable_encoder(submittedBidOfferPair),
                "bidAccepted": bidAccepted,
                "offerAccepted": offerAccepted,
            }
        )
    )
