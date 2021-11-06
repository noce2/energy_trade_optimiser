from typing import Dict, Optional

from decimal import Decimal
from fastapi import FastAPI
from pydantic import BaseModel
import os

from json import load

app = FastAPI()

bid_price_predictions = {}
offer_price_predictions = {}

hi = "hi"
bye = "bye"


class Prediction(BaseModel):
    offer_prices: Dict[str, Decimal]
    bid_prices: Dict[str, Decimal]


@app.get("/")
def read_root():
    return {"Hello": "from market service"}


@app.on_event("startup")
def load_bid_prices_into_memory():
    with open("./app/bid_price_predictions.json", "r") as read:
        for (key, value) in load(read).items():
            bid_price_predictions[key] = value


@app.on_event("startup")
def load_offer_prices_into_memory():
    with open("./app/offer_price_predictions.json", "r") as read:
        for (key, value) in load(read).items():
            offer_price_predictions[key] = value


@app.get("/predictions/")
def get_predictions(timeOfPredictionRequest: str):
    print(f"predictions now has {[key for key in offer_price_predictions][0:5]}")
    return {
        "offer_prices": offer_price_predictions[timeOfPredictionRequest],
        "bid_prices": bid_price_predictions[timeOfPredictionRequest],
    }
