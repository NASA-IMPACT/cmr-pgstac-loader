import os
from unittest.mock import patch

import pytest

from lambdas.build_ndjson.handler import handler, update_href


@pytest.fixture
def asset():
    return {"href": "https://nasa.gov/lp-prod-protected/B01.tif"}


bucket = "bucket"
queue_url = "url"


@patch.dict(
    os.environ,
    {
        "BUCKET": bucket,
        "QUEUE_URL": queue_url,
    },
)
@patch("lambdas.build_ndjson.handler.boto3")
@patch("lambdas.build_ndjson.handler.stream_stac_items")
@patch("lambdas.build_ndjson.handler.uuid4")
def test_handler(uuid4, stream_stac, boto3):
    path = "path"
    uuid = "1"
    uuid4.return_value = uuid
    key = f"s3://{bucket}/{uuid}.ndjson"
    event = {"Records": [{"body": path}]}
    handler(event, {})
    stream_stac.assert_called_with([path], key)
    boto3.client.return_value.send_message.assert_called_with(
        QueueUrl=queue_url, MessageBody=key
    )


def test_update_href(asset):
    updated_asset = update_href(asset)
    assert updated_asset["href"] == "s3://lp-prod-protected/B01.tif"
