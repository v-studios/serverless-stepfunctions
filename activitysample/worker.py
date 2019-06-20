"""Simple worker."""
import logging
import boto3
import os
# import random
from botocore.exceptions import ClientError


def my_worker(event, context):
    """Simple worker."""
    activity_arn = os.environ.get('ACTIVITY_ARN', "")
    worker_name = "mytestworker"
    client = boto3.client('stepfunctions')
    my_case_status = 1
    try:
        response = client.get_activity_task(
            activityArn=activity_arn,
            workerName=worker_name
        )
        logging.error("My worker response: {}".format(response))
        if my_case_status == 1:
            client.send_task_success(
                taskToken=response["taskToken"],
                output=response["input"]
            )
        else:
            client.send_task_failure(
                taskToken=response["taskToken"],
                error='Unlucky',
                cause='Unlucky Cause'
            )

    except ClientError as e:
        logging.error(e)

    return 1
