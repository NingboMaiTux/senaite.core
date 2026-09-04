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

import zExceptions
from Products.GenericSetup.content import DAVAwareFileAdapter
from zope.publisher.interfaces.http import MethodNotAllowed


def export(self, export_context, subdir, root=False):
    """Serialize the folder through WebDAV, signalling refusals in the
    vocabulary the caller actually catches.

    `StructureFolderWalkingAdapter.export` asks this adapter to dump the
    folder via `manage_FTPget` and falls back to writing a plain
    `.properties` file when the object refuses:

        try:
            FolderishDAVAwareFileAdapter(self.context).export(...)
        except (AttributeError, MethodNotAllowed):
            export_context.writeDataFile('.properties', ...)

    Every Archetypes folder refuses: `BaseFolder.__dav_marshall__` is False,
    so `WebDAVSupport.collection_check` raises. But it raises
    `zExceptions.MethodNotAllowed`, while `Products.CMFCore.exportimport.content`
    imports `MethodNotAllowed` from `zope.publisher.interfaces.http`. The two
    are unrelated classes -- neither is a subclass of the other -- so the
    `except` clause written for exactly this case never fires and the
    exception escapes all the way to the publisher. That aborts the whole
    `content` export step, and with it every full export run from
    portal_setup.

    Translating here rather than widening the `except` upstream keeps the
    patch to a single class: `FolderishDAVAwareFileAdapter` is only ever used
    by that fallback, whereas its base `DAVAwareFileAdapter` serializes
    non-folderish content elsewhere and must keep raising the HTTP exception.

    `zope.publisher`'s `MethodNotAllowed` takes (object, request); there is no
    request in this code path, so it is constructed with None.
    """
    try:
        return DAVAwareFileAdapter.export(self, export_context, subdir, root)
    except zExceptions.MethodNotAllowed:
        raise MethodNotAllowed(self.context, None)
