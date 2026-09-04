# -*- coding: utf-8 -*-

import six

from Products.CMFPlone.utils import safe_unicode
from senaite.core.schema.fields import BaseField
from zope import schema


class TextLineField(schema.TextLine, BaseField):
    """A text field with no newlines and without leading and trailing spaces.
    """

    def set(self, object, value):
        """Set the field's value to the given object.
        The value is converted to a Unicode string to preserve compatibility
        with the legacy behavior of auto-generated setters in AT content types.
        Leading and trailing whitespaces are removed before assignment.
        """
        value = safe_unicode(value)
        if isinstance(value, six.string_types):
            value = value.strip()
        super(TextLineField, self).set(object, value)

    def get(self, object):
        """Sets the value of this field from the given object.
        The returned value is encoded as UTF-8 to maintain compatibility with
        the legacy behavior of auto-generated getters in AT content types.

        Only text is encoded, never `six.string_types`: under Python 2 that
        alias also matches `str`, so an already-UTF-8 byte string would be
        encoded a second time, which makes Python decode it as ASCII first and
        raise UnicodeDecodeError on the first non-ASCII byte. `set()` funnels
        everything through `safe_unicode`, but values written past it -- direct
        attribute assignment, legacy AT setters, setup data importers -- do
        reach this getter as byte strings. They are already UTF-8, so they are
        returned untouched.

        The encoding itself is Python 2 only: on Python 3 there is no
        byte-string accessor contract left to emulate.
        """
        value = super(TextLineField, self).get(object)
        if six.PY2 and isinstance(value, six.text_type):
            value = value.encode("utf-8")
        return value
