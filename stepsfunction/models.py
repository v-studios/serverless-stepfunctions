"""Use PynamoDB lib to define DynamoDB's tables."""

import os
from datetime import datetime

from pynamodb.attributes import (
    ListAttribute,
    MapAttribute,
    NumberAttribute,
    UTCDateTimeAttribute,
    UnicodeAttribute
)

from pynamodb.models import Model

import logging


class MVPDateTime(UTCDateTimeAttribute):
    """Handle when UTCDateTimeAttribute's value is empty.

    Override deseialize function to ignore the error:
        'strptime() argument 1 must be str, not None'
    when the value of a UTCDateTimeAttribute was empty.
    """

    def deserialize(self, value):
        """Override UTCDateTimeAttribute.deserialize ."""
        if not value:
            return None
        return super(MVPDateTime, self).deserialize(value)


class SinglePage(MapAttribute):
    """Page."""

    page_id = UnicodeAttribute()
    file_path = UnicodeAttribute()


class PDFUpload(Model):
    """Mapping to DynamoDB - PDFUpload table."""

    class Meta:
        """Describe PDFUpload's meta data."""

        if 'ENV' in os.environ:
            table_name = 'PDFUpload'
            host = 'http://localhost:8000'
        else:  # pragma: no cover
            table_name = os.environ['PDFUPLOAD_TABLE']
            region = os.environ['REGION']
            host = 'https://dynamodb.' + region + '.amazonaws.com'

    uuid = UnicodeAttribute(hash_key=True)
    status = UnicodeAttribute(null=True)
    desired_filename = UnicodeAttribute(null=False)
    num_pages = NumberAttribute(null=True)
    pages = ListAttribute(of=SinglePage)
    filename = UnicodeAttribute(null=True)
    createdAt = UTCDateTimeAttribute(null=False, default=datetime.now())
    updatedAt = MVPDateTime(null=True)

    def __iter__(self):
        """Iterator method."""
        for name, attr in self._get_attributes().items():
            yield name, attr.serialize(getattr(self, name))

    def save_with_log(self):
        """Function save with logging."""
        try:
            result = self.save()
        except Exception as exc:
            logging.error("Saving PDFUpload|PDFUpload: {}|Error: {}".format(self, exc))
            raise
        else:
            return result

    def update_with_log(self, actions=None):
        """Function update with logging."""
        try:
            result = self.update(actions=actions)
        except Exception as exc:
            logging.error("Updating PDFUpload|PDFUpload: {}|Updates: {}|Error: {}".format(
                self, actions, exc))
            raise
        else:
            return result

    @classmethod
    def get_with_log(cls, hash_key, range_key=None):
        """Function get with logging."""
        try:
            result = PDFUpload.get(hash_key=hash_key, range_key=range_key)
        except PDFUpload.DoesNotExist:
            raise
        except Exception as exc:
            logging.error("Getting PDFUpload|hash_key: {}|range_key:{}|Error: {}".format(
                hash_key, range_key, exc))
            raise
        else:
            return result
