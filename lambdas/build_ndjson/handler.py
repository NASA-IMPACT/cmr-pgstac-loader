import asyncio
import json
import os
from typing import Dict, List
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp
import boto3
from aiobotocore.session import get_session
from aws_lambda_powertools.utilities.data_classes import SQSEvent, event_source
from smart_open import open


async def get_role_credentials(session, role_arn):
    async with session.create_client("sts") as client:
        response = await client.assume_role(
            RoleArn=role_arn, RoleSessionName="RoleSession"
        )
    return response["Credentials"]


def update_href(asset: Dict):
    """Update asset protected http endpoint to the internal S3 endpoint"""
    href = asset["href"]
    url_components = urlparse(href)
    hostname = url_components.hostname
    scheme = url_components.scheme
    if url_components.path.split("/")[1] == "lp-prod-protected":
        s3_href = href.replace(f"{scheme}://{hostname}/", "s3://")
        updated_asset = asset.copy()
        updated_asset["href"] = s3_href
    else:
        updated_asset = asset
    return updated_asset


def write_item(f, item, url_components):
    if url_components.scheme == "http" or url_components.scheme == "https":
        collection = url_components.path.split("/")[2].split(".")[0]
    elif url_components.scheme == "s3":
        collection = f"HLS{url_components.path.split('/')[1]}"
    item["collection"] = collection
    assets = {k: update_href(v) for (k, v) in item["assets"].items()}
    item["assets"] = assets
    f.write(json.dumps(item) + "\n")


async def stream_stac_items(urls: List[str], key: str, role_arn: str):
    aiobotocore_session = get_session()
    credentials = await get_role_credentials(aiobotocore_session, role_arn)
    with open(key, "w") as f:
        async with aiohttp.ClientSession() as session:
            async with aiobotocore_session.create_client(
                "s3",
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            ) as client:
                for url in urls:
                    url_components = urlparse(url)
                    if (
                        url_components.scheme == "http"
                        or url_components.scheme == "https"
                    ):
                        async with session.get(url) as resp:
                            item = await resp.json()
                            write_item(f, item, url_components)
                    elif url_components.scheme == "s3":
                        response = await client.get_object(
                            Bucket=url_components.hostname, Key=url_components.path[1:]
                        )
                        async with response["Body"] as stream:
                            content = await stream.read()
                            item = json.loads(content.decode())
                            write_item(f, item, url_components)


@event_source(data_class=SQSEvent)
def handler(event: SQSEvent, context):
    BUCKET = os.environ["BUCKET"]
    QUEUE_URL = os.environ["QUEUE_URL"]
    ROLE_ARN = os.environ["ROLE_ARN"]

    item_urls = [record.body for record in event.records]
    file_id = str(uuid4())
    key = f"s3://{BUCKET}/{file_id}.ndjson"
    asyncio.run(stream_stac_items(item_urls, key, ROLE_ARN))
    client = boto3.client("sqs")
    client.send_message(QueueUrl=QUEUE_URL, MessageBody=key)
