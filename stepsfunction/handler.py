"""Simple example."""
from json import dumps, loads
import os
import io
import sys
import boto3
import random
import botocore
from botocore.exceptions import ClientError
import logging
import subprocess
from time import sleep, time
import os
from models import PDFUpload, SinglePage
from uuid import uuid4
from datetime import datetime
from PyPDF2 import PdfFileReader, PdfFileWriter

UPLOAD_BUCKET_NAME = os.environ.get('UPLOAD_BUCKET_NAME', "")
STATEMACHINE_ARN = os.environ.get('STATEMACHINE_ARN', "")
ACTIVITY_OCR_DONE_ARN = os.environ.get('ACTIVITY_OCR_DONE_ARN', "")
STARTMARK = b"\xff\xd8"
STARTFIX = 0
ENDMARK = b"\xff\xd9"
ENDFIX = 2


# setting for tesseract
TESSERACT_BIN = './tesseract/bin/tesseract'
TESSERACT_DATA = './tesseract/share/tessdata'
TESSERACT_LIB = './tesseract/lib'
os.environ['LD_LIBRARY_PATH'] = ':'.join([os.environ['LD_LIBRARY_PATH'], TESSERACT_LIB])

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)
S3C = boto3.client('s3')  # Unneeded: config=boto3.session.Config(signature_version='s3v4'))
S3R = None
# Call Amazon Textract
TX = boto3.client(
    service_name='textract',
    region_name='us-east-1',
    endpoint_url='https://textract.us-east-1.amazonaws.com',
)
SF = boto3.client('stepfunctions')


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
    url = S3C.generate_presigned_url(ClientMethod='put_object',
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
        S3C.upload_fileobj(out, bucket, pdf_key)
        LOG.info(f'uploaded page_num={page_num}')
    pdf_upload = PDFUpload.get(hash_key=jid)
    # update PDFUpload
    pdf_upload.update_with_log(
        actions=[
            PDFUpload.status.set("split"),
            PDFUpload.num_pages.set(num_pages),
            PDFUpload.updatedAt.set(datetime.now())
        ])
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

    sf_input = dumps({'bucket': bucket, 'key': key, 'etag': etag,
                      'size': size, 'jid': jid, 'name_pdf': name_pdf})
    # For now, suffix jid with UUID so we can submit the same job URL again
    uid = uuid4().hex
    file_info = save_info(name_pdf, jid)
    res = SF.start_execution(stateMachineArn=STATEMACHINE_ARN,
                             name=f'{jid}',  # use our JobID as unique SM invocation ID
                             input=sf_input)  # state needs JSON str input
    LOG.info(f'SF.start_execurtion res={res}')


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
        status="uploaded",
        pages=[],
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
    LOG.info(f'boto3 version: {boto3.__version__} botocore version: {botocore.__version__}')

    s3rec = event['Records'][0]['s3']  # only the first, but there should only be one for S3
    bucket = s3rec['bucket']['name']
    key = s3rec['object']['key']
    _doc_pdf, jid, name_pdf = key.split('/')
    LOG.info(f'bucket={bucket} key={key} jid={jid} name_pdf={name_pdf}')

    # random to choose AWS Textract or Tesseract for OCR
    random_choice = random.randrange(0, 2)
    type = 'tesseract'
    if random_choice == 1:
        type = 'aws'
        detected_text = get_textract_data(bucket, key)
    else:
        detected_text = ocr_by_tesseract(bucket, key)
        _cleanup()

    s3_ocred_file_path = write_textract_to_s3(detected_text, bucket, key, type=type)
    pdf_upload = PDFUpload.get(hash_key=jid)
    update_db_after_ocr(pdf_upload, s3_ocred_file_path, name_pdf, jid)

    # Pretend we've discovered we've finished all the pages
    if check_ocr_done(pdf_upload, jid):
        # update db
        pdf_upload.update_with_log(
            actions=[
                PDFUpload.status.set("ocred"),
                PDFUpload.updatedAt.set(datetime.now())
            ])
        send_task_ocr_activity(jid)


def get_textract_data(bucket, key):
    """Using AWS textract."""
    LOG.info(f'Loading get_textract_data bucket:{bucket}, key:{key}')
    # convert to jpg
    jpg_file = extract_jpg_from_pdf(bucket, key)
    response = TX.detect_document_text(
        Document={
            'Bytes': jpg_file
        })
    detected_text = ''

    # Print detected text
    for item in response['Blocks']:
        if item['BlockType'] == 'LINE':
            detected_text += item['Text'] + '\n'
    return detected_text


def write_textract_to_s3(textract_data, bucket, key, type=''):
    """Save detected text to S3."""
    LOG.info(f'Loading write_textract_to_s3 bucket:{bucket}, key:{key}')
    generate_path = os.path.splitext(key)[0] + '_' + type + '.txt'
    S3C.put_object(Body=textract_data, Bucket=bucket, Key=generate_path)
    LOG.info(f'generateFilePath: {generate_path}')
    return generate_path


def update_db_after_ocr(pdf_upload, file_path, name, jid):
    """Update PDFUpload after finishing orc."""
    page = SinglePage(
        page_id=name[:4],
        file_path=file_path
    )
    pages = pdf_upload.pages
    if pages:
        pages.append(page)
    else:
        pages = [page]
    LOG.info(f'loading update_db_after_ocr pages:{pages}')
    pdf_upload.update_with_log(
        actions=[
            PDFUpload.pages.set(pages),
            PDFUpload.updatedAt.set(datetime.now())
        ])


def check_ocr_done(pdf_upload, jid):
    """Get db & check done."""
    LOG.info(f'loading check_ocr_done')
    num_pages = pdf_upload.num_pages
    pages = pdf_upload.pages
    pages_len = 0 if not pages else len(pages)
    LOG.info(f'check_ocr_done: num_pages:{num_pages}, pages_len={pages_len}')
    if num_pages == pages_len:
        return True
    else:
        return False


def send_task_ocr_activity(worker_name):
    """After ocr's done, send task success to WaitOcr activity."""
    try:
        response = SF.get_activity_task(
            activityArn=ACTIVITY_OCR_DONE_ARN,
            workerName=worker_name
        )
        LOG.info(f'activityArn={ACTIVITY_OCR_DONE_ARN}, sf_activity={response}')
        sf_input = dumps(response['input'])
        res = SF.send_task_success(
            taskToken=response["taskToken"],
            output=sf_input
        )
        LOG.info(f'SF.send_task_success={res}')
    except Exception as e:
        LOG.error(e)
        # Go to FailTask here
        SF.send_task_failure(taskToken=response["taskToken"],
                             error='CannotRecover',
                             cause=f'We coud not recover')


def extract_jpg_from_pdf(bucket, key):
    """Extract JPG from single-page PDF scan, return as bytes.

    No coversion involved so faster than GhostScript or ImageMagick,
    and also no loss due to conversion.
    This mutation of Batchelder's work only handles a single page.
    Only works with scanned PDF images, not text PDFs.
    May not always be reliable
    Past peformance is no guarantee of future results.
    Use only under a doctor's supervision.
    """
    LOG.info(f'Loadding extract_jpg_from_pdf: bucket:{bucket}, key={key}')
    # download from S3
    download(bucket, key, '/tmp/page.pdf')
    pdf = open('/tmp/page.pdf', "rb").read()
    LOG.info('extract_jpg_from_pdf after open file')
    i = 0
    while True:
        istream = pdf.find(b"stream", i)
        if istream < 0:
            break
        istart = pdf.find(STARTMARK, istream, istream + 20)
        if istart < 0:
            i = istream + 20
            continue
        iend = pdf.find(b"endstream", istart)
        if iend < 0:
            raise Exception("Did not find end of stream!")
        iend = pdf.find(ENDMARK, iend - 20)
        if iend < 0:
            raise Exception("Did not find end of JPG!")
        istart += STARTFIX
        iend += ENDFIX
        jpg = pdf[istart:iend]
        return jpg
    raise Exception(f"Could not extract JPG from bucket={bucket}, key={key}")


def download(bucket_name, key, path):
    """Safely download an object from S3.

    param str bucket_name: the name of the S3 bucket
    param str key: the desired object's S3 key
    param str path: path on the local disk to save the object to
    return: None
    """
    S3R = get_s3_resource()
    bucket = S3R.Bucket(bucket_name)
    s3_url = 's3://{}/{}'.format(bucket_name, key)
    LOG.info('downloading {} to {}'.format(s3_url, path))
    try:
        bucket.download_file(key, path)
    except (ClientError, Exception) as e:
        LOG.error('download({}, {}, $path) e.response={}'.format(
            bucket_name, key, e.response))
        raise e


def get_s3_resource():
    """If the global s3 is set, return it; else set it then return.

    This avoids initializing the s3 connection in every function call so is a
    performance boost. It's perhaps not as good as doing it in each lambda
    outside the handler, but good enough, and requires no lambda function changes.
    """
    global S3R
    if S3R is None:
        LOG.info('get_s3_resource initializing new connection')
        S3R = boto3.resource('s3')
    return S3R


def ocr_by_tesseract(bucket, key):
    """Convert PDF to JPG single page, then OCR with tesseract.

    :params: bucket name and key of single PDF file on S3
    :returns: extracted text as a str
    """
    LOG.info('ocr_by_tesseract converting page PDF to JPG: bucket {}, key {}'.format(bucket, key))
    jpg = extract_jpg_from_pdf(bucket, key)
    jpgfile = open("/tmp/jpgextracted.jpg", "wb")
    jpgfile.write(jpg)
    jpgfile.close()
    txt = run(f'{TESSERACT_BIN} --tessdata-dir {TESSERACT_DATA} /tmp/jpgextracted.jpg stdout')
    return txt.decode('utf-8')


def run(cmd):
    """Run a command as a subprocess, return output, log output or errors."""
    LOG.debug('RUN {}')
    if isinstance(cmd, str):
        cmd = cmd.split()
    t_0 = time()
    res = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t_run = time() - t_0
    if res.returncode == 0:
        LOG.info('run run_seconds=%s cmd="%s"', t_run, cmd)
        return res.stdout
    else:
        msg = 'run: {}'.format(res)
        LOG.error(msg)
        raise RuntimeError(msg)


def _cleanup():
    """Remove files on tmp after orc by tesseract done
    :returns: nothing
    """
    LOG.info('Removing tmp page pdf, tif files and S3 page')
    os.remove('/tmp/page.pdf')
    os.remove('/tmp/jpgextracted.jpg')
