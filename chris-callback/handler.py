import json
from random import random

import boto3


def start_task_and_wait_for_callback(event, context):
    print(f'startwait: event={event}')
    sfn = boto3.client('stepfunctions')
    task_token = event['taskToken']
    print(f'task_token={task_token}')
    # Here we would do something useful, then continue the statemachine
    # with success or failure depending on outcome of that work;
    # for now, just randomly pick one.
    # TODO: create a Lambda exception and see how SNF detects it
    chance = random()
    print(f'chance={chance}')
    if chance > 0.66:
        print(f'sending success...')
        res = sfn.send_task_success(taskToken=task_token,
                                    output=json.dumps({'msg': 'WHATEVER DUDE',
                                                       'chance': chance,
                                                       'taskToken': task_token}))
        print(f'sendTaskSuccess res={res}')
    elif chance > 0.33:
        print(f'sending failure: error and cause go to next step input')
        res = sfn.send_task_failure(taskToken=task_token,
                                    error='UnluckyError',
                                    cause=f'You were unlucky, chance={chance}')
        print(f'sendTaskFailure res={res}')
    else:
        raise RuntimeError(f'Simulated unhandled logic error chance={chance}')
    return {'msg': 'This does not get sent anywhere!'}


def notify_success(event, context):
    print(f'success: event={event}')
    return {'msg': 'Looking Good'}


def notify_unlucky(event, contect):
    print(f'unluck error: event={event}')
    return {'msg': f'Your state machine was unlucky today event={event}'}


# def notify_task_failed(event, context):
#     print(f'task failed: event={event}')
#     return {'msg': 'Task Failed, can we get Python traceback?'}
