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

from zope.interface import Attribute
from zope.interface import Interface


class IDashboardSection(Interface):
    """add-on 向 SENAITE 仪表盘（``@@senaite-dashboard``）贡献一个统计区块。

    这是仪表盘统计区**唯一的扩展点**。注册方式（add-on 侧 ZCML）::

        <utility
            factory=".dashboardsection.StabilityDashboardSection"
            provides="maitux.stability.dashboardsection.IDashboardSection"
            name="maitux.stability"
            />

    ★ 用 ``factory=`` 而不是 ``component=``：``component`` 注册的是**类对象
      本身**，core 枚举出来的 provider 会是个类，
      ``provider.get_dashboard_section()`` 在 py2 下变成 unbound method 调用
      直接 TypeError（已实测踩到）。``factory`` 才会实例化。

    为什么是 utility，而不是让 add-on 各自覆盖 ``@@senaite-dashboard``
    ----------------------------------------------------------------

    ZCML 注册是**进程级**的，视图覆盖也一样：两个 add-on 各自覆盖同一个
    视图名时，命中谁取决于请求 ``__iro__`` 的顺序（哪个浏览器层先被标记），
    表现是"其中一个静默失效、日志里连一条都没有"。utility 是**可枚举**的
    —— core 拿到全部注册者，再逐个做站点级筛选，N 个 add-on 互不打架。

    为什么要有 ``addon`` 这个属性
    ----------------------------

    同样因为 ZCML 是进程级的：装了 add-on A 的站点和没装 A 的站点，
    在进程里**看到的是同一份注册表**。所以"这个区块该不该出现"不能只看
    注册表有没有，必须问**当前站点**装没装那个 add-on。core 读的是
    ``portal_setup.getLastVersionForProfile('<addon>:default')``
    —— 装过给版本元组、没装/已卸载给 ``'unknown'``，于是：

    * 装上 add-on     -> 区块出现；
    * 卸载 add-on     -> 区块消失；
    * 该 add-on 的代码根本没部署 -> 连注册都没有，同样不出现。

    ★ 刻意**不用** ``portal_quickinstaller.isProductInstalled()``：
      它查的是 quickinstaller 下一个**同名子对象**的存在性，而卸载只删
      Add-ons 面板传进去的那个 id（``<名字>:default``）——``<名字>`` 那个
      子对象会留下来，卸载后照样返回 True（2026-10-14 线上踩到：
      卸载模块后区块仍在）。细节见 ``dashboard.is_addon_installed``。

    三种情况下，core 自带的三个区块（样本 / 检验项目 / 工作表）**一行都不变**。
    """

    section_id = Attribute(
        u"区块 id。会进 DOM id（``dashboard-section-<id>``）、数据接口的 "
        u"``?section=<id>`` 和日志，所以必须是可预测的 "
        u"``^[a-z][a-z0-9_]{1,31}$``（小写字母开头）。"
        u"**廉价属性**：页面骨架渲染时只读它，不会触发任何数据计算。")

    addon = Attribute(
        u"本区块所属 add-on 的名字（默认 profile 为 ``<名字>:default``，"
        u"SENAITE 的 add-on 都是这个约定），或直接给 profile id"
        u"（``'my.addon:plone'`` 这种带冒号的）。"
        u"core 用它做**站点级**门控，见类文档。"
        u"``None`` = 全局区块（所有站点都显示，谨慎使用）。")

    permission = Attribute(
        u"可选。看这一块需要的权限，默认 ``senaite.core: View Dashboard``。"
        u"**廉价属性**：骨架阶段就要用它决定「要不要给这块留容器」，"
        u"所以它不能藏在 :meth:`get_dashboard_section` 的返回值里"
        u"——那样骨架就得把数据先算一遍。")

    def get_dashboard_section():
        u"""返回区块数据（**只在数据接口真正取这一块时才调用**）。

        :returns: dict

            ``id``          区块 id，必须与 :attr:`section_id` 一致
            ``title``       区块标题（已翻译的显示文案）
            ``panels``      面板列表，见下
            ``api_version`` 可选，契约版本（当前 ``1``）

        面板（panel）目前支持两种，与 ``dashboard.js`` 的渲染一一对应：

        ``simple-panel``::

            {"type": "simple-panel", "description": u"待接收",
             "number": 12, "percentage": 30.0,
             "legend": u"共 40 (30.0%)", "link": "<url>"}

        ``bar-chart-panel``::

            {"type": "bar-chart-panel", "name": u"样本趋势",
             "description": u"样本趋势",
             "data": "<json>", "datacolors": "<json>"}

        其中 ``data`` 是 ``{"data": [{"date": <桶>, <系列名>: <数>}, ...],
        "states": [<系列名>, ...]}``，``datacolors`` 是
        ``{<系列名>: <颜色>}``。

        ★ **桶与系列由 provider 自己算好**，core 只负责画。这一点是刻意的：
          core 自带的图表是按 ``created`` 分桶、按工作流状态分系列，而
          有些业务的柱子是"按另一个日期分桶、按业务档位分系列"（例如
          稳定性按**时间点的目标日期**分桶），套不进
          ``_chart_panel(title, catalog, query)`` 那个签名。把口径交给
          provider，core 才能既保持自己的三个区块不变，又能被扩展。

        未识别的面板类型会被**丢弃并记日志**（不抛异常）——一个 provider
        写得不对，最多是自己这一块少几个面板，不会影响别的区块。
        """
