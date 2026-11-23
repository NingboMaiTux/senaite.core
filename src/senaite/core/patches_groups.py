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

"""Runtime patch: let disabled user groups lose their permissions

中文注释：本模块让被禁用的用户组在权限求值时失效（从 PAS 组查询结果
中过滤禁用组），用户账号与其它组不受影响，重新启用即恢复。

注意：senaite.core 已有 `patches/` 包（按目标库组织、通过
`monkey:patch` 在 ZCML 中注册的补丁）。本补丁需要包装原实现并在运行
时按禁用状态过滤，无法写成纯替换函数，因此独立于该包，由包初始化时
（`senaite/core/__init__.py`）显式调用，且必须保持幂等。
"""

from senaite.core import logger


# 中文注释：延迟导入的 is_group_disabled 实现。senaite.core 包初始化时
# 不能提前触发 bika.lims.api 的导入链（会连带加载大量模块并影响启动
# 顺序），因此这里在补丁首次真正被调用时才导入。
_is_group_disabled_impl = None

# 中文注释：延迟导入的 discard_group_disabled 实现，原因同上。
_discard_group_disabled_impl = None

# 原 getGroupsForPrincipal 的引用，patch_disabled_groups 时绑定。
_ORIGINAL_GET_GROUPS_FOR_PRINCIPAL = None

# 原 removeGroup 的引用，patch_disabled_groups 时绑定。
_ORIGINAL_REMOVE_GROUP = None


def _get_is_group_disabled_impl():
    global _is_group_disabled_impl
    if _is_group_disabled_impl is None:
        from senaite.core.browser.usergroup.group_status import \
            is_group_disabled
        _is_group_disabled_impl = is_group_disabled
    return _is_group_disabled_impl


def _get_discard_group_disabled_impl():
    global _discard_group_disabled_impl
    if _discard_group_disabled_impl is None:
        from senaite.core.browser.usergroup.group_status import \
            discard_group_disabled
        _discard_group_disabled_impl = discard_group_disabled
    return _discard_group_disabled_impl


def _group_id_without_prefix(plugin, group_id):
    """返回去掉插件前缀后的组 id

    中文注释：PAS 的 ZODBGroupManager 插件可以为组 id 配置前缀，而
    禁用状态的存储使用的是 portal_groups 中的原始组 id，这里先剥离
    前缀再做判断。
    """
    prefix = getattr(plugin, "prefix", None) or ""
    if prefix and group_id.startswith(prefix):
        return group_id[len(prefix):]
    return group_id


def _is_disabled_group(plugin, group_id):
    """判断组是否被禁用（异常时安全回退为 False）
    """
    try:
        is_group_disabled = _get_is_group_disabled_impl()
        return is_group_disabled(_group_id_without_prefix(plugin, group_id))
    except Exception:
        return False


def _getGroupsForPrincipal(plugin, principal, request=None):
    """包装后的 getGroupsForPrincipal，过滤掉被禁用的组

    中文注释：禁用组从“用户所属组”中剔除后，该组授予的角色
    （GroupAwareRoleManager 通过本方法继承组角色）以及该组的 local
    roles（PropertiedUser.getRolesInContext 按 user_id + 组 id 匹配）
    都会失效。用户账号、显式角色及其它组均不受影响，重新启用即恢复。
    """
    groups = _ORIGINAL_GET_GROUPS_FOR_PRINCIPAL(plugin, principal, request)
    try:
        return tuple(
            group_id for group_id in groups
            if not _is_disabled_group(plugin, group_id))
    except Exception as exc:
        logger.warn(
            "Could not filter disabled groups for '%s': %s"
            % (principal, exc))
        return groups


def _removeGroup(plugin, group_id):
    """包装后的 removeGroup：删除组时清理其禁用标记

    中文注释：组删除后如果保留禁用标记，重建的同名组会被误判为禁用
    状态（例如“禁用 -> ZMI 删除 -> 重建同名组”）。这里在物理删除成功
    后同步清理禁用记录。
    """
    result = _ORIGINAL_REMOVE_GROUP(plugin, group_id)
    try:
        _get_discard_group_disabled_impl()(group_id)
    except Exception as exc:
        logger.warn(
            "Could not discard disabled flag for group '%s': %s"
            % (group_id, exc))
    return result


def patch_disabled_groups():
    """让被禁用的用户组在权限求值时失效

    中文注释：包装 acl_users.source_groups（ZODBGroupManager）的
    getGroupsForPrincipal。PAS 的两个消费点最终都会调用该插件方法：
    * PluggableAuthService._getGroupsForPrincipal -> _findUser 填充
      user._groups（影响 local roles 与 getGroups()）
    * Products.PlonePAS.utils.getGroupsForPrincipal ->
      GroupAwareRoleManager.getRolesForPrincipal（影响组角色继承）
    因此只在此一处过滤即可覆盖全部授权链路。

    同时包装 removeGroup，在物理删除组时清理禁用标记，避免重建同名组
    时继承旧状态。
    """
    global _ORIGINAL_GET_GROUPS_FOR_PRINCIPAL
    global _ORIGINAL_REMOVE_GROUP

    try:
        from Products.PluggableAuthService.plugins.ZODBGroupManager import \
            ZODBGroupManager
    except ImportError as exc:
        logger.warn("Could not patch disabled groups: {}".format(exc))
        return

    current = ZODBGroupManager.getGroupsForPrincipal
    if not getattr(current, "_senaite_disabled_groups_patch", False):
        logger.info(
            "Patching ZODBGroupManager.getGroupsForPrincipal to filter "
            "disabled groups")
        _ORIGINAL_GET_GROUPS_FOR_PRINCIPAL = current
        _getGroupsForPrincipal._senaite_disabled_groups_patch = True
        ZODBGroupManager.getGroupsForPrincipal = _getGroupsForPrincipal

    current_remove = ZODBGroupManager.removeGroup
    if not getattr(current_remove, "_senaite_disabled_groups_patch", False):
        logger.info(
            "Patching ZODBGroupManager.removeGroup to discard disabled "
            "flags on deletion")
        _ORIGINAL_REMOVE_GROUP = current_remove
        _removeGroup._senaite_disabled_groups_patch = True
        ZODBGroupManager.removeGroup = _removeGroup
