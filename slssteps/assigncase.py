def handler(event, context):
    my_case_id = event['Case']
    my_message = event['Message'] + ' assigned...'
    return {'Case': my_case_id, 'Message': my_message}
