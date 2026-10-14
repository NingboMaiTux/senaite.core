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

"""仪表盘插件区块的**纯逻辑**：id 校验、契约规范化、注册者筛选。

本模块**不 import Zope / Plone**（同 ``maitux.stability.dashboard`` 的做法），
所以能直接用 py2.7 / py3 跑离线自检：

    python -m unittest senaite.core.tests.test_dashboard_sections

core 侧真正碰 Zope 的胶水在 ``dashboard.py``。这里只放"给定输入 ->
确定输出"的判定：一条断言就能守住一个契约，不必起 Zope。
"""

import re

#: 区块 id 的合法形式。
#:
#: id 会出现在三个地方：DOM id（``dashboard-section-<id>``）、
#: 数据接口的 ``?section=<id>``、以及日志。三处都要求它**可预测**，
#: 所以限死小写字母开头 + ``[a-z0-9_]``，长度 2~32。
SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

#: 面板契约版本。provider 报一个比 core 更新的版本时，core **拒绝**它
#: （而不是猜着渲染）——这样"core 落后于 add-on"是显式失败，不是画错图。
API_VERSION = 1

#: 区块默认权限，与 core 自带的统计区一致。
DEFAULT_PERMISSION = "senaite.core: View Dashboard"

#: ``dashboard.js`` 认得的面板类型。
PANEL_TYPES = ("simple-panel", "bar-chart-panel")

try:
    STRING_TYPES = (str, unicode)  # noqa: F821  (py2)
except NameError:                  # py3
    STRING_TYPES = (str,)


def to_text(value):
    """任意值 -> unicode（None / 空 -> u""），失败返回 u""

    刻意不抛：provider 的字段脏了只应导致"这一块降级"，不该 500。
    """
    if value is None:
        return u""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("utf-8", "replace")
    if isinstance(value, STRING_TYPES):
        return value
    try:
        return u"%s" % (value,)
    except Exception:
        return u""


def is_valid_section_id(value):
    """区块 id 是否合法（见 :data:`SECTION_ID_RE`）"""
    return bool(isinstance(value, STRING_TYPES)
                and SECTION_ID_RE.match(value))


def normalize_panels(panels):
    """过滤面板，返回 ``(保留的, [(序号, 原因), ...])``

    只丢不合法的，不抛异常：一个 provider 的面板写错了，最多是自己这块
    少几个面板，绝不影响别的区块。
    """
    kept = []
    dropped = []
    for index, panel in enumerate(panels or []):
        if not isinstance(panel, dict):
            dropped.append((index, "panel is not a dict"))
            continue
        panel_type = panel.get("type")
        if panel_type not in PANEL_TYPES:
            dropped.append((index, "unknown panel type %r" % (panel_type,)))
            continue
        if panel_type == "bar-chart-panel":
            # dashboard.js 的 loadBarChart 直接 JSON.parse(panel.data)，
            # 空/非字符串会让它抛异常并中断**后面所有**面板的渲染。
            if not to_text(panel.get("data")):
                dropped.append((index, "bar-chart-panel without 'data'"))
                continue
        else:
            # number 可以是 0，所以判 None 而不是判假
            if panel.get("number") is None:
                dropped.append((index, "simple-panel without 'number'"))
                continue
        kept.append(panel)
    return kept, dropped


def normalize_section(section, expected_id=None):
    """校验并补全 provider 返回的区块。

    :param section: provider 的返回值
    :param expected_id: provider 的 ``section_id``（注册时声明的那个）
    :returns: ``(区块 dict, None)`` 或 ``(None, 原因)``

    这里**不吞异常也不抛异常**：要么给一个可直接 json 序列化的区块，
    要么给一个可写进日志的原因字符串。
    """
    if not isinstance(section, dict):
        return None, "不是 dict（%r）" % (type(section).__name__,)

    section_id = section.get("id") or expected_id
    if not is_valid_section_id(section_id):
        return None, "非法 id %r" % (section_id,)
    if expected_id and section_id != expected_id:
        # 允许 provider 不写 id（用注册时声明的兜底），但不允许自报一个
        # 不同的 id —— 数据接口是按 id 找 provider 的，两处不一致会出现
        # "请求 A 拿到 B"。
        return None, "id %r 与声明的 section_id %r 不一致" % (
            section_id, expected_id)

    api_version = section.get("api_version", API_VERSION)
    try:
        api_version = int(api_version)
    except (TypeError, ValueError):
        return None, "非法 api_version %r" % (section.get("api_version"),)
    if api_version > API_VERSION:
        return None, ("api_version %s 高于 core 支持的 %s（升级 core 或降低 "
                      "add-on 的契约版本）" % (api_version, API_VERSION))

    panels, dropped = normalize_panels(section.get("panels"))

    # 刻意**不**从这里产出 permission：权限是廉价属性（页面骨架阶段就要
    # 用它决定"要不要给这块留容器"），放在返回值里会变成第二个事实来源
    # —— 骨架用属性、数据接口用返回值，两处迟早不一致。
    return {
        "id": section_id,
        "title": to_text(section.get("title")) or section_id,
        "panels": panels,
        "api_version": api_version,
        # 给调用方（和日志）一个可观测的量：丢弃了几块、为什么
        "dropped_panels": ["#%d: %s" % (i, why) for i, why in dropped],
    }, None


def get_provider_permission(provider):
    """provider 声明的权限（廉价属性），默认 :data:`DEFAULT_PERMISSION`"""
    return to_text(getattr(provider, "permission", None)) or DEFAULT_PERMISSION


def partition_providers(providers, is_available):
    """把注册者分成三堆：``(available, unavailable, invalid)``

    :param providers: ``[(注册名, provider), ...]``
    :param is_available: ``callable(provider) -> bool``

    ★ 分三堆而不是两堆，是因为调用方对三者的**日志级别**不一样：

      * ``available``   —— 正常，用；
      * ``unavailable`` —— 该 add-on 没装在**这个站点**。这是**正常情况**
        （同一个进程里还跑着装了它的站点，甚至这才是常态），记 info 就够，
        记 warning 会把"没装"和"坏了"混在一起；
      * ``invalid``     —— section_id 写错、或者可用性判定自己抛了异常。
        这才是需要人看的，记 warning。

    合并成"skipped"会让"正确的静默"和"真正的故障"长得一模一样。
    """
    available = []
    unavailable = []
    invalid = []
    for name, provider in providers or []:
        try:
            section_id = getattr(provider, "section_id", None)
            if not is_valid_section_id(section_id):
                invalid.append((name, "非法 section_id %r" % (section_id,)))
                continue
            if not is_available(provider):
                unavailable.append((name, provider))
                continue
            available.append((name, provider))
        except Exception as exc:  # noqa: B902  (provider 自己的锅，不该拖垮别人)
            invalid.append((name, "可用性判定失败: %s" % (exc,)))
    return available, unavailable, invalid
