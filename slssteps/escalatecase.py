def handler(event, context):
    my_case_id = event['Case']
    my_case_status = event['Status']
    my_message = event['Message'] + 'escalating.'
    return {'Case': my_case_id, 'Message': my_message, 'Status': my_case_status}
