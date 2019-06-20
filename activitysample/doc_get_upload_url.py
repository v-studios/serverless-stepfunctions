#!/usr/bin/env python
"""APIGW gives us filename, return S3 presigned URL for upload."""

from datetime import datetime
from os import environ
from json import dumps, loads
from sys import argv
import logging

from botocore.client import Config
import boto3

UPLOAD_BUCKET_NAME = "doc-pdfs"
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3 = boto3.client('s3', config=Config(signature_version='s3v4'))


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
    params = {
        'Bucket': UPLOAD_BUCKET_NAME,
        'Key': 'doc_pdf/' + filename,
        'ContentType': content_type,
        # 'ServerSideEncryption': 'AES256'
    }
    url = S3.generate_presigned_url('put_object', Params=params, ExpiresIn=3600)
    LOG.info('url=%s', url)
    body_json = {'url': url}
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': dumps(body_json)}
