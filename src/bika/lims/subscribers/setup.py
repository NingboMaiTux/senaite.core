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
from senaite.core.permissions import AddWorksheet
from senaite.core.permissions import EditWorksheet
from senaite.core.permissions import ManageWorksheets


def ObjectModifiedEventHandler(instance, event):
    """Actions to be taken when Setup object is modified
    """
    update_worksheet_manage_permissions(instance)


def update_worksheet_manage_permissions(senaite_setup):
    """Updates the permissions 'Manage Worksheets' and 'Edit Worksheet' based
    on the setting 'RestrictWorksheetManagement' from Setup
    """
    if senaite_setup.getRestrictWorksheetUsersAccess() and not senaite_setup.getRestrictWorksheetManagement():
        try:
            # 双保险中的第二层：如果前端或其他写入入口没有把联动值正确落库，
            # 在权限重算前再次兜底修正，避免 Analyst/LabClerk 被错误放权。
            senaite_setup.setRestrictWorksheetManagement(True)
        except Exception:
            # 这里保持静默，后续仍按当前存储值继续走权限更新流程。
            pass

    roles = ["LabManager", "Manager"]
    if not senaite_setup.getRestrictWorksheetManagement():
        # LabManagers, Analysts and LabClerks can create and manage worksheets
        roles.extend(["Analyst", "LabClerk"])

    portal = api.get_portal()
    worksheets = getattr(portal, "worksheets", None)
    if worksheets is None:
        # 中文注释：安装/建站早期当前站点可能还是 RequestContainer，
        # 此时 worksheets 容器尚未创建，跳过本次权限重算，等待后续正常事件再处理。
        return

    worksheets.manage_permission(AddWorksheet, roles, acquire=1)
    worksheets.manage_permission(ManageWorksheets, roles, acquire=1)
    worksheets.manage_permission(EditWorksheet, roles, acquire=1)
    worksheets.reindexObject()
