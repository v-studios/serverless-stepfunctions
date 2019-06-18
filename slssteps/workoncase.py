import random

def handler(event, context):
    my_case_id = event['Case']
    my_message = event['Message']
    my_case_status = random.choice((0, 1))
    if my_case_status == 1:
        my_message += ' was resolved...';
    elif my_case_status == 0:
        my_message += ' was unresolved...';
    else:
        raise RuntimeError(f'Uknown status={my_case_status}')
    return {'Case': my_case_id, 'Message': my_message, 'Status': my_case_status}
