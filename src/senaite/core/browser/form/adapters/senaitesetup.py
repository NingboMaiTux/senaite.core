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


class EditForm(EditFormAdapterBase):
    """Edit form adapter for SenaiteSetup
    """

    def _as_bool(self, value):
        """将表单值统一转换为布尔值，兼容字符串布尔输入"""
        if isinstance(value, basestring):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _lock_management_field(self):
        """锁定「仅实验室经理可管理工作表」为只读

        中文注释：这里**只能**设为只读，绝不能再附带一个值更新。
        `set_field_readonly` 已经把复选框换成了一个隐藏域，并把控件自己的
        token（"selected"）写了进去；而 `update_form` 里 readonly 的处理排在
        updates 之前，随后的值更新会命中那个隐藏域，把 token 覆写成裸的
        "true"。z3c.form 的 SingleCheckBoxWidget 只认 "selected"，token 对不
        上时 `SequenceWidget.extract()` 返回 NO_VALUE，这个必填字段就报
        「缺少必需的输入」—— 而且因为 fieldset 底下是同一个表单，它会连带
        让设置页**所有**标签页都保存不了，不只是「安全」这一页。
        """
        self.add_readonly_field(_MANAGEMENT_FIELD, message=None)

    def _unlock_management_field(self, checked):
        """解除只读，并把复选框恢复到给定的勾选状态

        这条路径可以安全地附带值更新：`set_field_editable` 会先把真实的
        复选框换回来，随后的更新落在复选框本身上，走的是 `field.checked`
        赋值，不经过 token。
        """
        self.add_editable_field(_MANAGEMENT_FIELD, message=None)
        self.add_update_field(_MANAGEMENT_FIELD, checked)

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
            # Make restrict_worksheet_management readonly. The read-only
            # handling already submits the field as checked, see
            # `_lock_management_field`.
            self._lock_management_field()

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
                # Make restrict_worksheet_management readonly (and checked)
                self._lock_management_field()
            else:
                # Make restrict_worksheet_management editable and unchecked
                self._unlock_management_field(False)

        return self.data
