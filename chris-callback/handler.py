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
    if chance > 0.75:
        print(f'sending success...')
        res = sfn.send_task_success(taskToken=task_token,
                                    output=json.dumps({'msg': 'WHATEVER DUDE',
                                                       'chance': chance,
                                                       'token': task_token}))
        print(f'sendTaskSuccess res={res}')
    elif chance > 0.50:
        print(f'sending failure: error and cause go to next step input')
        res = sfn.send_task_failure(taskToken=task_token,
                                    error='UnluckyError',
                                    cause=f'You were unlucky {chance}')
        print(f'sendTaskFailure res={res}')
    elif chance > 0.25:
        print(f'sending failure: error and cause go to next step input')
        res = sfn.send_task_failure(taskToken=task_token,
                                    error='SadPath',
                                    cause=f'Not the happy path {chance}')
        print(f'sendTaskFailure res={res}')
    else:
        raise RuntimeError(f'Simulated unhandled logic error {chance}')
    return {'msg': 'This does not get sent anywhere!'}


def happy_path(event, context):
    print(f'happy_path: event={event}')
    return {'msg': 'Looking Good'}


def sad_path(event, contect):
    print(f'sad_path: event={event}')
    return {'msg': f'Sorry, this was not the happy path event={event}'}


def unlucky(event, contect):
    print(f'unlucky: event={event}')
    return {'msg': f'Your state machine was unlucky today event={event}'}
