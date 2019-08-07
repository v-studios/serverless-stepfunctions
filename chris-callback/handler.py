import json

import boto3


def start_task_and_wait_for_callback(event, context):
    print(f'startwait: event={event}')
    sfn = boto3.client('stepfunctions')
    task_token = event['taskToken']
    print(f'task_token={task_token}')
    # Here we would do something useful, then continue the statemachine
    print(f'sending success...')
    res = sfn.send_task_success(taskToken=task_token,
                                output=json.dumps({'msg': 'WHATEVER DUDE',
                                                   'taskToken': task_token}))
    print(f'sendTaskSuccess res={res}')
    # send_task_failure(taskToken=..., error='...', cause='...')
    return {'msg': 'does this really get sent anywhere?'}

# def notify_success(event, context):
#     print(f'success: event={event}')
#     return {'msg': 'Looking Good'}


# def notify_failure(event, context):
#     print(f'failure: event={event}')
#     return {'msg': 'Failure Dude'}
