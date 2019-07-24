"""Simple example."""
from json import dumps, loads
import io

import boto3
import logging
import os
from models import PDFUpload
from uuid import uuid4
from datetime import datetime
from PyPDF2 import PdfFileReader, PdfFileWriter
import boto3
UPLOAD_BUCKET_NAME = "doc-pdfs"
STATEMACHINE_ARN = os.environ.get('STATEMACHINE_ARN', "")


logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3 = boto3.client('s3')  # Unneeded: config=boto3.session.Config(signature_version='s3v4'))


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
    LOG.debug('Got Task? event=%s', dumps(event))
    LOG.debug('Got Task? context=%s', dumps(dir(_context)))
    try:
        filename = event['queryStringParameters']['filename']  # TODO: URLdecode defense
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
    jid = uuid4().hex
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


def split_doc_pdf(event, context):
    """splitPDF."""
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
    sf_input = dumps({'bucket': bucket, 'key': key, 'etag': etag,
                      'size': size, 'jid': jid, 'name_pdf': name_pdf})
    # For now, suffix jid with UUID so we can submit the same job URL again
    uid = uuid4().hex
    file_info = save_info(name_pdf, jid)
    res = sf.start_execution(stateMachineArn=STATEMACHINE_ARN,
                             name=f'{jid}-{uid}',  # use our JobID as unique SM invocation ID
                             input=sf_input)  # state needs JSON str input
    LOG.info(f'sf.start_execurtion res={res}')


def start_state_machine(event, context):
    """Take input from start of statemachine, enter an event in DDB, pass useful bits to next state."""
    LOG.info(f'event: {dumps(event)}')
    # TODO enter info into the DB: jid+dt, event=uploaded, bucket, key, ...
    return {'bucket': event['bucket'], 'key': event['key'], 'jid': event['jid']}


def save_info(desired_filename, jid):
    """Save information when user get presigned url."""
    file_upload = PDFUpload(
        desired_filename=desired_filename,
        uuid=jid,
        state=0,
        filename='',
        createdAt=datetime.now()
    )
    file_upload.save_with_log()
    return file_upload


def ocr_page(event, context):
    """Get PDF page from S3, convert to image and tesseract txt to page_txt/jid/0000.txt.

    After saving each page, we need to check whether all the pages are done
    by inserting the page into DynamoDB atomically and getting the list of done pages back
    and seeing if all are there. When done, send a notification to the WaitForOcr state
    to release it.
    Start development TESTING here, don't bother converting or OCRing, or even using DDB yet:
    just signal when we see page 0000.pdf to get the workflow going.
    TODO: Instead of Activity, can we include somehow get a Task Token and send it to a state that's .waitForTaskToken?
    See Callback Pattern at https://console.aws.amazon.com/states/home?region=us-east-1#/sampleProjects
    """
    LOG.info(f'event: {dumps(event)}')
    activity_arn = os.environ.get('ACTIVITY_ARN', "")
    s3rec = event['Records'][0]['s3']  # only the first, but there should only be one for S3
    bucket = s3rec['bucket']['name']
    key = s3rec['object']['key']
    _doc_pdf, jid, name_pdf = key.split('/')
    LOG.info(f'bucket={bucket} key={key} jid={jid} name_pdf={name_pdf}')

    worker_name = "notify_upload_worker"
    sf = boto3.client('stepfunctions')
    # Pretend we've discovered we've finished all the pages
    if name_pdf == '0000.pdf':
        res = sf.get_activity_task(activityArn=activity_arn, workerName=worker_name)
        LOG.info(f'sf_activity={res}')
        sf_input = dumps(res['input'])
        res = sf.send_task_success(taskToken=res['taskToken'], output=sf_input)
        LOG.info(f'sf.send_task_success={res}')
