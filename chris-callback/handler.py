import json

import boto3


def start_task_and_wait_for_callback(event, context):
    print(f'startwait: event={event}')
    sfn = boto3.client('stepfunctions')
    for record in event['Records']:
        message_body = json.loads(record['body'])
        task_token = message_body['TaskToken']
        params = {'output': 'Callback task completed successfully',
                  'taskToken': task_token}

        print(f'Calling Step Functions to complete callback with {params}')
        # output is the JSON output of the task as a str
        res = sfn.send_task_success(taskToken=task_token, output=
        print(f'sendTaskSuccess res={res}')
        # send_task_failure(taskToken=..., error='...', cause='...')

def notify_success(event, context):
    print(f'success: event={event}')
    return {'msg': 'Looking Good'}


def notify_failure(event, context):
    print(f'failure: event={event}')
    return {'msg': 'Failure Dude'}
