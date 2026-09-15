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

from plone.app.users.browser.register import AddUserForm as BaseAddUserForm
from plone.app.users.utils import notifyWidgetActionExecutionError
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.browser.user.passwordpolicy_service import PasswordPolicyService


class AddUserForm(BaseAddUserForm):
    template = ViewPageTemplateFile("templates/newuser_form.pt")

    def updateFields(self):
        super(AddUserForm, self).updateFields()

        # remove groups field from registration
        if "groups" in self.fields:
            del self.fields["groups"]

    def updateWidgets(self):
        super(AddUserForm, self).updateWidgets()
        summary = PasswordPolicyService().rules_summary()
        for fieldname in ("password", "password_ctl"):
            if fieldname in self.widgets:
                # 这里只改 widget 展示文案，避免直接修改 schema 字段定义触发类型校验。
                self.widgets[fieldname].description = summary

    def updateActions(self):
        super(AddUserForm, self).updateActions()
        self.actions["register"].klass = "btn btn-sm btn-success"

    def validate_registration(self, action, data):
        """在新建用户时追加自定义密码规则校验。"""
        super_method = getattr(super(AddUserForm, self),
                               "validate_registration", None)
        if callable(super_method):
            super_method(action, data)

        password = data.get("password")
        if not password:
            return

        errors = PasswordPolicyService().validate(password)
        for err_str in errors:
            notifyWidgetActionExecutionError(action,
                                             "password", err_str)
            notifyWidgetActionExecutionError(action,
                                             "password_ctl", err_str)
