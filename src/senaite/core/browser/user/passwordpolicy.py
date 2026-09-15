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
from plone.registry.interfaces import IRegistry
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core import logger
from zope import schema
from zope.component import getUtility
from zope.interface import Interface


REGISTRY_PREFIX = "senaite.core.password_policy"


class IPasswordPolicySettings(Interface):
    """密码规则配置 schema。"""

    enabled = schema.Bool(
        title=u"Enable password policy",
        description=u"Turn the custom password policy on or off.",
        default=True,
        required=False,
    )

    min_length = schema.Int(
        title=u"Minimum password length",
        description=u"Minimum number of characters required for a password.",
        default=8,
        required=False,
        min=1,
    )

    require_uppercase = schema.Bool(
        title=u"Require uppercase letter",
        description=u"Password must contain at least one uppercase letter.",
        default=False,
        required=False,
    )

    require_lowercase = schema.Bool(
        title=u"Require lowercase letter",
        description=u"Password must contain at least one lowercase letter.",
        default=False,
        required=False,
    )

    require_digit = schema.Bool(
        title=u"Require digit",
        description=u"Password must contain at least one number.",
        default=False,
        required=False,
    )

    require_special = schema.Bool(
        title=u"Require special character",
        description=u"Password must contain at least one special character.",
        default=False,
        required=False,
    )


class PasswordPolicyControlPanelView(BrowserView):
    """管理员密码规则配置页面。"""

    index = ViewPageTemplateFile("templates/password-policy-controlpanel.pt")

    def __call__(self):
        self._ensure_registry_records()
        if self.request.get("saved"):
            self._show_message("Password policy settings saved.", "info")
        if self.request.get("form.cancel"):
            return self.request.response.redirect(api.get_url(self.context))
        if self.request.get("form.save"):
            return self.handle_save()
        return self.index()

    def _ensure_registry_records(self):
        """确保 registry 字段存在，避免旧站点首次打开时报错。"""
        registry = getUtility(IRegistry)
        try:
            registry.registerInterface(
                IPasswordPolicySettings,
                prefix=REGISTRY_PREFIX,
            )
        except Exception as exc:
            # 不吞掉：注册失败说明 registry 里已有同名但类型不同的记录，
            # 此时面板显示的是默认值，而校验走的是另一套 —— 比报错更难查。
            logger.warning(
                "Unable to register password policy settings: %s" % exc)

    def _show_message(self, message, level="info"):
        api.get_portal().plone_utils.addPortalMessage(message, level)

    def _record_key(self, name):
        return "{}.{}".format(REGISTRY_PREFIX, name)

    def _registry_value(self, name, default=None):
        registry = getUtility(IRegistry)
        record = registry.records.get(self._record_key(name))
        if record is None:
            return default
        return getattr(record, "value", default)

    def _set_registry_value(self, name, value):
        registry = getUtility(IRegistry)
        key = self._record_key(name)
        if key not in registry.records:
            self._ensure_registry_records()
        record = registry.records[key]
        record.value = value

    def enabled(self):
        return bool(self._registry_value("enabled", True))

    def min_length(self):
        return int(self._registry_value("min_length", 8) or 8)

    def require_uppercase(self):
        return bool(self._registry_value("require_uppercase", False))

    def require_lowercase(self):
        return bool(self._registry_value("require_lowercase", False))

    def require_digit(self):
        return bool(self._registry_value("require_digit", False))

    def require_special(self):
        return bool(self._registry_value("require_special", False))

    def handle_save(self):
        """保存密码规则配置。"""
        try:
            min_length = int(self.request.get("min_length", "8") or 8)
        except Exception:
            self._show_message("Minimum password length must be an integer.", "error")
            return self.index()

        if min_length < 1:
            self._show_message("Minimum password length must be greater than 0.", "error")
            return self.index()

        self._set_registry_value("enabled", bool(self.request.get("enabled")))
        self._set_registry_value("min_length", min_length)
        self._set_registry_value(
            "require_uppercase",
            bool(self.request.get("require_uppercase")),
        )
        self._set_registry_value(
            "require_lowercase",
            bool(self.request.get("require_lowercase")),
        )
        self._set_registry_value(
            "require_digit",
            bool(self.request.get("require_digit")),
        )
        self._set_registry_value(
            "require_special",
            bool(self.request.get("require_special")),
        )

        return self.request.response.redirect(
            "{}/@@password-policy-controlpanel?saved=1".format(
                api.get_url(self.context)
            )
        )
