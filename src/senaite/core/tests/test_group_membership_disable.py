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


class _Namespace(object):
    """py2/py3 兼容的简单命名空间（py2.7 无 types.SimpleNamespace）"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class DummyPloneUtils(object):
    """模拟 plone_utils，记录 portal messages"""

    def __init__(self):
        self.messages = []

    def addPortalMessage(self, message, level="info"):
        self.messages.append((message, level))


class DummyContext(object):
    def __init__(self):
        self.plone_utils = DummyPloneUtils()


class DummyRequest(object):
    def __init__(self, form=None, **attrs):
        self.form = form or {}
        for key, value in attrs.items():
            setattr(self, key, value)


class DummyUserMembershipBase(object):
    """模拟 CMFPlone 的 UserMembershipControlPanel"""

    def __init__(self):
        self.request = DummyRequest()
        self.context = DummyContext()
        self.candidates = []
        self.updated = False

    def getPotentialGroups(self, searchString):
        return self.candidates

    def update(self):
        self.updated = True


class DummyGroupMembershipBase(object):
    """模拟 CMFPlone 的 GroupMembershipControlPanel"""

    def __init__(self):
        self.request = DummyRequest()
        self.context = DummyContext()
        self.canAddUsers = True
        self.updated = False

    def update(self):
        self.updated = True


class TestGroupMembershipDisable(unittest.TestCase):
    """禁用组在成员管理页面的行为回归测试"""

    def setUp(self):
        self._added_modules = {}
        self.disabled = set()
        self.user_mod, self.group_mod = self._load_modules()

    def tearDown(self):
        for name, original in self._added_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def _install_module(self, name, module):
        self._added_modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _load_modules(self):
        fake_plonepass = types.ModuleType("Products.CMFPlone")
        fake_plonepass.PloneMessageFactory = lambda text: text

        fake_controlpanel = types.ModuleType("Products.CMFPlone.controlpanel")
        fake_browser = types.ModuleType(
            "Products.CMFPlone.controlpanel.browser")
        fake_user_membership = types.ModuleType(
            "Products.CMFPlone.controlpanel.browser."
            "usergroups_usermembership")
        fake_user_membership.UserMembershipControlPanel = \
            DummyUserMembershipBase
        fake_group_membership = types.ModuleType(
            "Products.CMFPlone.controlpanel.browser."
            "usergroups_groupmembership")
        fake_group_membership.GroupMembershipControlPanel = \
            DummyGroupMembershipBase

        fake_senaite = types.ModuleType("senaite")
        fake_core = types.ModuleType("senaite.core")
        fake_senaite.core = fake_core

        def fake_is_group_disabled(group_id):
            return group_id in self.disabled

        fake_browser_senaite = types.ModuleType("senaite.core.browser")
        fake_usergroup = types.ModuleType("senaite.core.browser.usergroup")
        fake_group_status = types.ModuleType(
            "senaite.core.browser.usergroup.group_status")
        fake_group_status.is_group_disabled = fake_is_group_disabled
        fake_usergroup.group_status = fake_group_status
        fake_browser_senaite.usergroup = fake_usergroup
        fake_core.browser = fake_browser_senaite

        self._install_module("Products", types.ModuleType("Products"))
        self._install_module("Products.CMFPlone", fake_plonepass)
        self._install_module(
            "Products.CMFPlone.controlpanel", fake_controlpanel)
        self._install_module(
            "Products.CMFPlone.controlpanel.browser", fake_browser)
        self._install_module(
            "Products.CMFPlone.controlpanel.browser."
            "usergroups_usermembership", fake_user_membership)
        self._install_module(
            "Products.CMFPlone.controlpanel.browser."
            "usergroups_groupmembership", fake_group_membership)
        self._install_module("senaite", fake_senaite)
        self._install_module("senaite.core", fake_core)
        self._install_module(
            "senaite.core.browser", fake_browser_senaite)
        self._install_module(
            "senaite.core.browser.usergroup", fake_usergroup)
        self._install_module(
            "senaite.core.browser.usergroup.group_status", fake_group_status)

        base_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "browser", "usergroup"))

        def load(name, filename):
            path = os.path.join(base_path, filename)
            return _load_module(name, path)

        user_mod = load("usermembership_under_test",
                        "usergroups_usermembership.py")
        group_mod = load("groupmembership_under_test",
                         "usergroups_groupmembership.py")
        return user_mod, group_mod

    def _group(self, group_id):
        return _Namespace(getId=lambda: group_id)

    def test_potential_groups_filters_disabled(self):
        """可分配组候选中不显示被禁用的组"""
        view = self.user_mod.UserMembershipControlPanel()
        view.candidates = [self._group("group1"), self._group("group2")]
        self.disabled.add("group2")

        groups = view.getPotentialGroups("")

        self.assertEqual([g.getId() for g in groups], ["group1"])

    def test_update_ignores_disabled_add(self):
        """向禁用组添加成员的提交应被忽略并提示"""
        view = self.user_mod.UserMembershipControlPanel()
        view.request = DummyRequest(
            {"form.submitted": True, "add": ["group1", "group2"]})
        self.disabled.add("group2")

        view.update()

        self.assertEqual(view.request.form["add"], ["group1"])
        self.assertEqual(len(view.context.plone_utils.messages), 1)

    def test_group_membership_blocks_disabled_group(self):
        """禁用组不允许添加成员"""
        view = self.group_mod.GroupMembershipControlPanel()
        view.request = DummyRequest(
            {"form.submitted": True, "add": ["user1"],
             "groupname": "group2"})
        self.disabled.add("group2")

        view.update()

        self.assertEqual(view.request.form["add"], [])
        self.assertFalse(view.canAddUsers)


def test_suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(
        TestGroupMembershipDisable)
