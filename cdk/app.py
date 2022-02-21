import os

from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from aws_cdk import core
from aws_cdk.aws_lambda_event_sources import SqsEventSource

# Required env settings
STACKNAME = os.environ["STACKNAME"]
PROJECT = os.environ["PROJECT"]
SECRET_NAME = os.environ["SECRET_NAME"]


class Stack(core.Stack):
    def __init__(self, scope: core.Construct, stack_name: str, **kwargs) -> None:
        super().__init__(scope, stack_name, **kwargs)

        self.cmr_query_role = iam.Role(
            self,
            "CMRQueryRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        self.bucket = s3.Bucket(
            self,
            "NDJsonBucket",
            bucket_name=f"{stack_name}-ndjson",
        )

        self.item_dlq = sqs.Queue(
            self,
            "ItemDLQ",
            retention_period=core.Duration.days(14),
        )
        self.item_queue = sqs.Queue(
            self,
            "ItemQueue",
            visibility_timeout=core.Duration.minutes(1),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.item_dlq,
            ),
        )
        self.item_queue.grant_send_messages(self.cmr_query_role)

        self.cmr_query_function = aws_lambda.Function(
            self,
            f"{stack_name}-cmr-query-lambda",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            role=self.cmr_query_role,
            code=aws_lambda.Code.from_docker_build(
                path=os.path.abspath("./"),
                file="lambdas/Dockerfile.cmr_query",
                platform="linux/amd64",
            ),
            handler="handler.handler",
            memory_size=8000,
            timeout=core.Duration.minutes(15),
            environment={"QUEUE_URL": self.item_queue.queue_url},
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        self.build_ndjson_role = iam.Role(
            self,
            "BuildNDJsonRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        self.item_queue.grant_consume_messages(self.build_ndjson_role)
        self.bucket.grant_write(self.build_ndjson_role)

        self.ndjson_dlq = sqs.Queue(
            self,
            "NDJsonDLQ",
            retention_period=core.Duration.days(14),
        )
        self.ndjson_queue = sqs.Queue(
            self,
            "NDJsonQueue",
            visibility_timeout=core.Duration.minutes(15),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.ndjson_dlq,
            ),
        )
        self.ndjson_queue.grant_send_messages(self.build_ndjson_role)
        self.build_ndjson_function = aws_lambda.Function(
            self,
            f"{stack_name}-build_ndjson-lambda",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            role=self.build_ndjson_role,
            code=aws_lambda.Code.from_docker_build(
                path=os.path.abspath("./"),
                file="lambdas/Dockerfile.build_ndjson",
                platform="linux/amd64",
            ),
            handler="handler.handler",
            memory_size=8000,
            timeout=core.Duration.minutes(10),
            environment={
                "BUCKET": self.bucket.bucket_name,
                "QUEUE_URL": self.ndjson_queue.queue_url,
            },
        )

        item_event_source = SqsEventSource(
            self.item_queue,
            batch_size=100,
            max_batching_window=core.Duration.seconds(300),
            report_batch_item_failures=True,
        )
        self.build_ndjson_function.add_event_source(item_event_source)

        self.pgstac_loader_role = iam.Role(
            self,
            "PGStacLoaderRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        self.ndjson_queue.grant_consume_messages(self.pgstac_loader_role)
        self.bucket.grant_read(self.pgstac_loader_role)

        self.pgstac_secret = secretsmanager.Secret.from_secret_arn(
            self,
            id="PGStacSecret",
            secret_arn=SECRET_NAME,
        )
        self.pgstac_secret.grant_read(self.pgstac_loader_role)

        self.pgstac_loader = aws_lambda.Function(
            self,
            f"{stack_name}-pgstac-loader-lambda",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            role=self.pgstac_loader_role,
            code=aws_lambda.Code.from_docker_build(
                path=os.path.abspath("./"),
                file="lambdas/Dockerfile.pgstac_loader",
                platform="linux/amd64",
            ),
            handler="handler.handler",
            memory_size=8000,
            timeout=core.Duration.minutes(15),
            environment={
                "SECRET_NAME": SECRET_NAME,
            },
            reserved_concurrent_executions=3,
        )
        ndjson_event_source = SqsEventSource(
            self.ndjson_queue,
            batch_size=5,
            max_batching_window=core.Duration.seconds(300),
            report_batch_item_failures=True,
        )
        self.pgstac_loader.add_event_source(ndjson_event_source)


app = core.App()
Stack(scope=app, stack_name=STACKNAME)

for k, v in {
    "Project": PROJECT,
    "Stack": STACKNAME,
}.items():
    core.Tags.of(app).add(k, v, apply_to_launched_instances=True)

app.synth()
