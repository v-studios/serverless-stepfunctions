"""Copy from Socrates."""
import logging
import os
import socket
import subprocess
from time import sleep, time
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

# Make s3 a global so we can initialize it only once for performance.
s3 = None


def done_check(bucket_name, donekey):
    """Check existence of done key to determine if we have duplicate event.
    If we've already processed this key successfully, we likely have gotten a
    duplicate event and need to ignore it, else we'll likely get a 404 because
    the object will have been cleaned up.
    Since we expect that S3 eventual consistency may return false 404 when the
    object has actually been created this is not 100% reliable, but is the best
    we can do without a real database.
    param str bucket_name: name of the S3 bucket
    param str donekey: S3 path for marker, generated by done_key()
    return: False if not found, datetime object if found
    """
    s3 = get_s3_resource()
    try:
        dt = s3.Object(bucket_name, donekey).last_modified
    except ClientError as e:
        if e.response['Error']['Code'] == '404':  # yes, a string, sigh...
            return False
        logging.error(f'done_check e={e}')
        raise e
    return dt


def done_key(key, etag):
    """Return done-marker key based on S3 object key and object/event etag.
    We use the etag to detect different versions of the same-named file, to
    distinguish between duplicated notifications, retries, and different file
    upload.
    Putting it in /done/* prevents it from getting removed by the cleanup code
    but allows it to age out due to 24hour lifecycle event.
    param str key: the path in S3 where the object lives
    param str etag: the etag provided in the S3 event or on the S3 object itself
    return: str like done/filename.pdf/605f239f44a05305bfdfee8436e6c468
    """
    return os.path.join('done', key, etag)


def done_mark(bucket_name, donekey):
    """Create empty file to mark the key and contents as successfully processed.
    param str bucket_name: name of the S3 bucket
    param str donekey: S3 path for marker, generated by done_key()
    return: None
    """
    try:
        upload_blob('', bucket_name, donekey)
    except Exception as e:
        logging.error('done_mark could not create bucket_name={} done_key_={} e='.format(
            bucket_name, donekey, e))
        raise e


def download(bucket_name, key, path):
    """Safely download an object from S3.
    param str bucket_name: the name of the S3 bucket
    param str key: the desired object's S3 key
    param str path: path on the local disk to save the object to
    return: None
    """
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    s3_url = 's3://{}/{}'.format(bucket_name, key)
    logging.info('downloading {} to {}'.format(s3_url, path))
    try:
        bucket.download_file(key, path)
    except (ClientError, Exception) as e:
        logging.error('download({}, {}, $path) e.response={}'.format(
            bucket_name, key, e.response))
        raise e


def get_logger(level=logging.INFO, botolevel=logging.WARNING, elasticsearchlevel=logging.INFO):
    logging.basicConfig(level=level)
    log = logging.getLogger()
    log.setLevel(level)
    for b in ('boto', 'boto3', 'botocore'):
        logging.getLogger(b).setLevel(botolevel)
    for e in ('elasticsearch', 'elasticsearch.trace'):
        logging.getLogger(e).setLevel(elasticsearchlevel)
    return log


def get_metadata(bucket_name, key):
    """Get the user-defined metadata on an object by bucket_name and key.
    param str bucket_name: name of the S3 bucket, e.g., socrates-dev
    param str key: path to the object, e.g., doc_pdf/foo.pdf
    return: dict of user-named key:value pairs (no AWS prefixes)
    """
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    obj = bucket.Object(key)
    s3_url = 's3://{}/{}'.format(bucket_name, key)
    logging.info('get_metadata %s' % s3_url)
    try:
        return obj.metadata
    except (ClientError, Exception) as err:
        logging.error('get_metadata({}, {}) e.response={}'.format(
            bucket_name, key, err.response))
        raise err


def get_s3_keys(bucket_name, prefix=None):
    """Return list of all keys at bucket with optional prefix.
    This avoids the 1000 key limit of bucket.objects.filter().
    param str bucket_name: name of the bucket
    param str prefix: optional "folder" prefix, saftest to end with "/"
    return: list of all key names (at prefix) in bucket
    """
    # I tried to use a generator to save RAM but a generator is exhausted after
    # reading once and we need to read it multiple times and access keys later.
    logging.info('get_s3_keys bucket_name={} prefix={}'.format(bucket_name, prefix))
    print('### lib.py: get_s3_keys bucket_name={} prefix={}'.format(bucket_name, prefix))
    s3 = get_s3_resource()
    paginator = s3.meta.client.get_paginator('list_objects_v2')
    params = {'Bucket': bucket_name}
    if prefix:
        params['Prefix'] = prefix
    page_iterator = paginator.paginate(**params)
    # It's a bit tricky testing for timeouts and recovering as we may get keys
    # for the first page then timeout on a subseqnet page in the loop.
    # This while loop and try/except will restart the iterator if any page (of 1000)
    # fails, which is a bit wasteful of resources but I don't know a better way.
    keys = []
    got_keys = False
    while got_keys is False:
        try:
            for page in page_iterator:
                page_keys = [obj['Key'] for obj in page.get('Contents', [])]
                keys.extend(page_keys)
            got_keys = True
        except socket.timeout as e:
            logging.warning('Timeout getting keys bucket={} prefix={}: {}'.format(
                bucket_name, prefix, e))
            print('### lib.py: Timeout getting keys bucket={} prefix={}: {}'.format(
                bucket_name, prefix, e))

            sleep(1)
    return keys


def get_s3_resource():
    """If the global s3 is set, return it; else set it then return.
    This avoids initializing the s3 connection in every function call so is a
    performance boost. It's perhaps not as good as doing it in each lambda
    outside the handler, but good enough, and requires no lambda function changes.
    """
    global s3
    if s3 is None:
        logging.info('get_s3_resource initializing new connection')
        s3 = boto3.resource('s3')
    return s3


def log_dns_resolution_time(lookups=3):
    """Log time to resolve S3 DNS name, multiple times to test cache.
    We suspect some slow DNS resolution, 200ms according to boto where it looks
    up S3 before uploading. Try once to test DNS, then another or two to test
    DNS cache.
    If there's a way to report the resolver host, that would be really helpful,
    but I can't find how yet.
    param lookups int: number of times to try, 1 will not test cache
    """
    t0 = time()
    for lookup in range(lookups):
        t1 = time()
        socket.gethostbyname('s3-us-gov-west-1.amazonaws.com')
        logging.info('lookup={} dns_resolution_seconds={}'.format(lookup, time() - t1))
    logging.info('lookups={} total_dns_resolution_seconds={}'.format(lookups, time() - t0))


def log_time_left(context):
    """Log the remaining time left in the lambda.
    param object context: context passed to the lambda.
    """
    logging.info('lambda_remaining_seconds={}'.format(
        context.get_remaining_time_in_millis() / 1000.0))


def read_obj_body(bucket_name, key):
    """Safely read an S3 object's body.
    param str bucket_name: the name of the S3 bucket
    param str key: the desired object's S3 key
    return: str object body
    """
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    s3_url = 's3://{}/{}'.format(bucket_name, key)
    logging.info('read_obj_body reading {}'.format(s3_url))
    try:
        return bucket.Object(key).get()['Body'].read()
    except (ClientError, Exception) as e:
        logging.error('read_obj_body({}, {}) e.response={}'.format(
            bucket_name, key, e.response))
        raise e


def remove_s3_tree(bucket_name, folder):
    """Get list of objects starting at folder and remove them.
    We don't want sensitive data lying around or costing us money.
    param str bucket_name: the name of the S3 bucket
    param str folder: prefix of tree to remove, safest to end with '/'
    return: None
    """
    # AWS can delete up to 1000 items at a time, so limit page size to that
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    pager = bucket.meta.client.get_paginator('list_objects_v2')
    iter = pager.paginate(Bucket=bucket.name, Prefix=folder,
                          PaginationConfig={'PageSize': 1000})
    logging.info('remove_s3_tree s3://{}/{}'.format(bucket_name, folder))
    for page in iter:
        if page['KeyCount'] == 0:
            logging.warning('remove_s3_tree no keys found for folder={}'.format(folder))
            print('### lib.py: remove_s3_tree no keys found for folder={}'.format(folder))
            return
        keys = [{'Key': obj['Key']} for obj in page['Contents']]
        res = bucket.delete_objects(Delete={'Objects': keys})
        if res['ResponseMetadata']['HTTPStatusCode'] != 200:
            raise RuntimeError('remove_s3_tree s3://{}/{} HTTP error: {}'.format(
                bucket_name, folder, res))
        if 'Errors' in res:
            raise RuntimeError('remove_s3_tree s3://{}/{} error: {}'.format(
                bucket_name, folder, res['Errors']))


def remove_s3_item(bucket_name, key):
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    logging.info('remove_s3_item s3://{}/{}'.format(bucket_name, key))
    res = bucket.delete_objects(Delete={'Objects': [{'Key': key}]})
    if 'Errors' in res:
        raise RuntimeError('remove_s3_item s3://{}/{} error: {}'.format(
            bucket_name, key, res['Errors']))
    # res['Deleted'] has the key name, even if it didn't exist, can't check
    if res['ResponseMetadata']['HTTPStatusCode'] != 200:
        raise RuntimeError('remove_s3_item s3://{}/{} HTTP error: {}'.format(
            bucket_name, key, res))


def run(cmd):
    """Run a command as a subprocess, return output, log output or errors."""
    logging.debug('RUN {}')
    if isinstance(cmd, str):
        cmd = cmd.split()
    t_0 = time()
    res = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t_run = time() - t_0
    if res.returncode == 0:
        logging.info('run run_seconds=%s cmd="%s"', t_run, cmd)
        return res.stdout
    else:
        msg = 'run: {}'.format(res)
        logging.error(msg)
        raise RuntimeError(msg)


def upload_blob(blob, bucket_name, key, metadata=None):
    """Safely upload a blob of text to S3 as an object, with optional metadata.
    param bytes blob: blob to upload to S3
    param str bucket_name: the name of the S3 bucket
    param str key: the object's desired S3 key
    param dict metadata: optional metadata to store on object
    return: None
    """
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    logging.info('Uploading {} bytes to s3://{}/{}'.format(len(blob), bucket.name, key))
    try:
        if metadata is None:
            bucket.Object(key).put(Body=blob, ServerSideEncryption='AES256')
        else:
            bucket.Object(key).put(Body=blob, ServerSideEncryption='AES256', Metadata=metadata)
    except Exception as e:
        raise RuntimeError('Upload to s3://{}/{} failed: {}'.format(bucket.name, key, e))


def upload_file(path, bucket_name, key, metadata=None):
    """Safely upload a file to S3, ensuring metadata valuess are str.
    param str path: path on the local disk to upload to S3
    param str bucket_name: the name of the S3 bucket
    param str key: the object's desired S3 key
    param dict metadata: optional metadata to store on object
    return: None
    """
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    try:
        file_size = os.stat(path).st_size
    except OSError as e:
        raise RuntimeError('Upload of {} to s3://{}/{} failed: {}'.format(
            path, bucket.name, key, e))
    logging.info('Uploading {} ({} bytes) to s3://{}/{}'.format(
        path, file_size, bucket.name, key))
    extraargs = {'ServerSideEncryption': 'AES256'}
    if metadata:
        extraargs['Metadata'] = {k: str(v) for k, v in metadata.items()}
    try:
        t_0 = time()
        bucket.upload_file(path, key, ExtraArgs=extraargs)
        t_1 = time() - t_0
        logging.info('upload_file seconds=%s bytes=%s kbyte_per_second=%s key=%s',
                     t_1, file_size, int((file_size / t_1) / 1024), key)
    except Exception as e:
        raise RuntimeError('Upload of {} to s3://{}/{} failed: {}'.format(
            path, bucket.name, key, e))