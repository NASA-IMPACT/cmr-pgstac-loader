import io
import json
import os
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from aiobotocore.response import StreamingBody
from asynctest import CoroutineMock
from asynctest import patch as async_patch

from lambdas.build_ndjson.handler import handler, stream_stac_items, update_href


class AsyncBytesIO(io.BytesIO):
    async def read(self, amt: int = -1):
        return super().read(amt if amt != -1 else None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def asset():
    return {"href": "https://nasa.gov/lp-prod-protected/B01.tif"}


bucket = "bucket"
queue_url = "url"
role_arn = "arn"


@patch.dict(
    os.environ,
    {
        "BUCKET": bucket,
        "QUEUE_URL": queue_url,
        "ROLE_ARN": role_arn,
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
    stream_stac.assert_called_with([path], key, role_arn)
    boto3.client.return_value.send_message.assert_called_with(
        QueueUrl=queue_url, MessageBody=key
    )


def test_update_href(asset):
    updated_asset = update_href(asset)
    assert updated_asset["href"] == "s3://lp-prod-protected/B01.tif"


@patch("lambdas.build_ndjson.handler.write_item")
@patch("lambdas.build_ndjson.handler.get_role_credentials")
@async_patch("lambdas.build_ndjson.handler.aiohttp.ClientSession.get")
@patch("lambdas.build_ndjson.handler.get_session")
@patch("lambdas.build_ndjson.handler.open")
@pytest.mark.asyncio
async def test_stream_stac_items(
    smart_open, get_session, get, get_role_credentials, write_item
):
    item = {"test": "test"}
    key = "key"
    role_arn = "role_arn"
    get.return_value.__aenter__.return_value.json = CoroutineMock(side_effect=[item])

    url = "http://test/S30/item.json"
    await stream_stac_items([url], key, role_arn)
    smart_open.assert_called_with(key, "w")
    get.assert_called_with(url)
    write_item.assert_called_with(smart_open().__enter__(), item, urlparse(url))

    url = "s3://test/S30/item.json"
    get_session.assert_called_with()
    get_object = (
        get_session.return_value.create_client.return_value.__aenter__.return_value.get_object
    )
    val = str.encode(json.dumps(item))
    get_object.return_value = {"Body": StreamingBody(AsyncBytesIO(val), len(val))}
    await stream_stac_items([url], key, role_arn)
    get_object.assert_called_with(Bucket="test", Key="S30/item.json")
    write_item.assert_called_with(smart_open().__enter__(), item, urlparse(url))
