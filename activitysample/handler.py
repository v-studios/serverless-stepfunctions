"""Simple example."""
import logging
import os
from doc_pdf_split import _download_split_upload

UPLOAD_BUCKET_NAME = "doc-pdfs"


def split_doc_pdf(event, context):
    """splitPDF."""
    activity_arn = os.environ.get('ACTIVITY_ARN', "")
    logging.error("splitPDF event: {}".format(event))
    key = event.get('key', '')
    bucket_name = UPLOAD_BUCKET_NAME
    _download_split_upload(bucket_name, key)
    result = {"message": "splitPDF", "activity_arn": activity_arn}
    return result


def return_presigned_url(event, context):
    """return_presigned_url."""
    logging.error("return_presigned_url event: {}".format(event))
    return event
