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
from Products.CMFPlone.controlpanel.browser.usergroups_usermembership import \
    UserMembershipControlPanel as BaseView
from senaite.core.browser.usergroup.group_status import is_group_disabled


def _get_group_id(group):
    """获取组对象的 id（兼容 GroupData 的不同接口）
    """
    if group is None:
        return None
    getter = getattr(group, "getGroupId", None)
    if getter is None:
        getter = getattr(group, "getId", None)
    if getter is None:
        return None
    return getter()


class UserMembershipControlPanel(BaseView):
    """覆盖用户组成员页面：被禁用的组不再出现在可分配候选中
    """

    def getPotentialGroups(self, searchString):
        """从可分配组候选中剔除被禁用的组
        """
        groups = super(UserMembershipControlPanel, self).getPotentialGroups(
            searchString)
        result = []
        for group in groups:
            group_id = _get_group_id(group)
            if group_id and is_group_disabled(group_id):
                continue
            result.append(group)
        return result

    def update(self):
        """忽略向禁用组添加成员的提交
        """
        form = self.request.form
        if form.get("form.submitted", False) and form.get("add"):
            disabled = [g for g in form["add"] if is_group_disabled(g)]
            if disabled:
                form["add"] = [g for g in form["add"] if g not in disabled]
                self.context.plone_utils.addPortalMessage(
                    _("Disabled groups cannot be assigned."), "warn")
        super(UserMembershipControlPanel, self).update()
