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

import re

from plone.registry.interfaces import IRegistry
from senaite.core import logger
from zope.component import getUtility

from senaite.core.browser.user.passwordpolicy import IPasswordPolicySettings
from senaite.core.browser.user.passwordpolicy import REGISTRY_PREFIX


class PasswordPolicyService(object):
    """统一读取并校验自定义密码规则。"""

    def __init__(self):
        self.registry = getUtility(IRegistry)
        self._ensure_registry_records()

    def _ensure_registry_records(self):
        try:
            self.registry.registerInterface(
                IPasswordPolicySettings,
                prefix=REGISTRY_PREFIX,
            )
        except Exception as exc:
            # 不吞掉：注册失败说明 registry 里已有同名但类型不同的记录，
            # 此时读到的是默认值，实际生效的是另一套 —— 比报错更难查。
            logger.warning(
                "Unable to register password policy settings: %s" % exc)

    def settings(self):
        return self.registry.forInterface(
            IPasswordPolicySettings,
            prefix=REGISTRY_PREFIX,
            check=False,
        )

    def is_enabled(self):
        return bool(getattr(self.settings(), "enabled", True))

    def min_length(self):
        return int(getattr(self.settings(), "min_length", 8) or 8)

    def rules_summary(self):
        """返回用于页面展示的密码规则说明。"""
        if not self.is_enabled():
            return "Custom password policy is disabled."

        rules = ["be at least {} characters long".format(self.min_length())]
        settings = self.settings()
        if getattr(settings, "require_uppercase", False):
            rules.append("include at least one uppercase letter")
        if getattr(settings, "require_lowercase", False):
            rules.append("include at least one lowercase letter")
        if getattr(settings, "require_digit", False):
            rules.append("include at least one digit")
        if getattr(settings, "require_special", False):
            rules.append("include at least one special character")
        return "Password must " + ", ".join(rules) + "."

    def validate(self, password):
        """根据管理员配置校验密码，返回错误字符串列表。"""
        if not self.is_enabled():
            return []

        password = password or ""
        errors = []
        settings = self.settings()

        if len(password) < self.min_length():
            errors.append(
                "Password must be at least {} characters long.".format(
                    self.min_length()
                )
            )
        if getattr(settings, "require_uppercase", False):
            if not re.search(r"[A-Z]", password):
                errors.append("Password must contain at least one uppercase letter.")
        if getattr(settings, "require_lowercase", False):
            if not re.search(r"[a-z]", password):
                errors.append("Password must contain at least one lowercase letter.")
        if getattr(settings, "require_digit", False):
            if not re.search(r"[0-9]", password):
                errors.append("Password must contain at least one digit.")
        if getattr(settings, "require_special", False):
            if not re.search(r"[^A-Za-z0-9]", password):
                errors.append("Password must contain at least one special character.")

        return errors
