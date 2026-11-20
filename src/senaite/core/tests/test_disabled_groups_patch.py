# -*- coding: utf-8 -*-

import os
import sys
import types
import unittest


def _load_module(name, path):
    """加载模块：py3 用 importlib，py2.7 回退 imp"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    except (ImportError, AttributeError):
        import imp
        return imp.load_source(name, path)


def _func_of(method):
    """返回方法/函数的底层函数对象（兼容 py2 unbound method）"""
    return getattr(method, "im_func", getattr(method, "__func__", method))


class DummyLogger(object):
    """最小 logger stub"""

    def info(self, message):
        return message

    def warn(self, message):
        return message


class TestDisabledGroupsPatch(unittest.TestCase):
    """禁用组权限失效补丁回归测试"""

    def setUp(self):
        self._added_modules = {}
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
        class DummyZODBGroupManager(object):
            prefix = ""
            removed = None

            def getGroupsForPrincipal(self, principal, request=None):
                return ("group1", "group2", "group3")

            def removeGroup(self, group_id):
                DummyZODBGroupManager.removed = group_id

        fake_pas_plugins = types.ModuleType(
            "Products.PluggableAuthService.plugins.ZODBGroupManager")
        fake_pas_plugins.ZODBGroupManager = DummyZODBGroupManager

        fake_products = types.ModuleType("Products")
        fake_pas = types.ModuleType("Products.PluggableAuthService")
        fake_pas_plugins_parent = types.ModuleType(
            "Products.PluggableAuthService.plugins")
        fake_products.PluggableAuthService = fake_pas
        fake_pas_plugins_parent.ZODBGroupManager = fake_pas_plugins

        fake_senaite = types.ModuleType("senaite")
        fake_core = types.ModuleType("senaite.core")
        fake_core.logger = DummyLogger()
        fake_senaite.core = fake_core

        # 中文注释：动态可变的禁用组集合，供 group_status.is_group_disabled
        # 的 fake 实现使用。
        self.disabled = set()
        self.discarded = []

        def fake_is_group_disabled(group_id):
            return group_id in self.disabled

        def fake_discard_group_disabled(group_id):
            self.discarded.append(group_id)
            self.disabled.discard(group_id)

        fake_browser = types.ModuleType("senaite.core.browser")
        fake_usergroup = types.ModuleType(
            "senaite.core.browser.usergroup")
        fake_group_status = types.ModuleType(
            "senaite.core.browser.usergroup.group_status")
        fake_group_status.is_group_disabled = fake_is_group_disabled
        fake_group_status.discard_group_disabled = \
            fake_discard_group_disabled
        fake_usergroup.group_status = fake_group_status
        fake_browser.usergroup = fake_usergroup
        fake_core.browser = fake_browser

        self._install_module("Products", fake_products)
        self._install_module("Products.PluggableAuthService", fake_pas)
        self._install_module(
            "Products.PluggableAuthService.plugins",
            fake_pas_plugins_parent)
        self._install_module(
            "Products.PluggableAuthService.plugins.ZODBGroupManager",
            fake_pas_plugins)
        self._install_module("senaite", fake_senaite)
        self._install_module("senaite.core", fake_core)
        self._install_module("senaite.core.browser", fake_browser)
        self._install_module("senaite.core.browser.usergroup", fake_usergroup)
        self._install_module(
            "senaite.core.browser.usergroup.group_status",
            fake_group_status)

        module_name = "disabled_groups_patch_under_test"
        self._added_modules[module_name] = sys.modules.get(module_name)
        module_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "patches_groups.py"))
        return _load_module(module_name, module_path)

    def _get_plugin_class(self):
        return sys.modules[
            "Products.PluggableAuthService.plugins.ZODBGroupManager"
        ].ZODBGroupManager

    def test_patch_filters_disabled_groups(self):
        """补丁应从用户组查询结果中剔除禁用组"""
        self.module.patch_disabled_groups()
        plugin = self._get_plugin_class()()

        self.disabled.add("group2")
        groups = plugin.getGroupsForPrincipal("user1")

        self.assertEqual(groups, ("group1", "group3"))

    def test_patch_keeps_groups_when_none_disabled(self):
        """没有禁用组时应原样返回"""
        self.module.patch_disabled_groups()
        plugin = self._get_plugin_class()()

        groups = plugin.getGroupsForPrincipal("user1")

        self.assertEqual(groups, ("group1", "group2", "group3"))

    def test_patch_strips_plugin_prefix(self):
        """带前缀的组 id 应先剥离前缀再判断禁用状态"""
        self.module.patch_disabled_groups()
        original = self.module._ORIGINAL_GET_GROUPS_FOR_PRINCIPAL

        def fake_original(plugin, principal, request=None):
            return ("pre.group1", "pre.group2")

        self.module._ORIGINAL_GET_GROUPS_FOR_PRINCIPAL = fake_original
        try:
            plugin = self._get_plugin_class()()
            plugin.prefix = "pre."
            self.disabled.add("group2")

            self.assertEqual(
                plugin.getGroupsForPrincipal("user1"), ("pre.group1",))
        finally:
            self.module._ORIGINAL_GET_GROUPS_FOR_PRINCIPAL = original

    def test_patch_is_idempotent(self):
        """重复调用 patch_disabled_groups 不应重复包装"""
        self.module.patch_disabled_groups()
        first = _func_of(self._get_plugin_class().getGroupsForPrincipal)

        self.module.patch_disabled_groups()
        second = _func_of(self._get_plugin_class().getGroupsForPrincipal)

        # 中文注释：Python 2 的 unbound method 每次访问都是新包装对象，
        # 这里比较其底层函数，避免版本差异导致的误判。
        self.assertIs(first, second)

    def test_patch_wraps_remove_group(self):
        """删除组时应调用原始实现并清理禁用标记"""
        self.module.patch_disabled_groups()
        plugin = self._get_plugin_class()()
        self.disabled.add("group2")

        plugin.removeGroup("group2")

        self.assertEqual(self._get_plugin_class().removed, "group2")
        self.assertEqual(self.discarded, ["group2"])


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(
        TestDisabledGroupsPatch)
