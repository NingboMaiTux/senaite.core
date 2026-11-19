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

from Products.CMFPlone.controlpanel.browser.quickinstaller import \
    ManageProductsView as BaseView
from zope.i18n import translate
from zope.i18nmessageid import MessageFactory


addon_message = MessageFactory("senaite.core.addons")


class ManageProductsView(BaseView):
    """
    """

    def addon_text(self, message):
        """Translate profile metadata, falling back to the add-on's own domain."""
        original = translate(message, domain="plone", context=self.request)
        # ZCML can preserve indentation inside multiline profile descriptions.
        msgid = u" ".join(message.split())
        return translate(msgid, domain="senaite.core.addons",
                         context=self.request, default=original)

    def upgrade_label(self, product_id):
        message = addon_message(u"Upgrade ${product}", mapping={"product": product_id})
        return translate(message, context=self.request)

    def get_available(self):
        """Available add-ons
        """
        available = []
        available_addons = self.get_addons(apply_filter="available").values()
        for addon in available_addons:
            id = addon.get("id")
            if id.startswith("plone."):
                continue
            elif id.startswith("Products."):
                continue
            elif id.startswith("collective."):
                continue
            elif id == "bika.lims":
                continue
            available.append(addon)
        return available
