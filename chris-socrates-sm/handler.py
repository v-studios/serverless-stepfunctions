#!/usr/bin/env python
"""All Handlers for initial Socrates, will be split into files later."""

from json import dumps, loads
import io
import logging
import os
import random
import uuid

import boto3

from PyPDF2 import PdfFileReader, PdfFileWriter


UPLOAD_BUCKET_NAME = os.environ['BUCKET_NAME']
STATEMACHINE_ARN = os.environ['STATEMACHINE_ARN']

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
    LOG.debug('Got Task? event=%s', dumps(event))
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
    """Handle the S3 ObjectCreated trigger: just start the state machine."""
    LOG.info(f'event: {dumps(event)}')
    LOG.info(f'STATEMACHINE_ARN={STATEMACHINE_ARN}')
    s3rec = event['Records'][0]['s3']  # only the first, but there should only be one for S3
    bucket = s3rec['bucket']['name']
    key = s3rec['object']['key']
    size = s3rec['object']['size']
    etag = s3rec['object']['eTag']
    _doc_pdf, jid, name_pdf = key.split('/')
    LOG.info(f'bucket={bucket} etag={etag} size={size} key={key} jid={jid} name_pdf={name_pdf}')
    sf = boto3.client('stepfunctions')
    sf_input = dumps({'bucket': bucket, 'key': key, 'etag': etag, 'size': size, 'jid': jid, 'name_pdf': name_pdf})
    # For now, suffix jid with UUID so we can submit the same job URL again
    uid = uuid.uuid4().hex
    res = sf.start_execution(stateMachineArn=STATEMACHINE_ARN,
                             name=f'{jid}-{uid}',  # use our JobID as unique SM invocation ID
                             input=sf_input)  # state needs JSON str input
    LOG.info(f'sf.start_execurtion res={res}')


def start_state_machine(event, context):
    """Take input from start of statemachine, enter an event in DDB, pass useful bits to next state."""
    LOG.info(f'event: {dumps(event)}')
    # TODO enter info into the DB: jid+dt, event=uploaded, bucket, key, ...
    return {'bucket': event['bucket'], 'key': event['key'], 'jid': event['jid']}


def split_pdf(event, context):
    """Use PyPDF to split the PDF on S3, write pages to S3 page_pdf/uid/jid/0000.pdf.

    Returns someting to the next state machine state, do_ocr_and_wait_for_completion.
    """
    LOG.info('event: {dumps(event)}')
    bucket = event['bucket']
    key = event['key']
    jid = event['jid']
    body_stream = boto3.resource('s3').Object(bucket, key).get()['Body']
    body = io.BytesIO(body_stream.read())
    pdf = PdfFileReader(body, strict=False)  # log unexpected stream ends, don't raise
    num_pages = pdf.getNumPages()
    LOG.info(f'num_pages={num_pages}')
    for page_num in range(num_pages):  # 0-based, want 1-based for humans?
        pdf_writer = PdfFileWriter()
        pdf_writer.addPage(pdf.getPage(page_num))
        pdf_key = f'page_pdf/{jid}/{page_num:04}.pdf'
        out = io.BytesIO()
        pdf_writer.write(out)
        out.seek(0)
        S3.upload_fileobj(out, bucket, pdf_key)
        LOG.info(f'uploaded page_num={page_num}')
    return {'jid': jid, 'num_pages': num_pages}


