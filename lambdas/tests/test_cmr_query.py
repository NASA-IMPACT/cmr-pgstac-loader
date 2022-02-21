import os
from datetime import datetime
from unittest.mock import patch

from lambdas.cmr_query.handler import handler

queue_url = "url"


@patch.dict(
    os.environ,
    {
        "QUEUE_URL": queue_url,
    },
)
@patch("lambdas.cmr_query.handler.boto3")
@patch("lambdas.cmr_query.handler.GranuleQuery")
def test_handler(granule_query, boto3):
    event = {
        "short_name": "HLSS30",
        "version": "2.0",
        "start_date": "2021-07-28 05:00:00",
        "end_date": "2021-07-29 05:00:00",
        "bbox": [-123.750000, 35.029996, -110.390625, 44.213710],
    }
    short_name = granule_query.return_value.short_name
    version = short_name.return_value.version
    temporal = version.return_value.temporal
    bounding_box = temporal.return_value.bounding_box
    item_url = "https://lpdaac/some_granule_stac.json"
    bounding_box.return_value.get_all.return_value = [
        {
            "links": [
                {
                    "href": item_url,
                }
            ],
        }
    ]
    handler(event, {})
    short_name.assert_called_with(event["short_name"])
    version.assert_called_with(event["version"])
    temporal.assert_called_with(
        datetime.fromisoformat(event["start_date"]),
        datetime.fromisoformat(event["end_date"]),
    )
    bounding_box.assert_called_with(*event["bbox"])
    boto3.client.return_value.send_message.assert_called_with(
        QueueUrl=queue_url, MessageBody=item_url
    )
