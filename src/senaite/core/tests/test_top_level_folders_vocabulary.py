# -*- coding: utf-8 -*-
"""侧边栏文件夹词汇表 (senaite.core.vocabularies.top_level_folders) 回归测试

背景：门户根下各文件夹的 Title() 返回类型并不统一 ——
AT 文件夹和 core 的 DX 文件夹返回 utf-8 字节串 (str)，而 maitux.projects /
maitux.stock / maitux.stability 这类按请求语言翻译 Title() 的 add-on 文件夹
返回 unicode。Py2 里 str 与 unicode 比较，会先把 str 按 ASCII 解码，所以只要有
一个字节串标题带非 ASCII 字符（比如把 clients 改名成「客户」），
TopLevelFoldersVocabulary 里的 items.sort() 就会抛

    UnicodeDecodeError: 'ascii' codec can't decode byte 0xe5 in position 0

整个 /setup/@@edit（侧边栏文件夹那个多选框）因此 500。标题全是 ASCII 时两种类型
混着比不出错，所以这个问题只在有人用了中文标题的站点上才会冒出来。

全部用例不依赖 Plone / Zope：词汇表模块用桩加载，它用到的 bika.lims.api 函数由
FakeApi 顶替 —— 其中 safe_unicode 是从 bika/lims/api/__init__.py 里按 AST 原样
抽出来的真实实现，SKIP_NAV_TYPES 也是真实的配置文件，不是手写的替身。
"""

import ast
import imp
import os
import sys
import types
import unittest

import six


PACKAGE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir))
LIMS_DIR = os.path.abspath(
    os.path.join(PACKAGE_DIR, os.pardir, os.pardir, "bika", "lims"))

#: 被测的词汇表模块。换成别的路径即可对比修复前后的行为
VOCABULARY_SOURCE = os.path.join(PACKAGE_DIR, "vocabularies", "setup.py")
SETUP_CONFIG_SOURCE = os.path.join(PACKAGE_DIR, "config", "setup.py")
API_SOURCE = os.path.join(LIMS_DIR, "api", "__init__.py")

MODULE_NAME = "_top_level_folders_vocabulary_under_test"
VOCABULARY_NAME = "TopLevelFoldersVocabulary"


def load_api_function(name):
    """把 bika.lims.api 里的某个函数按源码原样抽出来

    bika.lims.api 一 import 就要拉起整套 Plone，这里只需要 safe_unicode 这一个
    只依赖 six 的纯函数，所以走 AST 单独编译它，保证测的是真实实现。
    """
    with open(API_SOURCE, "r") as handle:
        tree = ast.parse(handle.read(), API_SOURCE)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node])
            ast.fix_missing_locations(module)
            namespace = {"six": six}
            exec(compile(module, API_SOURCE, "exec"), namespace)
            return namespace[name]
    raise AssertionError("%s not found in %s" % (name, API_SOURCE))


class FakeFolder(object):
    """模拟门户根下的一个内容对象

    `title` 原样由 Title() 返回，由用例决定它是 utf-8 字节串还是 unicode，
    就像真实站点里不同类型的文件夹那样。
    """

    def __init__(self, portal_type, title):
        self.portal_type = portal_type
        self._title = title

    def Title(self):  # noqa camelCase (Plone API)
        return self._title


class FakeTool(object):
    """模拟门户根下的非内容对象（portal_catalog、acl_users 之类）"""


class FakePortal(object):
    """模拟 Plone 站点根：按给定顺序暴露子对象"""

    def __init__(self, children):
        self._ids = [obj_id for obj_id, obj in children]
        self._children = dict(children)

    def objectIds(self):  # noqa camelCase (Plone API)
        return list(self._ids)

    def __getitem__(self, obj_id):
        return self._children[obj_id]


class FakeTerm(object):
    """模拟 zope.schema.vocabulary.SimpleTerm"""

    def __init__(self, value, token=None, title=None):
        self.value = value
        self.token = token
        self.title = title


class FakeVocabulary(object):
    """模拟 zope.schema.vocabulary.SimpleVocabulary（只实现用到的部分）"""

    def __init__(self, terms):
        self.terms = list(terms)

    @classmethod
    def fromItems(cls, items):  # noqa camelCase (zope.schema API)
        return cls(FakeTerm(*item) for item in items)

    def __iter__(self):
        return iter(self.terms)

    def __len__(self):
        return len(self.terms)


class FakeApi(types.ModuleType):
    """模拟 bika.lims.api：只提供词汇表用到的那几个函数"""

    def __init__(self, portal):
        types.ModuleType.__init__(self, "bika.lims.api")
        self.portal = portal
        self.safe_unicode = load_api_function("safe_unicode")

    def get_portal(self):
        return self.portal

    def is_object(self, obj):
        return isinstance(obj, FakeFolder)

    def get_portal_type(self, obj):
        return obj.portal_type

    def get_title(self, obj):
        return obj.Title()


class VocabularyModules(object):
    """用桩加载真实的 vocabularies/setup.py"""

    def __init__(self, portal):
        self.portal = portal
        self._saved = {}
        self.module = None
        self._install()

    def _save(self, name):
        self._saved[name] = sys.modules.get(name)

    def _module(self, name, **attrs):
        """创建并注册一个桩模块"""
        self._save(name)
        module = types.ModuleType(name)
        module.__path__ = []
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        return module

    def _install(self):
        api = FakeApi(self.portal)
        self._module("bika")
        lims = self._module("bika.lims", _=lambda msgid, **kw: msgid, api=api)
        self._save("bika.lims.api")
        sys.modules["bika.lims.api"] = api
        lims.api = api

        # senaite.core.api.geo / .config.setup / .interfaces
        self._module("senaite")
        core = self._module("senaite.core")
        core_api = self._module(
            "senaite.core.api", geo=types.ModuleType("geo"))
        core_config = self._module("senaite.core.config")
        # 真实的配置文件：纯数据，没有任何 import
        self._save("senaite.core.config.setup")
        core_config_setup = imp.load_source(
            "senaite.core.config.setup", SETUP_CONFIG_SOURCE)
        core_interfaces = self._module(
            "senaite.core.interfaces", IWorksheetLayouts=object)
        core.api = core_api
        core.config = core_config
        core.interfaces = core_interfaces
        core_config.setup = core_config_setup

        # zope.component / zope.i18n.locales / zope.interface / zope.schema
        zope_pkg = self._module("zope")
        component = self._module(
            "zope.component", getUtilitiesFor=lambda iface: [])
        i18n = self._module("zope.i18n")
        locales = self._module("zope.i18n.locales", locales=object())
        interface = self._module(
            "zope.interface", implementer=lambda *ifaces: lambda cls: cls)
        schema = self._module("zope.schema")
        schema_interfaces = self._module(
            "zope.schema.interfaces", IVocabularyFactory=object)
        schema_vocabulary = self._module(
            "zope.schema.vocabulary", SimpleVocabulary=FakeVocabulary)
        zope_pkg.component = component
        zope_pkg.i18n = i18n
        i18n.locales = locales
        zope_pkg.interface = interface
        zope_pkg.schema = schema
        schema.interfaces = schema_interfaces
        schema.vocabulary = schema_vocabulary

        # 真实的词汇表模块，用私有名字加载，避免盖掉真实环境里的同名模块
        self._save(MODULE_NAME)
        self.module = imp.load_source(MODULE_NAME, VOCABULARY_SOURCE)

    def vocabulary(self):
        """调用词汇表工厂，就像 z3c.form 渲染 sidebar_folders 字段时那样"""
        factory = getattr(self.module, VOCABULARY_NAME)()
        return factory(context=None)

    def uninstall(self):
        for name, original in self._saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def bytes_title(text):
    """AT 文件夹的 Title() 对非 ASCII 标题返回的东西：utf-8 字节串"""
    return text.encode("utf-8")


def real_site_children():
    """lims 站点门户根的真实布局（标题全是 ASCII，类型却是 str / unicode 混的）

    数据取自对 MaiLIMS 站点的只读检查：core 的文件夹返回 str，
    stockmanager / stability_studies / projects 三个 add-on 文件夹返回 unicode。
    """
    return [
        ("setup", FakeFolder("Setup", "SENAITE Setup")),
        ("clients", FakeFolder("ClientFolder", "Clients")),
        ("samples", FakeFolder("Samples", "Samples")),
        ("batches", FakeFolder("BatchFolder", "Batches")),
        ("referencesamples",
         FakeFolder("ReferenceSamplesFolder", "Reference Samples")),
        ("methods", FakeFolder("Methods", "Methods")),
        ("pricelists", FakeFolder("PricelistFolder", "Pricelists")),
        ("bika_setup", FakeFolder("BikaSetup", "Setup")),
        ("worksheets", FakeFolder("Worksheets", "Worksheets")),
        ("stockmanager", FakeFolder("StockManager", u"Stock Inventory")),
        ("stability_studies",
         FakeFolder("StabilityStudies", u"Stability Studies")),
        ("projects", FakeFolder("Projects", u"Projects")),
    ]


def chinese_children():
    """同一个站点，但有人把几个文件夹改成了中文标题

    clients / worksheets 是 AT / DX 文件夹，Title() 返回 utf-8 字节串；
    projects 是按中文请求翻译 Title() 的 add-on 文件夹，返回 unicode。
    """
    return [
        ("batches", FakeFolder("BatchFolder", "Batches")),
        ("clients", FakeFolder("ClientFolder", bytes_title(u"客户"))),
        ("methods", FakeFolder("Methods", "Methods")),
        ("projects", FakeFolder("Projects", u"项目")),
        ("stockmanager", FakeFolder("StockManager", u"Stock Inventory")),
        ("worksheets", FakeFolder("Worksheets", bytes_title(u"工作表"))),
    ]


class VocabularyTestCase(unittest.TestCase):
    """公共装配：每个用例一套干净的桩"""

    def make_vocabulary(self, children):
        modules = VocabularyModules(FakePortal(children))
        self.addCleanup(modules.uninstall)
        return modules.vocabulary()

    def values(self, vocabulary):
        return [term.value for term in vocabulary]


@unittest.skipUnless(
    sys.version_info[0] == 2,
    "str / unicode 比较时按 ASCII 解码是 Py2 的行为")
class TestPython2PremiseOfTheBug(unittest.TestCase):
    """把这个 bug 的前提钉死：没有这条前提，下面的用例就没有意义"""

    def test_non_ascii_bytes_cannot_be_compared_with_unicode(self):
        """非 ASCII 字节串与 unicode 比较会抛 UnicodeDecodeError"""
        titles = [bytes_title(u"客户"), u"Projects"]
        with self.assertRaises(UnicodeDecodeError):
            titles.sort()

    def test_ascii_bytes_can_be_compared_with_unicode(self):
        """全是 ASCII 时混着比不出错 —— 所以只有中文标题的站点才会中招"""
        titles = ["Clients", u"Projects", "Batches"]
        titles.sort()
        self.assertEqual(titles, ["Batches", "Clients", u"Projects"])


class TestTopLevelFoldersVocabulary(VocabularyTestCase):
    """TopLevelFoldersVocabulary 对混合类型标题的处理"""

    def test_byte_string_and_unicode_titles_can_be_sorted_together(self):
        """字节串中文标题与 unicode 标题混排不得抛 UnicodeDecodeError"""
        vocabulary = self.make_vocabulary(chinese_children())

        self.assertEqual(len(vocabulary), 6)

    def test_terms_are_sorted_by_unicode_title(self):
        """按 unicode 标题（码点）排序：ASCII 在前，中文按首字码点"""
        vocabulary = self.make_vocabulary(chinese_children())

        self.assertEqual(
            self.values(vocabulary),
            ["batches",        # Batches
             "methods",        # Methods
             "stockmanager",   # Stock Inventory
             "clients",        # 客户   U+5BA2
             "worksheets",     # 工作表 U+5DE5
             "projects"])      # 项目   U+9879

    def test_every_term_title_is_unicode(self):
        """term 标题统一成 unicode，字节串标题按 utf-8 解码而不是丢掉或乱码"""
        vocabulary = self.make_vocabulary(chinese_children())

        for term in vocabulary:
            self.assertIsInstance(term.title, six.text_type)
        titles = dict((term.value, term.title) for term in vocabulary)
        self.assertEqual(titles["clients"], u"客户")
        self.assertEqual(titles["worksheets"], u"工作表")
        self.assertEqual(titles["projects"], u"项目")
        self.assertEqual(titles["batches"], u"Batches")

    def test_value_and_token_are_still_the_object_id(self):
        """value / token 仍是对象 id —— sidebar_folders 里存的就是这些 id"""
        vocabulary = self.make_vocabulary(chinese_children())

        for term in vocabulary:
            self.assertEqual(term.value, term.token)
        self.assertIn("clients", self.values(vocabulary))

    def test_ascii_titles_keep_their_order(self):
        """纯 ASCII 的真实站点布局：结果和修复前一致（修复前也不报错）"""
        vocabulary = self.make_vocabulary(real_site_children())

        self.assertEqual(
            [(term.value, term.title) for term in vocabulary],
            [("batches", u"Batches"),
             ("clients", u"Clients"),
             ("methods", u"Methods"),
             ("projects", u"Projects"),
             ("referencesamples", u"Reference Samples"),
             ("setup", u"SENAITE Setup"),
             ("samples", u"Samples"),
             ("stability_studies", u"Stability Studies"),
             ("stockmanager", u"Stock Inventory"),
             ("worksheets", u"Worksheets")])

    def test_skipped_types_and_non_content_objects_are_left_out(self):
        """SKIP_NAV_TYPES 里的类型和非内容对象不进词汇表"""
        vocabulary = self.make_vocabulary(
            real_site_children() + [
                ("portal_catalog", FakeTool()),
                ("front-page", FakeFolder("Document", "Welcome")),
            ])

        values = self.values(vocabulary)
        for skipped in ("pricelists", "bika_setup", "portal_catalog",
                        "front-page"):
            self.assertNotIn(skipped, values)
        self.assertEqual(len(values), 10)

    def test_empty_title_is_an_empty_unicode(self):
        """没设标题的文件夹（DX 的 Title() 返回 ""）不会让排序出问题"""
        vocabulary = self.make_vocabulary([
            ("clients", FakeFolder("ClientFolder", bytes_title(u"客户"))),
            ("untitled", FakeFolder("Samples", "")),
            ("projects", FakeFolder("Projects", u"项目")),
        ])

        self.assertEqual(
            [(term.value, term.title) for term in vocabulary],
            [("untitled", u""), ("clients", u"客户"), ("projects", u"项目")])


def test_suite():
    from unittest import TestSuite
    from unittest import makeSuite

    suite = TestSuite()
    suite.addTest(makeSuite(TestPython2PremiseOfTheBug))
    suite.addTest(makeSuite(TestTopLevelFoldersVocabulary))
    return suite
