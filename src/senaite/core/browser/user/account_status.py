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

from plone import api as ploneapi
from senaite.core import logger
from Products.PluggableAuthService.interfaces.plugins import \
    IPropertiesPlugin


ACCOUNT_DISABLED_PROPERTY = "account_disabled"


def _get_user(user_or_username):
    """统一获取可写用户对象
    """
    if hasattr(user_or_username, "getId"):
        return user_or_username

    user = ploneapi.user.get(userid=user_or_username)
    if user is not None:
        return user
    return ploneapi.user.get(username=user_or_username)


def _set_user_property(user, key, value):
    """将用户属性写入可变属性存储
    """
    portal_memberdata = user._tool
    if not portal_memberdata.hasProperty(key):
        portal_memberdata.manage_addProperty(key, "", "string")
        logger.info("Registered user property {}".format(key))

    saved = False
    acl_users = portal_memberdata.acl_users
    for _plugin_id, plugin in acl_users.plugins.listPlugins(IPropertiesPlugin):
        sheet = plugin.getPropertiesForUser(user)
        if sheet is None:
            continue
        has = getattr(sheet, "hasProperty", None)
        setter = getattr(sheet, "setProperty", None)
        if not callable(has) or not callable(setter):
            continue
        if not has(key):
            continue
        setter(user, key, value)
        saved = True
        break

    member_setter = getattr(user, "setMemberProperties", None)
    if callable(member_setter):
        try:
            # 中文注释：部分现场环境里 plugin 路径可真实落库，但当前请求
            # 的 memberdata 视图缓存不会立刻同步；这里补一次标准接口调用，
            # 兼容回显与不同用户源实现。
            member_setter({key: value})
            saved = True
        except Exception as exc:
            logger.warn(
                "setMemberProperties failed for '{}': {}".format(key, exc))

    properties_setter = getattr(user, "setProperties", None)
    if callable(properties_setter):
        try:
            # 中文注释：再补一层 kwargs/properties 双兼容写法，尽量覆盖
            # 不同 MemberData/User 对象的实现差异。
            try:
                properties_setter(**{key: value})
            except TypeError:
                properties_setter(properties={key: value})
            saved = True
        except Exception as exc:
            logger.warn(
                "setProperties failed for '{}': {}".format(key, exc))

    if not saved:
        logger.warn("No writable path accepted '{}'".format(key))
    return saved


def is_account_disabled(user_or_username):
    """判断账号是否被禁用
    """
    user = _get_user(user_or_username)
    if user is None:
        return False
    value = user.getProperty(ACCOUNT_DISABLED_PROPERTY, "")
    return bool(value)


def set_account_disabled(user_or_username, disabled):
    """设置账号禁用状态
    """
    user = _get_user(user_or_username)
    if user is None:
        return False

    # 使用字符串存储，兼容现有 memberdata 属性表。
    value = "1" if disabled else ""
    return _set_user_property(user, ACCOUNT_DISABLED_PROPERTY, value)
