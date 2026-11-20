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

import logging
import zope.i18nmessageid

logger = logging.getLogger("senaite.core")

# Message factory for generic texts (e.g. "Title" for schema fields, etc.)
PloneMessageFactory = zope.i18nmessageid.MessageFactory('plone')
# 中文注释：禁用账号拦截改为登录表单入口处理，避免在包初始化时
# 全局 monkey patch PAS 认证链，防止把原生“错误密码失败”行为带坏。


def initialize(context):
    """Initializer called when used as a Zope 2 product."""
    logger.info("*** Initializing SENAITE.CORE ***")


# 中文注释：让被禁用的用户组在权限求值时失效（过滤 PAS 组查询结果）。
# 该补丁只影响授权计算，不拦截认证链，用户账号与其它组不受影响。
# 模块名刻意避开 patches/ 包（senaite.core 已存在按库组织的补丁包）。
try:
    from senaite.core.patches_groups import patch_disabled_groups  # noqa: E402

    patch_disabled_groups()
except Exception as exc:
    logger.warn(
        "Could not enable disabled-group permission filtering: %s" % exc)
