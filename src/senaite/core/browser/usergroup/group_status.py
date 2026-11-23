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
from senaite.core import logger


# 中文注释：禁用组 ID 的持久化存储键。portal_groupdata 是 PlonePAS 的
# GroupDataTool（SimpleItem 子类，继承 Persistent），直接 setattr 到工具
# 上即可随事务持久化，避免依赖组属性表/属性 sheet 的实现差异。
DISABLED_GROUPS_ATTR = "_senaite_disabled_groups"


def _get_groupdata_tool():
    """获取 portal_groupdata 工具

    中文注释：组数据（GroupData）统一由 portal_groupdata 承载，禁用状态
    也存放在该工具上。注意 api.get_tool 在工具不存在时会抛 APIError，
    这里统一捕获并返回 None。
    """
    try:
        return api.get_tool("portal_groupdata")
    except Exception as exc:
        logger.warn(
            "Could not find 'portal_groupdata' tool: {}".format(exc))
        return None


def get_disabled_group_ids():
    """返回当前被禁用组的 id 集合
    """
    tool = _get_groupdata_tool()
    if tool is None:
        return set()
    return set(getattr(tool, DISABLED_GROUPS_ATTR, None) or ())


def is_group_disabled(group_id):
    """判断组是否被禁用
    """
    return group_id in get_disabled_group_ids()


def set_group_disabled(group_id, disabled):
    """设置组的禁用状态
    """
    if not group_id:
        return False

    tool = _get_groupdata_tool()
    if tool is None:
        logger.warn(
            "Could not find 'portal_groupdata' to disable group '%s'"
            % group_id)
        return False

    ids = get_disabled_group_ids()
    if disabled:
        ids.add(group_id)
    else:
        ids.discard(group_id)
    setattr(tool, DISABLED_GROUPS_ATTR, sorted(ids))
    return True


def discard_group_disabled(group_id):
    """从禁用列表中移除组 id（不校验组是否存在）

    中文注释：组被删除后必须清理其禁用标记，否则重建同名组会被误判为
    禁用状态。此函数幂等，组不在禁用列表时返回 False。
    """
    if not group_id:
        return False

    tool = _get_groupdata_tool()
    if tool is None:
        return False

    ids = get_disabled_group_ids()
    if group_id not in ids:
        return False
    ids.discard(group_id)
    setattr(tool, DISABLED_GROUPS_ATTR, sorted(ids))
    return True
