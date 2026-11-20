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

from Acquisition import aq_inner
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.controlpanel.browser.usergroups_groupsoverview import \
    GroupsOverviewControlPanel as BaseView
from senaite.core.browser.usergroup.group_status import is_group_disabled
from senaite.core.browser.usergroup.group_status import set_group_disabled
from senaite.core.config.roles import HIDDEN_ROLES


class GroupsOverviewControlPanel(BaseView):
    """Custom userprefs controlpanel
    """

    @property
    def portal_roles(self):
        """Return only SENAITE Roles
        """
        pmemb = getToolByName(aq_inner(self.context), "portal_membership")
        roles = pmemb.getPortalRoles()
        return filter(lambda r: r not in HIDDEN_ROLES, roles)

    def is_group_disabled(self, group_id):
        """返回组当前是否处于禁用状态
        """
        return is_group_disabled(group_id)

    def manageGroup(self, groups=None, delete=None):
        """接管保存逻辑，忽略物理删除，仅维护禁用状态
        """
        # 中文注释：与用户管理页的实现思路一致——表单中 groups.id:records
        # 与 groups.disabled:records 会被 Zope 合并成同一条 record，因此
        # 直接遍历 request.form["groups"]，读取记录的 id / disabled 属性
        # 即可，无需再解析带后缀的原始键。
        for group in (self.request.form.get("groups") or []):
            group_id = getattr(group, "id", None)
            if not group_id:
                continue
            set_group_disabled(
                group_id, bool(getattr(group, "disabled", None)))

        # 即使有人手工伪造 delete:list 提交，也不再执行物理删除。
        return super(GroupsOverviewControlPanel, self).manageGroup(groups, [])
