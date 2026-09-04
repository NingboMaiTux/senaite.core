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

from bika.lims import api

PORTAL_CATALOG = "portal_catalog"


def index_in_portal_catalog(obj):
    portal_type = api.get_portal_type(obj)
    if not portal_type:
        # `manage_renameObject` detaches the object from its container for the
        # duration of the rename, so acquisition cannot resolve `portal_type`
        # and it reads as None. The indexing queue is flushed inside that
        # window by anything that issues a catalog search -- plone.app.
        # discussion looks for 'Discussion Item' on every ObjectMovedEvent --
        # and the object then arrives here with no type at all.
        #
        # Nothing useful can be indexed in that state: `get_catalogs_for`
        # raises an APIError on the missing type, and letting it through
        # instead only moves the failure downstream, where building the
        # catalog metadata needs the schema that the type would have named.
        # Skip it. `manage_renameObject` re-adds the object to its container
        # afterwards, which queues a fresh index request with the type back
        # in place.
        return False
    portal_catalog = api.get_tool(PORTAL_CATALOG)
    catalogs = api.get_catalogs_for(portal_type)
    if portal_catalog not in catalogs:
        return False
    return True


def index(self, obj, attributes=None):
    if not index_in_portal_catalog(obj):
        return
    catalog = api.get_tool(PORTAL_CATALOG)
    if catalog is not None:
        catalog._indexObject(obj)


def reindex(self, obj, attributes=None, update_metadata=1):
    if not index_in_portal_catalog(obj):
        return
    catalog = api.get_tool(PORTAL_CATALOG)
    if catalog is not None:
        catalog._reindexObject(
            obj,
            idxs=attributes,
            update_metadata=update_metadata)


def unindex(self, obj):
    if not index_in_portal_catalog(obj):
        return
    catalog = api.get_tool(PORTAL_CATALOG)
    if catalog is not None:
        catalog._unindexObject(obj)
