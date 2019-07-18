#!/usr/bin/env python
"""All Handlers for initial Socrates, will be split into files later."""

from json import dumps, loads
import logging
import os
import random
import uuid

import boto3

UPLOAD_BUCKET_NAME = os.environ['BUCKET_NAME']
#STATEMACHINE_ARN = os.environ['STATEMACHINE_ARN']

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3 = boto3.client('s3')         # Unneeded: config=boto3.session.Config(signature_version='s3v4'))


def get_upload_url(event, _context):
    """Return presigned URL to PUT file to our S3 bucket with read access.

    Ensure the file is a PDF, in suffix and content type.
    Create a UUID jobid and use that for the SM invocation for tracking.

    NOTE: our Lambda must be given s3:PutObject rights or PUT to the URL will be denied.

    Test like:
        curl -H "content-type: application/pdf" "$urlget?filename=doc.pdf"
    then set a variable 'urlupload' to the returned value, and upload (via PUT):
        curl -v -H "content-type: application/pdf" --upload-file mydoc.pdf "$urlupload"
    """
    # Later want userid so we can include it in PSURL for tracking
    LOG.info('Got Task? event=%s', dumps(event))
    LOG.debug('Got Task? context=%s', dumps(dir(_context)))
    try:
        filename = event['queryStringParameters']['filename']  # TODO: basename, URLdecode defense
    except Exception as err:
        return {'statusCode': 400,
                'body': 'Must supply query string "filename=..."'}
    if not filename.endswith('.pdf'):
        return {'statusCode': 400,
                'body': 'Filename must end with ".pdf"'}
    try:
        content_type = event['headers']['content-type']  # APIG downcases this
        if content_type != 'application/pdf':
            raise ValueError('Must specify Content-Type: application/pdf')
    except Exception as err:
        return {'statusCode': 400, 'body': f'{err}'}
    LOG.info(f'content-type={content_type} filename={filename}')

    # We need to spec content-type since NG sets this header;
    # ContentType is boto3 key spelling, no dash; the value must be lowercase.
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
    LOG.debug('url=%s', url)
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},  # for CORS
            'body': dumps({'url': url})}


def uploaded(event, context):
    """Handle the S3 ObjectCreated trigger: just record in DB and start the statemachine."""
    LOG.info(f'event: {dumps(event)}')
    s3rec = event['Records'][0]['s3']  # only the first, but there should only be one for S3
    LOG.info('s3rec={s3rec}')
    bucket = s3rec['bucket']['name']
    key = s3rec['object']['key']
    size = s3rec['object']['size']
    etag = s3rec['object']['eTag']
    _doc_pdf, jid, name_pdf = key.split('/')
    LOG.info(f'bucket={bucket} etag={etag} size={size} key={key} jid={jid} name_pdf={name_pdf}')
    # TODO put info into DB
    # TODO trigger start of statemachine
    return {'bucket': bucket, 'key': key, 'etag': etag, 'size': size, 'jid': jid, 'name_pdf': name_pdf}  # to next step


def split_pdf(event, context):
    """TODO use PyPDF to split the PDF on S3, write pages to S3 page_pdf/uid/jid/0000.pdf.

    Returns nothing because this is triggered by state machine.
    """
    return {'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': dumps({'msg': 'Not doing anything useful right now'})}


