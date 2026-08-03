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

from senaite.core.browser.form.adapters import EditFormAdapterBase

_FIELD_PREFIX = "form.widgets."
_MANAGEMENT_FIELD = _FIELD_PREFIX + "restrict_worksheet_management"
_MANAGEMENT_CHECKBOX_SELECTOR = (
    "input[type='checkbox'][name^='{}']".format(_MANAGEMENT_FIELD)
)


class EditForm(EditFormAdapterBase):
    """Edit form adapter for SenaiteSetup
    """

    def _as_bool(self, value):
        """将表单值统一转换为布尔值，兼容字符串布尔输入"""
        if isinstance(value, basestring):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _set_management_checked_state(self, checked):
        """同步更新管理权限复选框的值与勾选外观"""
        self.add_update_field(_MANAGEMENT_FIELD, checked)
        # 中文注释：部分前端逻辑只更新字段值，不会同步刷新 checkbox
        # 的勾选外观，因此这里显式补充 checked 属性。
        self.add_attribute(
            _MANAGEMENT_CHECKBOX_SELECTOR,
            "checked",
            "checked" if checked else False
        )

    def initialized(self, data):
        """Handle form initialization
        Show/hide rejection_reasons based on enable_rejection_workflow
        Make restrict_worksheet_management readonly if
        restrict_worksheet_users_access is enabled
        """
        # Check if rejection workflow is enabled
        enabled = self.context.getEnableRejectionWorkflow()

        if not enabled:
            # Hide rejection_reasons field if workflow is not enabled
            self.add_hide_field(_FIELD_PREFIX + "rejection_reasons")

        # Check if worksheet access is restricted to assigned analysts
        restrict_users = self.context.getRestrictWorksheetUsersAccess()

        if self._as_bool(restrict_users):
            # 中文注释：页面初始化时先把下方字段显式更新为 True，
            # 再设为只读，避免旧数据为空时前端禁用后提交丢值。
            self._set_management_checked_state(True)
            # Make restrict_worksheet_management readonly and force it to True
            self.add_readonly_field(
                _MANAGEMENT_FIELD,
                message=None
            )

        return self.data

    def modified(self, data):
        """Handle field modifications
        Show/hide rejection_reasons when enable_rejection_workflow changes
        Enable/readonly restrict_worksheet_management when
        restrict_worksheet_users_access changes
        """
        name = data.get("name")
        value = data.get("value")

        if name == _FIELD_PREFIX + "enable_rejection_workflow":
            # Show or hide rejection_reasons based on checkbox value
            if value:
                self.add_show_field(_FIELD_PREFIX + "rejection_reasons")
            else:
                self.add_hide_field(_FIELD_PREFIX + "rejection_reasons")

        elif name == _FIELD_PREFIX + "restrict_worksheet_users_access":
            # Handle restrict_worksheet_management based on
            # restrict_worksheet_users_access
            if self._as_bool(value):
                self._set_management_checked_state(True)
                # Make restrict_worksheet_management readonly
                self.add_readonly_field(
                    _MANAGEMENT_FIELD,
                    message=None
                )
            else:
                self._set_management_checked_state(False)
                # Make restrict_worksheet_management editable
                self.add_editable_field(
                    _MANAGEMENT_FIELD,
                    message=None
                )

        return self.data
