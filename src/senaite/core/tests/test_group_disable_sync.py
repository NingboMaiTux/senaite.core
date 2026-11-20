# -*- coding: utf-8 -*-

import importlib.util
import os
import sys
import types
import unittest


class DummyLogger(object):
    """最小 logger stub"""

    def info(self, message):
        return message

    def warn(self, message):
        return message


class DummyGroupDataTool(object):
    """模拟 portal_groupdata 工具"""

    def __init__(self):
        self.__dict__.setdefault("calls", [])


class TestGroupDisableSync(unittest.TestCase):
    """组禁用同步回归测试"""

    def setUp(self):
        self._added_modules = {}
        self.tool = DummyGroupDataTool()
        self.module = self._load_module_under_test()

    def tearDown(self):
        # 中文注释：恢复测试过程中临时注入的模块，避免污染其他用例。
        for name, original in self._added_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def _install_module(self, name, module):
        self._added_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _load_module_under_test(self):
        fake_api = types.SimpleNamespace(
            get_tool=lambda name: self.tool
            if name == "portal_groupdata" else None)

        fake_bika = types.ModuleType("bika")
        fake_bika_lims = types.ModuleType("bika.lims")
        fake_bika_lims.api = fake_api
        fake_bika.lims = fake_bika_lims

        fake_senaite = types.ModuleType("senaite")
        fake_core = types.ModuleType("senaite.core")
        fake_core.logger = DummyLogger()
        fake_senaite.core = fake_core

        self._install_module("bika", fake_bika)
        self._install_module("bika.lims", fake_bika_lims)
        self._install_module("senaite", fake_senaite)
        self._install_module("senaite.core", fake_core)

        module_name = "group_disable_sync_under_test"
        self._added_modules[module_name] = sys.modules.get(module_name)
        module_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "browser", "usergroup", "group_status.py"))
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def test_set_group_disabled_persists_flag(self):
        """禁用组时应把组 id 持久化到 groupdata 工具"""
        self.assertFalse(self.module.is_group_disabled("group1"))

        result = self.module.set_group_disabled("group1", True)

        self.assertTrue(result)
        self.assertTrue(self.module.is_group_disabled("group1"))
        self.assertEqual(
            getattr(self.tool, "_senaite_disabled_groups"), ["group1"])

    def test_set_group_disabled_removes_flag(self):
        """取消禁用时应从存储中移除组 id"""
        self.module.set_group_disabled("group1", True)
        self.module.set_group_disabled("group1", False)

        self.assertFalse(self.module.is_group_disabled("group1"))
        self.assertEqual(
            getattr(self.tool, "_senaite_disabled_groups"), [])

    def test_discard_group_disabled_removes_flag(self):
        """删除组时应能清理其禁用标记"""
        self.module.set_group_disabled("group1", True)

        result = self.module.discard_group_disabled("group1")

        self.assertTrue(result)
        self.assertFalse(self.module.is_group_disabled("group1"))
        self.assertEqual(
            getattr(self.tool, "_senaite_disabled_groups"), [])

    def test_discard_group_disabled_noop(self):
        """组不在禁用列表时 discard 返回 False"""
        self.assertFalse(self.module.discard_group_disabled("group1"))

    def test_no_groupdata_tool_returns_false(self):
        """找不到 portal_groupdata 时安全返回"""
        fake_module = self.module
        original = fake_module._get_groupdata_tool

        fake_module._get_groupdata_tool = lambda: None
        try:
            self.assertFalse(fake_module.set_group_disabled("group1", True))
            self.assertFalse(fake_module.is_group_disabled("group1"))
        finally:
            fake_module._get_groupdata_tool = original

    def test_groups_template_has_no_delete_checkbox(self):
        """组列表模板不应再有物理删除勾选框"""
        template_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "..", "browser", "usergroup", "templates",
            "usergroups_groupsoverview.pt"))

        with open(template_path, "r") as handle:
            template = handle.read()

        self.assertNotIn('name="delete:list"', template)
        self.assertNotIn("listingheader_remove", template)
        self.assertIn("groups.disabled:records", template)
        self.assertIn("groups.id:records", template)
        self.assertIn("is_group_disabled", template)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(
        TestGroupDisableSync)
