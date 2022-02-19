import os
import time
from datetime import datetime
from typing import Optional

import boto3
from aws_lambda_powertools.utilities.parser import BaseModel, event_parser
from cmr import GranuleQuery
from geojson_pydantic.types import BBox


class GranuleQueryParameters(BaseModel):
    short_name: str
    version: str
    start_date: datetime
    end_date: datetime
    bbox: Optional[BBox]


@event_parser(model=GranuleQueryParameters)
def handler(event: GranuleQueryParameters, context):
    """
    Lambda handler for CMR query STAC asset to ndjson result.
    """
    print(
        f"Querying for {event.short_name} granules"
        f"from {event.start_date} to {event.end_date}"
    )
    api = GranuleQuery()
    granules = (
        api.short_name(event.short_name)
        .version(event.version)
        .temporal(event.start_date, event.end_date)
    )
    if event.bbox:
        granules = granules.bounding_box(*event.bbox)
    start = time.time()
    granules = granules.get_all()

    item_urls = [
        link["href"]
        for granule in granules
        for link in granule["links"]
        if link["href"][-9:] == "stac.json" and link["href"][0:5] == "https"
    ]

    client = boto3.client("sqs")
    QUEUE_URL = os.environ["QUEUE_URL"]
    for item_url in item_urls:
        client.send_message(QueueUrl=QUEUE_URL, MessageBody=item_url)
    end = time.time()
    print(end - start)


if __name__ == "__main__":
    event = {
        "short_name": "HLSS30",
        "version": "2.0",
        "start_date": "2021-07-28 05:00:00",
        "end_date": "2021-07-29 05:00:00",
        "bbox": [-123.750000, 35.029996, -110.390625, 44.213710],
    }
    handler(event, {})
