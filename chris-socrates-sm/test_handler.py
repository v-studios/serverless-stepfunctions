import json
import pytest

from handler import get_upload_url, uploaded


CONTEXT = None                # it's really an object

def test_get_upload_ok():
    event = {'headers': {'content-type': 'application/pdf'}, 'queryStringParameters': {'filename': 'filename.pdf'}}
    res = get_upload_url(event, CONTEXT)
    assert res['statusCode'] == 200
    assert 'url' in res['body']

def test_get_upload_missing_filename():
    event = {'headers': {'content-type': 'application/pdf'}, 'queryStringParameters': {'MISSING': 'filename.pdf'}}
    res = get_upload_url(event, CONTEXT)
    assert res == {'body': 'Must supply query string "filename=..."', 'statusCode': 400}


def test_get_upload_bad_contenttype():
    event = {'headers': {'content-type': 'BOGUS'}, 'queryStringParameters': {'filename': 'filename.pdf'}}
    res = get_upload_url(event, CONTEXT)
    assert res == {'body': 'Must specify Content-Type: application/pdf', 'statusCode': 400}


def test_uploaded_ok():
    event = json.loads("""
{
    "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "us-east-1",
      "eventTime": "2019-07-18T19:25:00.584Z",
      "eventName": "ObjectCreated:Put",
      "userIdentity": {
        "principalId": "AWS:AROAUN73CWDX7G4QITKX4:chris-socrates-sm-dev-GetUploadUrl"
      },
      "requestParameters": {
        "sourceIPAddress": "71.246.227.100"
      },
      "responseElements": {
        "x-amz-request-id": "26177C2E4AA1A703",
        "x-amz-id-2": "yLAlaRgJaco7Hhf+u1fiNKOWYrJiYXi725CnKx0Kl93gf4T0ZWUwHgCRZTqIjf6Ul0ypARE70zA="
      },
      "s3": {
        "s3SchemaVersion": "1.0",
        "configurationId": "1e0a4c30-bc44-48ea-add4-0d259d1bb071",
        "bucket": {
          "name": "chris-socrates-sm-dev-chris",
          "ownerIdentity": {
            "principalId": "A3CHJVRWCQTXYM"
          },
          "arn": "arn:aws:s3:::chris-socrates-sm-dev-chris"
        },
        "object": {
          "key": "doc_pdf/f4ad351bd2244ee1b2ba3fd96abb2dd8/doc.pdf",
          "size": 15,
          "eTag": "ae83ad4555f58d15329ce849019f5f79",
          "sequencer": "005D30C78C8885EB41"
        }
      }
    }
  ]
}
""")
    res = uploaded(event, CONTEXT)
    assert res == {'bucket': 'chris-socrates-sm-dev-chris',
                   'key': 'doc_pdf/f4ad351bd2244ee1b2ba3fd96abb2dd8/doc.pdf',
                   'etag': 'ae83ad4555f58d15329ce849019f5f79',
                   'size': 15,
                   'jid': 'f4ad351bd2244ee1b2ba3fd96abb2dd8',
                   'name_pdf': 'doc.pdf'}
