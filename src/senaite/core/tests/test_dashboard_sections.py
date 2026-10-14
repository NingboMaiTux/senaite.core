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

"""仪表盘插件区块（``IDashboardSection``）契约的测试。

只测**纯逻辑**（``sections.py``），不碰 Zope：这些判定是"装/卸 add-on
不影响原有图表"的兜底所在，值得一条断言守一个。

两种跑法都可以：

    # buildout 里（Zope 可用）
    bin/test -s senaite.core -t test_dashboard_sections

    # 离线（只要 py2.7 / py3，没有 Zope 也行）
    python -m unittest senaite.core.tests.test_dashboard_sections
"""

import os
import unittest


def _load_sections_module():
    """拿到 ``browser/dashboard/sections.py``

    优先走包路径；没有 Zope 时按**文件路径**加载同一份源码
    （``senaite/core/__init__.py`` 会 import ``zope.i18nmessageid``，
    离线环境拿不到，但 ``sections.py`` 自己只依赖 ``re``）。
    """
    try:
        from senaite.core.browser.dashboard import sections
        return sections
    except ImportError:
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "browser", "dashboard", "sections.py")
    path = os.path.normpath(path)

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "dashboard_sections", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except ImportError:  # py2.7
        import imp
        return imp.load_source("dashboard_sections", path)


sections = _load_sections_module()


class _Provider(object):
    """最小的 provider 替身（只有廉价属性）"""

    def __init__(self, section_id, addon="maitux.example", permission=None):
        self.section_id = section_id
        self.addon = addon
        if permission is not None:
            self.permission = permission


class TestSectionId(unittest.TestCase):
    """section_id 会进 DOM id / URL query / 日志，必须可预测"""

    def test_valid(self):
        for value in ("stability", "s1", "my_section", "a" * 32):
            self.assertTrue(sections.is_valid_section_id(value), value)

    def test_invalid(self):
        for value in ("", "S", "1abc", "has-dash", "has space", "中文",
                      "a" * 33, None, 12, u"stability "):
            self.assertFalse(sections.is_valid_section_id(value), repr(value))


class TestNormalizePanels(unittest.TestCase):
    def test_keeps_known_types(self):
        panels = [
            {"type": "simple-panel", "number": 0},
            {"type": "bar-chart-panel", "data": "{}"},
        ]
        kept, dropped = sections.normalize_panels(panels)
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, [])

    def test_number_zero_is_not_dropped(self):
        # 0 是合法计数：判 None 而不是判假，否则"这一档是 0"会整块消失
        kept, dropped = sections.normalize_panels(
            [{"type": "simple-panel", "number": 0}])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_drops_unknown_and_incomplete(self):
        panels = [
            {"type": "pie-chart-panel", "number": 1},
            {"type": "simple-panel"},                  # 缺 number
            {"type": "bar-chart-panel"},               # 缺 data
            {"type": "bar-chart-panel", "data": ""},   # data 是空串
            "not-a-dict",
        ]
        kept, dropped = sections.normalize_panels(panels)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 5)


class TestNormalizeSection(unittest.TestCase):
    def test_minimal_section(self):
        section, reason = sections.normalize_section(
            {"title": u"稳定性"}, expected_id="stability")
        self.assertIsNone(reason)
        self.assertEqual(section["id"], "stability")
        self.assertEqual(section["title"], u"稳定性")
        self.assertEqual(section["panels"], [])
        self.assertEqual(section["api_version"], sections.API_VERSION)

    def test_permission_is_not_part_of_the_payload(self):
        # 权限是 provider 的**廉价属性**（骨架阶段要用），
        # 放进返回值就会变成第二个事实来源
        section, _ = sections.normalize_section(
            {"id": "stability", "permission": "cmf.ManagePortal"})
        self.assertNotIn("permission", section)

    def test_rejects_non_dict(self):
        for value in (None, [], "x", 3):
            section, reason = sections.normalize_section(value)
            self.assertIsNone(section)
            self.assertTrue(reason)

    def test_rejects_id_mismatch(self):
        # 数据接口是按 id 找 provider 的：自报一个不同的 id 会出现
        # "请求 A 拿到 B"
        section, reason = sections.normalize_section(
            {"id": "other"}, expected_id="stability")
        self.assertIsNone(section)
        self.assertIn("不一致", reason)

    def test_rejects_newer_api_version(self):
        section, reason = sections.normalize_section(
            {"id": "stability",
             "api_version": sections.API_VERSION + 1})
        self.assertIsNone(section)
        self.assertIn("api_version", reason)

    def test_accepts_same_api_version(self):
        section, reason = sections.normalize_section(
            {"id": "stability", "api_version": sections.API_VERSION})
        self.assertIsNone(reason)

    def test_reports_dropped_panels(self):
        section, reason = sections.normalize_section(
            {"id": "stability", "panels": [{"type": "nope"}]})
        self.assertIsNone(reason)
        self.assertEqual(section["panels"], [])
        self.assertEqual(len(section["dropped_panels"]), 1)


class TestPartitionProviders(unittest.TestCase):
    """站点级筛选必须把"没装"和"坏了"分成两堆（日志级别不同）"""

    def test_empty_registry_is_fine(self):
        available, unavailable, invalid = sections.partition_providers(
            [], lambda p: True)
        self.assertEqual(available, [])
        self.assertEqual(unavailable, [])
        self.assertEqual(invalid, [])

    def test_not_installed_is_not_an_error(self):
        # 该 add-on 没装在**这个**站点 = 正常情况：不进 invalid，
        # 否则每个没装它的站点都会刷 warning
        providers = [("maitux.stability", _Provider("stability"))]
        available, unavailable, invalid = sections.partition_providers(
            providers, lambda p: False)
        self.assertEqual(available, [])
        self.assertEqual([name for name, _ in unavailable],
                         ["maitux.stability"])
        self.assertEqual(invalid, [])

    def test_invalid_section_id_is_reported(self):
        providers = [
            ("bad", _Provider("Has-Dash")),
            ("good", _Provider("good_one")),
        ]
        available, unavailable, invalid = sections.partition_providers(
            providers, lambda p: True)
        self.assertEqual([name for name, _ in available], ["good"])
        self.assertEqual(unavailable, [])
        self.assertEqual([name for name, _ in invalid], ["bad"])

    def test_one_broken_provider_does_not_hide_the_others(self):
        class Boom(object):
            section_id = "boom"

        def is_available(provider):
            if isinstance(provider, Boom):
                raise ValueError("bang")
            return True

        providers = [
            ("boom", Boom()),
            ("good", _Provider("good_one")),
        ]
        available, unavailable, invalid = sections.partition_providers(
            providers, is_available)
        self.assertEqual([name for name, _ in available], ["good"])
        self.assertEqual(unavailable, [])
        self.assertEqual([name for name, _ in invalid], ["boom"])


class TestProviderPermission(unittest.TestCase):
    def test_default_permission(self):
        self.assertEqual(
            sections.get_provider_permission(_Provider("s")),
            sections.DEFAULT_PERMISSION)

    def test_declared_permission(self):
        self.assertEqual(
            sections.get_provider_permission(
                _Provider("s", permission=u"cmf.ManagePortal")),
            u"cmf.ManagePortal")


if __name__ == "__main__":
    unittest.main()
