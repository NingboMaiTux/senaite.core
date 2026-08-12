# -*- coding: utf-8 -*-

import os
import unittest


class TestFrontendUpdatePackages20260812(unittest.TestCase):
    """前端更新包回归测试"""

    def _read(self, *parts):
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", *parts))
        with open(path, "r") as handle:
            return handle.read()

    def test_analysisrequest_template_deselection_memory_is_present(self):
        """样品模板手工取消记忆逻辑应同时存在于源码和编译文件"""
        coffee = self._read(
            "browser", "static", "js", "senaite.core.analysisrequest.add.coffee")
        compiled = self._read(
            "browser", "static", "js", "senaite.core.analysisrequest.add.js")

        expected_markers = [
            "template_service_deselections",
            "remember_template_service_deselection",
            "should_select_service_from_snapshot",
            "clear_template_service_deselections"
        ]

        for marker in expected_markers:
            self.assertIn(marker, coffee)
            self.assertIn(marker, compiled)

    def test_worksheet_wide_autofill_is_limited_to_selected_service(self):
        """Worksheet 宽填充应按当前选中的服务行过滤"""
        worksheet_js = self._read(
            "browser", "static", "js", "senaite.core.worksheet.js")

        self.assertIn(
            "$(\"#wideinterims_analyses option:selected\").text().trim()",
            worksheet_js)
        self.assertIn(
            "row.querySelector(\"td.contentcell.Service, td.Service, td:first-child\")",
            worksheet_js)
        self.assertIn("if (service_text !== analysis_title)", worksheet_js)


def test_suite():
    from unittest import TestSuite
    from unittest import makeSuite

    suite = TestSuite()
    suite.addTest(makeSuite(TestFrontendUpdatePackages20260812))
    return suite
