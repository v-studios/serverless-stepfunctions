"""Worker."""
import logging
import boto3
import os
import json
from botocore.exceptions import ClientError


def notify_upload_worker(event, context):
    """Simple worker."""
    logging.error("Worker trigger by S3 event: {}".format(event))
    activity_arn = os.environ.get('ACTIVITY_ARN', "")
    worker_name = "notify_upload_worker"
    client = boto3.client('stepfunctions')
    my_case_status = 1
    try:
        response = client.get_activity_task(
            activityArn=activity_arn,
            workerName=worker_name
        )
        logging.error("My worker response: {}".format(response))
        input_json = json.loads(response["input"])
        input_str = json.dumps(input_json)
        if my_case_status == 1:
            res = client.send_task_success(
                taskToken=response["taskToken"],
                output=input_str
            )
            logging.error("response of send_task_success {}".format(res))
        else:
            res = client.send_task_failure(
                taskToken=response["taskToken"],
                error='Unlucky',
                cause='Unlucky Cause'
            )
            logging.error("response of send_task_failure {}".format(res))

    except ClientError as e:
        logging.error(e)

    return 1
