from os import getenv
import boto3


if __name__ == "__main__":
    dynamodb = boto3.resource(
        "dynamodb", endpoint_url=getenv("SVC_DYNAMODB_HOST"), region_name="eu-west-2"
    )
    table = dynamodb.Table("BATTERY_STATE")
    table.delete()

    table.wait_until_not_exists()
