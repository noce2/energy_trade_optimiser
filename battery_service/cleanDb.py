from os import getenv
import re
import boto3
from botocore import errorfactory


if __name__ == "__main__":
    dynamodb = boto3.resource(
        "dynamodb", endpoint_url=getenv("SVC_DYNAMODB_HOST"), region_name="eu-west-2"
    )

    try:
        table = dynamodb.Table("BATTERY_STATE")
        table.delete()

        table.wait_until_not_exists()
    except errorfactory.ClientError as e:
        if re.search(r"ResourceNotFoundException", str(e)):
            pass
        else:
            raise e
