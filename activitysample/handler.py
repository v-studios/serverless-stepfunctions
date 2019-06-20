"""Simple example."""
import random
import logging
import os


def open(event, context):
    """Open case."""
    activity_arn = os.environ.get('ACTIVITY_ARN', "")
    my_case_id = event["inputCaseID"]
    my_mesasge = "Case " + my_case_id + ": opened..."
    result = {"case": my_case_id, "message": my_mesasge, "activity_arn": activity_arn}
    return result


def assign(event, context):
    """Assign."""
    logging.error("Event: {}".format(event))
    if type(event) is list:
        event = event[0]
    my_case_id = event["case"]
    my_mesasge = event["message"] + "assigned..."

    result = {"case": my_case_id, "message": my_mesasge}
    return result


def work(event, context):
    """Work on."""
    my_case_status = random.randrange(0, 2)
    my_case_id = event["case"]
    my_mesasge = event["message"]
    logging.info("Event: {}".format(event))
    if my_case_status == 1:
        # Support case has been resolved
        my_mesasge = my_mesasge + "resolved..."
    else:
        # Support case is still open
        my_mesasge = my_mesasge + "unresolved..."

    result = {"case": my_case_id, "status": my_case_status, "message": my_mesasge}
    return result


def escalate(event, context):
    """Escalate func."""
    my_case_id = event["case"]
    my_case_status = event["status"]
    my_mesasge = event["message"] + "escalating."
    result = {"case": my_case_id, "status": my_case_status, "message": my_mesasge}
    return result


def close(event, context):
    """Close func."""
    my_case_id = event["case"]
    my_case_status = event["status"]
    my_mesasge = event["message"] + "closed."
    result = {"case": my_case_id, "status": my_case_status, "message": my_mesasge}
    return result
