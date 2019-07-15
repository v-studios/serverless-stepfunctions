"""Split scanned PDF doc into pages and store each page to S3 page_pdf/docname.pdf/0000.pdf."""

# TODO: Enable alarm in resource-alarmcriticallogged.yml

import io
from json import dumps
import os
from time import time
from traceback import format_exc

import boto3
from PyPDF2 import PdfFileReader, PdfFileWriter
from urllib.parse import unquote_plus

from lib import (done_check, done_key, done_mark, get_logger, get_metadata,
                 remove_s3_item, run, upload_file)

LOG = get_logger()
S3 = boto3.client('s3')


def handler_s3created(event, _context):
    """Handle the S3 ObjectCreated then mark it done and remove the orig."""
    LOG.info('Incoming Event: %s', dumps(event))
    LOG.info('Memory_limit_in_mb=%s', _context.memory_limit_in_mb)
    LOG.info('vmfree_start=%s', _vm_free())
    try:
        record = event['Records'][0]
        bucket_name = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        etag = record['s3']['object']['eTag']
        donekey = done_key(key, etag)
        donetime = done_check(bucket_name, donekey)
        LOG.info("Inputs bucket_name {} key {} etag {} donekey {} donetime {}".format(
            bucket_name, key, etag, donekey, donetime))
        if donetime:
            LOG.warning('key=%s already done at datetime=%s', key, donetime)
            return
        _download_split_upload(bucket_name, key)
        done_mark(bucket_name, donekey)
        # remove_s3_item(bucket_name, key)
    except Exception as err:
        LOG.critical('doc_pdf_split: key=%s err=%s : %s', key, err, format_exc())
        # Do not raise the error, exit cleanly so Lambda does not retry 2x


def _download_split_upload(bucket_name, key):
    """Download the PDF doc, split into pages, upload each to S3.

    We use PyPDF2 to split, as it's 12x faster than ghostscript, which allows us to
    avoid hairy recursive splitting techniques we were using.

    Uploaded pages go to page_pdf/docname.pdf/0000.pdf and we store the total
    number of pages in each page's S3 metadata.

    return: None
    """
    # TODO: handle empty pdf
    # TODO: if file larger than the 512MB /tmp log an error

    docname_pdf = key.split('/')[1]  # doc_pdf/docname.pdf
    metadata = get_metadata(bucket_name, key)
    LOG.info("_download_split_upload Inputs bucket_name {} key {}".format(bucket_name, key))
    LOG.info('get_metadata: bucket=%s key=%s metadata=%s', bucket_name, key, metadata)

    # Read into RAM instead of downloading: 3GB RAM limit > 512MB disk limit
    t_0 = time()
    body_stream = boto3.resource('s3').Object(bucket_name, key).get()['Body']
    body = io.BytesIO(body_stream.read())
    LOG.info('download_seconds=%s', time() - t_0)
    LOG.info('vmfree_download=%s', _vm_free())
    LOG.info('body:'.format(body))
    t_0 = time()
    pdf = PdfFileReader(body, strict=False)  # log unexpected stream ends, don't raise
    LOG.info('read_seconds=%s', time() - t_0)
    LOG.info('vmfree_read=%s', _vm_free())

    num_pages = pdf.getNumPages()
    LOG.info('num_pages=%s', num_pages)
    metadata['socrates_total_pages'] = num_pages
    extraargs = {'ServerSideEncryption': 'AES256', 'ContentType': 'application/pdf'}
    extraargs['Metadata'] = {k: str(v) for k, v in metadata.items()}

    t_0 = time()
    for page_num in range(num_pages):
        pdf_writer = PdfFileWriter()
        pdf_writer.addPage(pdf.getPage(page_num))
        pdf_key = 'page_pdf/{}/{:0>4}.pdf'.format(docname_pdf, page_num + 1)  # zero-based
        out = io.BytesIO()
        pdf_writer.write(out)
        out.seek(0)
        t_1 = time()
        S3.upload_fileobj(out, bucket_name, pdf_key, ExtraArgs=extraargs)
        LOG.info('key=%s upload_seconds=%s', pdf_key, time() - t_1)
    LOG.info('split_upload_seconds=%s num_pages=%s', time() - t_0, num_pages)


def _vm_free():
    """Return amount of free memory KB from vmstat as an int."""
    # On lambda, output of "vmstat -a" looks like:
    #   procs -----------memory---------- ---swap-- -----io---- --system-- -----cpu-----
    #    r  b   swpd   free  inact active   si   so    bi    bo   in   cs us sy id wa st
    #    0  0      0 3404432 127548 211984    0    0   149    32   47   64  1  0 98  0  0\t
    try:
        vmstat = run('vmstat -a')
    except Exception:
        return 0
    free = vmstat.decode('utf-8').split('\n')[2].split()[3]
    return int(free)
