def handler(event, context):
    my_case_id = event['input_case_id']
    my_message = 'Case ' + my_case_id + ': opened...'
    return {'Case': my_case_id, 'Message': my_message}
