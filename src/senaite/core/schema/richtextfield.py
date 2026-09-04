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

import six
from bika.lims import api
from plone.app.textfield import RichText
from senaite.core.schema.fields import BaseField
from senaite.core.schema.interfaces import IRichTextField
from zope.interface import implementer


@implementer(IRichTextField)
class RichTextField(RichText, BaseField):
    """A field that handles markup texts
    """

    def set(self, object, value):
        """Set field value

        :param object: the instance of the field
        :param value: value to set
        """
        # always ensure unicode
        if isinstance(value, str):
            value = api.safe_unicode(value)
        if value and isinstance(value, six.text_type):
            # The schema promises an `IRichTextValue`, and readers reach for
            # `.raw` or `.output` accordingly. Plain text still arrives here
            # from paths that never build one: the legacy AT proxy mutators on
            # `bika_setup`, GenericSetup imports, setup data importers. Storing
            # it unchanged leaves the object holding text where an object is
            # expected, and the next reader breaks -- exporting the site
            # structure, for one, dies on
            #     AttributeError: 'unicode' object has no attribute 'raw'
            value = self.fromUnicode(value)
        super(RichTextField, self).set(object, value)

    def get(self, object):
        """Get the field value

        :param object: the instance of the field
        :returns: RichTextValue
        """
        value = super(RichTextField, self).get(object)
        return value

    def _validate(self, value):
        """Validator when called from form submission
        """
        super(RichTextField, self)._validate(value)
