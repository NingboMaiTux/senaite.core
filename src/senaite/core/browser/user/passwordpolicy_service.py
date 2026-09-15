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

from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from plone.registry.interfaces import IRegistry
from senaite.core import logger
from zope.component import getUtility
from zope.i18n import translate as zope_translate

from senaite.core.browser.user.passwordpolicy import IPasswordPolicySettings
from senaite.core.browser.user.passwordpolicy import REGISTRY_PREFIX


def translate_message(message):
    """Translates a message for the language of the current request

    Uses `zope.i18n.translate` directly instead of the `senaite.core.i18n`
    helper on purpose: that helper does `api.safe_unicode(msgid)` first, which
    flattens the Message into a plain string and thereby drops its domain,
    default and -- the one that actually bites -- its mapping. A msgstr like
    "be at least ${count} characters long" would then be rendered with a
    literal `${count}` in it.

    Falls back to the message default when no request is around (unit tests,
    command line scripts), which is what the catalogs would do anyway.
    """
    return zope_translate(message, context=api.get_request())


class PasswordPolicyService(object):
    """统一读取并校验自定义密码规则。

    All the strings this service returns are already translated for the
    current request: the callers (change password panel, registration form)
    put them straight into widget descriptions and widget errors, with no
    template in between to translate them.
    """

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
        """返回用于页面展示的密码规则说明（已翻译）

        逐条规则各自翻译再拼接：中文与英文的语序、标点都不同，
        把整句当一个 msgid 就没法翻译了。
        """
        if not self.is_enabled():
            return translate_message(_(
                u"description_password_policy_disabled",
                default=u"Custom password policy is disabled."))

        rules = [translate_message(_(
            u"description_password_policy_rule_min_length",
            default=u"be at least ${count} characters long",
            mapping={u"count": self.min_length()}))]

        settings = self.settings()
        for field, msgid, default in (
            ("require_uppercase", u"description_password_policy_rule_uppercase",
             u"include at least one uppercase letter"),
            ("require_lowercase", u"description_password_policy_rule_lowercase",
             u"include at least one lowercase letter"),
            ("require_digit", u"description_password_policy_rule_digit",
             u"include at least one digit"),
            ("require_special", u"description_password_policy_rule_special",
             u"include at least one special character"),
        ):
            if getattr(settings, field, False):
                rules.append(translate_message(_(msgid, default=default)))

        separator = translate_message(_(
            u"description_password_policy_rule_separator", default=u", "))

        return translate_message(_(
            u"description_password_policy_summary",
            default=u"Password must ${rules}.",
            mapping={u"rules": separator.join(rules)}))

    def validate(self, password):
        """根据管理员配置校验密码，返回已翻译的错误字符串列表"""
        if not self.is_enabled():
            return []

        password = password or ""
        errors = []
        settings = self.settings()

        if len(password) < self.min_length():
            errors.append(translate_message(_(
                u"error_password_policy_min_length",
                default=u"Password must be at least ${count} characters long.",
                mapping={u"count": self.min_length()})))
        if getattr(settings, "require_uppercase", False):
            if not re.search(r"[A-Z]", password):
                errors.append(translate_message(_(
                    u"error_password_policy_uppercase",
                    default=u"Password must contain at least one uppercase "
                            u"letter.")))
        if getattr(settings, "require_lowercase", False):
            if not re.search(r"[a-z]", password):
                errors.append(translate_message(_(
                    u"error_password_policy_lowercase",
                    default=u"Password must contain at least one lowercase "
                            u"letter.")))
        if getattr(settings, "require_digit", False):
            if not re.search(r"[0-9]", password):
                errors.append(translate_message(_(
                    u"error_password_policy_digit",
                    default=u"Password must contain at least one digit.")))
        if getattr(settings, "require_special", False):
            if not re.search(r"[^A-Za-z0-9]", password):
                errors.append(translate_message(_(
                    u"error_password_policy_special",
                    default=u"Password must contain at least one special "
                            u"character.")))

        return errors
