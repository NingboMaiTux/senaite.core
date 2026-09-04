# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.CORE.
#
# SENAITE.CORE is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright 2018-2025 by it's authors.
# Some rights reserved, see README and LICENSE.

from types import ListType
from types import TupleType

import six
from Products.Archetypes.interfaces.base import IBaseUnit
from Products.Archetypes.Marshall import formatRFC822Headers
from Products.Archetypes.utils import mapply
from zope.contenttype import guess_content_type


def to_str(value):
    """`str()` that survives non-ASCII text

    The original marshaller calls `str()` on every field value. Under Python 2
    that means an implicit `encode("ascii")` for unicode, which raises
    UnicodeEncodeError on the first non-ASCII character. Text is encoded as
    UTF-8 instead; everything else keeps the original `str()` behaviour.
    """
    if isinstance(value, six.text_type):
        return value.encode("utf-8")
    return str(value)


def marshall(self, instance, **kwargs):
    """Serialize the instance as an RFC822 document.

    Copy of `Products.Archetypes.Marshall.RFC822Marshaller.marshall` with
    every `str()` on a field value routed through `to_str`, and the same
    treatment for the primary field body.

    The original blows up on any field holding non-ASCII text:

        headers.append((field.getName(), str(value)))
        UnicodeEncodeError: 'ascii' codec can't encode characters ...

    `manage_FTPget` calls this for every Archetypes object the GenericSetup
    `content` export step walks over, so a single translated setup value --
    a Chinese e-mail body template, say -- aborts the whole step, and with it
    every full export run from portal_setup.

    Note this path is Archetypes-only: Dexterity content is serialized by
    `plone.dexterity.exportimport` and never reaches this marshaller. Byte
    strings are the native storage of AT fields, so re-importing the UTF-8
    written here round-trips into the same representation the objects already
    hold. RFC822 headers carry no charset declaration, though, so the
    resulting file is only interpretable as UTF-8 by convention.
    """
    p = instance.getPrimaryField()
    body = p and instance[p.getName()] or ''
    pname = p and p.getName() or None
    content_type = length = None
    # Gather/Guess content type
    if IBaseUnit.providedBy(body):
        content_type = str(body.getContentType())
        body = body.getRaw()
    else:
        if p and hasattr(p, 'getContentType'):
            content_type = p.getContentType(instance) or 'text/plain'
        else:
            content_type = body and guess_content_type(body) or 'text/plain'

    headers = []
    fields = [f for f in instance.Schema().fields()
              if f.getName() != pname]
    for field in fields:
        if field.type in ('file', 'image', 'object'):
            continue
        accessor = field.getEditAccessor(instance)
        if not accessor:
            continue
        kw = {'raw': 1, 'field': field.__name__}
        value = mapply(accessor, **kw)
        if type(value) in [ListType, TupleType]:
            value = '\n'.join([to_str(v) for v in value])
        headers.append((field.getName(), to_str(value)))

    headers.append(('Content-Type', content_type or 'text/plain'))

    header = formatRFC822Headers(headers)
    data = '%s\n\n%s' % (header, to_str(body))
    length = len(data)

    return (content_type, length, data)
