#!/usr/bin/env python
"""APIGW gives us filename, return S3 presigned URL for upload."""
from json import dumps
import logging
from botocore.client import Config
import boto3
from uuid import uuid4
from datetime import datetime
from models import PDFUpload
import os

UPLOAD_BUCKET_NAME = "doc-pdfs"
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3 = boto3.client('s3', config=Config(region_name='ap-southeast-1', signature_version='s3v4'))


def api_http_get(event, _context):
    """Return a presigned URL to PUT a file to in our S3 bucket, with read access.

    Ensure the file is a PDF, in suffix and content type.
    Test like:
        curl -i -H "Content-Type: application/pdf" "$urlget"?filename=ALEX.JPG
    then set a variable 'url' to the returned value, and upload:
        curl -v -H "Content-Type: application/pdf" --upload-file mydoc.pdf "$url"
    """
    LOG.info('event=%s', dumps(event))
    content_type = event['headers'].get('content-type')  # APIG downcases this
    filename = event['queryStringParameters'].get('filename')
    if not filename:
        return {'statusCode': 400,
                'body': 'Must supply query string "filename=..."'}
    if not filename.endswith('.pdf'):
        return {'statusCode': 400,
                'body': 'Filename must end with ".pdf"'}
    if content_type != 'application/pdf':
        return {'statusCode': 400,
                'body': 'Filename must have "Content-Type: application/pdf"'}
    LOG.info('api_http_get filename=%s content-type=%s',
             filename, content_type)

    # We need to spec content-type since NG sets this header;
    # ContentType is proper boto3 spelling, no dash; value must be lowercase.
    # Might want ACL:public-read if NG needs to read and display directly, without API.
    file_info = save_info(filename)
    jobid = file_info.uuid
    params = {
        'Bucket': UPLOAD_BUCKET_NAME,
        'Key': 'doc_pdf/' + str(jobid) + '/' + filename,
        # 'Key': filename,
        'ContentType': content_type,
        # 'ServerSideEncryption': 'AES256'
    }

    url = S3.generate_presigned_url('put_object', Params=params, ExpiresIn=3600)
    body_json = {'url': url, 'jobid': jobid, "key": 'doc_pdf/' + str(jobid) + '/' + filename}
    sf_arn = os.environ.get('SF_ARN', "")
    client = boto3.client('stepfunctions')
    client.start_execution(
        stateMachineArn=sf_arn,
        name=jobid,
        input=dumps(body_json)
    )
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': dumps(body_json)}


def save_info(desired_filename):
    """Save information when user get presigned url."""
    file_upload = PDFUpload(
        desired_filename=desired_filename,
        state=0,
        filename='',
        createdAt=datetime.now()
    )
    file_upload.uuid = str(uuid4())
    file_upload.save_with_log()
    return file_upload
