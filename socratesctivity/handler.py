#!/usr/bin/env python
"""All Handlers for initial Socrates, will be split into files later."""

from json import dumps, loads
import logging
import os
import random
import uuid

import boto3

UPLOAD_BUCKET_NAME = os.environ['BUCKET_NAME']
STATEMACHINE_ARN = os.environ['STATEMACHINE_ARN']

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3 = boto3.client('s3')         # Unneeded: config=boto3.session.Config(signature_version='s3v4'))


def start_job(event, _context):
    """Start StateMachine, return presigned URL to PUT file to our S3 bucket with read access.

    Ensure the file is a PDF, in suffix and content type.
    Create a UUID jobid and use that for the SM invocation for tracking.

    Test like:
        curl -H "content-type: application/pdf" "$urlget?filename=doc.pdf"
    then set a variable 'url' to the returned value, and upload (via PUT):
        curl -v -H "content-type: application/pdf" --upload-file mydoc.pdf "$url"
    """
    # Later we will want to require userid and include it in the PSURL so
    # splitter can track it in the DB.

    LOG.debug('event=%s', dumps(event))
    content_type = event['headers'].get('content-type')  # APIG downcases this
    # TODO use basename and URLencode filename to defend against slashes etc
    filename = event['queryStringParameters'].get('filename')
    if not filename:
        return {'statusCode': 400,
                'body': 'Must supply query string "filename=..."'}
    if not filename.endswith('.pdf'):
        return {'statusCode': 400,
                'body': 'Filename must end with ".pdf"'}
    if content_type != 'application/pdf':
        return {'statusCode': 400,
                'body': 'Must specify "Content-Type: application/pdf"'}
    LOG.info('api_http_get filename=%s content-type=%s',
             filename, content_type)

    # We need to spec content-type since NG sets this header;
    # ContentType is proper boto3 spelling, no dash; value must be lowercase.
    # Might want ACL:public-read if NG needs to read and display directly, without API.
    jid = uuid.uuid4().hex
    params = {
        'Bucket': UPLOAD_BUCKET_NAME,
        'Key': f'doc_pdf/{jid}/{filename}',
        'ContentType': content_type,
        # 'ServerSideEncryption': 'AES256'
    }
    LOG.info(f'PSURL params={params}')
    url = S3.generate_presigned_url(ClientMethod='put_object',
                                    Params=params,
                                    ExpiresIn=3600)
    LOG.info('url=%s', url)
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': dumps({'url': url})}


def split_pdf(event, context):
    """TODO use PyPDF to split the PDF on S3, write pages to S3 page_pdf/uid/jid/0000.pdf.

    Returns nothing because this is triggered by state machine.
    """
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': dumps({'msg': 'Not doing anything useful right now'})}
