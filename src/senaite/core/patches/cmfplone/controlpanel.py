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

from Products.CMFPlone.utils import safe_unicode
from zope.i18nmessageid import Message


def _initConfiglets(self, node):
    """Register the control panel entries described by the node.

    Copy of `Products.CMFPlone.exportimport.controlpanel`'s method with one
    change: the configlet title is passed to `Message` as text.

    The original reads

        title = Message(str(child.getAttribute('title')), domain=domain)

    `getAttribute` hands back unicode and `Message` subclasses it, so that
    `str()` is an implicit `encode("ascii")` that raises UnicodeEncodeError on
    the first translated title. Every control panel entry named in Chinese --
    or in any other non-Latin language -- therefore aborts the `controlpanel`
    import step, and with it the whole run.

    The remaining `str()` calls are left alone on purpose: action ids,
    expressions, categories and permission names are identifiers, not prose.
    """
    controlpanel = self.context
    default_domain = "plone"
    if node.nodeName == 'object':
        domain = str(node.getAttribute('i18n:domain'))
        if domain:
            default_domain = domain
    for child in node.childNodes:
        if child.nodeName != 'configlet':
            continue

        domain = str(child.getAttribute('i18n:domain'))
        if not domain:
            domain = default_domain

        action_id = str(child.getAttribute('action_id'))
        # Remove previous action with same id and category.
        controlpanel.unregisterConfiglet(action_id)
        remove = str(child.getAttribute('remove'))
        if remove.lower() == 'true':
            continue

        title = Message(safe_unicode(child.getAttribute('title')),
                        domain=domain)
        url_expr = str(child.getAttribute('url_expr'))
        condition_expr = str(child.getAttribute('condition_expr'))
        icon_expr = str(child.getAttribute('icon_expr'))
        category = str(child.getAttribute('category'))
        visible = str(child.getAttribute('visible'))
        appId = str(child.getAttribute('appId'))
        if visible.lower() == 'true':
            visible = 1
        else:
            visible = 0

        permission = ''
        for permNode in child.childNodes:
            if permNode.nodeName == 'permission':
                for textNode in permNode.childNodes:
                    if textNode.nodeName != '#text' or \
                            not textNode.nodeValue.strip():
                        continue
                    permission = str(textNode.nodeValue)
                    break  # only one permission is allowed
                if permission:
                    break

        controlpanel.registerConfiglet(id=action_id,
                                       name=title,
                                       action=url_expr,
                                       appId=appId,
                                       condition=condition_expr,
                                       category=category,
                                       permission=permission,
                                       visible=visible,
                                       icon_expr=icon_expr)
