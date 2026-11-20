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

from Products.CMFPlone import PloneMessageFactory as _
from Products.CMFPlone.controlpanel.browser.usergroups_groupmembership import \
    GroupMembershipControlPanel as BaseView
from senaite.core.browser.usergroup.group_status import is_group_disabled


class GroupMembershipControlPanel(BaseView):
    """覆盖组成员管理页面：被禁用的组不允许添加成员
    """

    def _get_groupname(self):
        groupname = getattr(self.request, "groupname", None)
        if not groupname:
            groupname = self.request.form.get("groupname")
        return groupname

    def update(self):
        groupname = self._get_groupname()
        disabled = bool(groupname) and is_group_disabled(groupname)
        form = self.request.form
        if disabled and form.get("form.submitted", False):
            if form.get("add"):
                form["add"] = []
                self.context.plone_utils.addPortalMessage(
                    _("This group is disabled; users cannot be added to it."),
                    "warn")
        super(GroupMembershipControlPanel, self).update()
        if disabled:
            self.canAddUsers = False
