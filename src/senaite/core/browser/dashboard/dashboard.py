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

import collections
import datetime
import json
import os
from calendar import monthrange
from operator import itemgetter
from time import time

from AccessControl import getSecurityManager
from bika.lims import api
from bika.lims import bikaMessageFactory as _
from bika.lims import logger
from bika.lims.api import get_current_client
from bika.lims.api import get_url
from bika.lims.api import search
from bika.lims.browser import BrowserView
from bika.lims.utils import get_strings
from DateTime import DateTime
from plone.memoize import ram
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.browser.dashboard import sections as section_utils
from senaite.core.browser.dashboard.interfaces import IDashboardSection
from senaite.core.catalog import ANALYSIS_CATALOG
from senaite.core.catalog import SAMPLE_CATALOG
from senaite.core.catalog import WORKSHEET_CATALOG
from senaite.core.permissions import AddAnalysisRequest
from senaite.core.permissions import EditResults
from senaite.core.permissions import ManageBika
from senaite.core.permissions import TransitionPublishResults
from senaite.core.permissions import TransitionReceiveSample
from senaite.core.permissions import TransitionVerify
from senaite.core.permissions import ViewDashboard
from senaite.core.permissions import ViewResults
from zope.component import getUtilitiesFor

DASHBOARD_FILTER_COOKIE = "dashboard_filter_cookie"

#: core 自带的统计区块 id，顺序 = 页面上的显示顺序。
#:
#: ★ 这个元组是"装/卸 add-on 不影响原有图表"的第一条：core 的区块是
#:   **写死的常量**，不经过任何 add-on 的注册表 —— 插件区块只是追加在
#:   它们后面，注册表空了（没装任何 add-on）时页面与改造前逐字一致。
CORE_SECTION_IDS = ("analysisrequests", "analyses", "worksheets")

# Cache TTL for search counts (5 minutes)
SEARCH_CACHE_TTL = 60 * 5

# Periodicities for evolution charts
PERIODICITY_DAILY = "d"
PERIODICITY_WEEKLY = "w"
PERIODICITY_MONTHLY = "m"
PERIODICITY_QUARTERLY = "q"
PERIODICITY_BIANNUAL = "b"
PERIODICITY_YEARLY = "y"
PERIODICITY_ALL = "a"

# Days per bar segment for each periodicity
PERIODICITY_DAYS = {
    PERIODICITY_DAILY: 1,
    PERIODICITY_WEEKLY: 7,
    PERIODICITY_MONTHLY: 28,
    PERIODICITY_QUARTERLY: 84,
    PERIODICITY_BIANNUAL: 168,
    PERIODICITY_YEARLY: 336,
    PERIODICITY_ALL: 336,
}

# Status cards: (permission, title, portal_type,
#                review_state, catalog, url, icon)
STATUS_CARD_DEFS = [
    (TransitionReceiveSample, "待接收样品",
     "AnalysisRequest", "sample_due", SAMPLE_CATALOG,
     "samples?samples_review_state=sample_due",
     "fa-inbox"),
    (ViewResults, "待结果录入",
     "AnalysisRequest", "sample_received", SAMPLE_CATALOG,
     "samples?samples_review_state=sample_received",
     "fa-flask"),
    (TransitionVerify, "待复核",
     "AnalysisRequest", "to_be_verified", SAMPLE_CATALOG,
     "samples?samples_review_state=to_be_verified",
     "fa-check-circle"),
    (TransitionPublishResults, "待发布",
     "AnalysisRequest", "verified", SAMPLE_CATALOG,
     "samples?samples_review_state=verified",
     "fa-paper-plane"),
    (EditResults, "开放工作表",
     "Worksheet", "open", WORKSHEET_CATALOG,
     "worksheets?list_review_state=open",
     "fa-th-list"),
]

# Quick action links: (permission, title, url, icon)
QUICK_LINK_DEFS = [
    (AddAnalysisRequest, "样品登记",
     "samples", "fa-plus-circle"),
    (EditResults, "工作表",
     "worksheets", "fa-th-list"),
    (TransitionVerify, "结果复核",
     "samples?samples_review_state=to_be_verified",
     "fa-check-double"),
    (TransitionPublishResults, "发布报告",
     "samples?samples_review_state=verified",
     "fa-paper-plane"),
    (ManageBika, "LIMS 设置",
     "setup", "fa-cog"),
]

# State labels for evolution charts
ANALYSIS_STATES = collections.OrderedDict([
    ("registered", "已登记"),
    ("unassigned", "等待分配"),
    ("assigned", "等待结果"),
    ("to_be_verified", "待复核"),
    ("rejected", "拒收"),
    ("retracted", "已撤回"),
    ("verified", "已复核"),
    ("published", "已发布"),
])

SAMPLE_STATES = collections.OrderedDict([
    ("to_be_sampled", "待取样"),
    ("to_be_preserved", "待保存"),
    ("scheduled_sampling", "采样计划"),
    ("sample_due", "待接收"),
    ("rejected", "拒收"),
    ("invalid", "无效"),
    ("sample_received", "等待结果"),
    ("assigned", "等待结果"),
    ("to_be_verified", "待复核"),
    ("verified", "已复核"),
    ("published", "已发布"),
])

WORKSHEET_STATES = collections.OrderedDict([
    ("open", "等待结果"),
    ("to_be_verified", "待复核"),
    ("verified", "已复核"),
])

STATES_MAP = {
    "Analysis": ANALYSIS_STATES,
    "AnalysisRequest": SAMPLE_STATES,
    "Worksheet": WORKSHEET_STATES,
}

OTHER_STATE_LABEL = "其他状态"

# Colors aligned with base.scss $state-*-color variables
STATE_COLORS = {
    "to_be_sampled": "#917A4C",
    "to_be_preserved": "#C2803E",
    "scheduled_sampling": "#F38630",
    "sample_due": "#ffff8d",        # $state-sample_due-color
    "sample_received": "#a1887f",   # $state-sample_received-color
    "unassigned": "#f8f9fa",        # $state-unassigned-color
    "assigned": "#ced4da",          # $state-unassigned-active-color
    "open": "#ced4da",
    "rejected": "#6c757d",          # $state-rejected-color
    "retracted": "#ff6f00",         # $state-retracted-color
    "invalid": "#e65100",           # $state-invalid-color
    "to_be_verified": "#18ffff",    # $state-to_be_verified-color
    "verified": "#0091ea",          # $state-verified-color
    "published": "#00c853",         # $state-published-color
    "cancelled": "#000000",         # $state-cancelled-color
    "registered": "#007bff",        # $state-active-color
}


def build_colors_palette():
    """Build the full color palette with both state keys
    and translated label keys for D3 chart lookups
    """
    palette = {}
    for states in STATES_MAP.values():
        for state_id, label in states.items():
            color = STATE_COLORS.get(state_id, "#999")
            palette[state_id] = color
            palette[label] = color
    return palette


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def format_date_label(period, created):
    """Format a DateTime into a chart x-axis label
    """
    year2 = str(created.year())[2:]
    if period in (PERIODICITY_YEARLY, PERIODICITY_ALL):
        return created.year()
    if period == PERIODICITY_BIANNUAL:
        m = (((created.month() - 1) / 6) * 6) + 1
        return "%s-%s" % (year2, str(m).zfill(2))
    if period == PERIODICITY_QUARTERLY:
        m = (((created.month() - 1) / 3) * 3) + 1
        return "%s-%s" % (year2, str(m).zfill(2))
    if period == PERIODICITY_MONTHLY:
        return "%s-%s" % (year2,
                          str(created.month()).zfill(2))
    if period == PERIODICITY_WEEKLY:
        _year, _week, dow = (
            created.asdatetime().isocalendar())
        created = created - dow
        return "%s-%s-%s" % (
            str(created.year())[2:],
            str(created.month()).zfill(2),
            str(created.day()).zfill(2))
    # Daily or fallback
    return "%s-%s-%s" % (
        year2,
        str(created.month()).zfill(2),
        str(created.day()).zfill(2))


# -------------------------------------------------------
# 插件区块（IDashboardSection）—— 仪表盘的扩展点
# -------------------------------------------------------

def is_addon_installed(portal, addon):
    """``addon`` 的 GenericSetup profile 是否**已应用**（= 装在**这个**站点上）

    :param addon: 二选一 ——

        * add-on 名字（默认 profile ``<名字>:default``），例如
          ``"maitux.stability"``；
        * 或直接给 profile id（``"my.addon:plone"`` 这种带冒号的）。

    ★★ 为什么用 profile 版本、**不用** ``portal_quickinstaller.
       isProductInstalled()``（2026-10-14 线上实测踩到，卸载后区块没消失）：

       CMFQuickInstallerTool 4.0.4 的实现是"查同名**子对象**在不在"：

           def isProductInstalled(self, productname):
               ob = self._getOb(productname, None)
               return ob is not None and ob.isInstalled()

       而卸载只删**传进来的那个 id**：

           for pid in products:
               self.manage_delObjects(pid)              # 只删 pid
               portal_setup.unsetLastVersionForProfile(profile['id'])

       Add-ons 面板传的是 ``<名字>:default``，于是 ``<名字>`` 那个子对象
       **留在了 portal_quickinstaller 里**，``isProductInstalled("<名字>")``
       卸载后照样返回 True。实测：卸载后

           isProductInstalled('maitux.stability')         -> True    ← 骗人
           isProductInstalled('maitux.stability:default') -> False
           getLastVersionForProfile('…:default')          -> 'unknown' ← 真相

       所以改成读 profile 版本：装过 -> ``('1', '0', '0')`` 这样的版本元组；
       没装 / 已卸载 -> ``'unknown'``。它由 ``unsetLastVersionForProfile``
       在卸载时明确清掉，是**跟着安装/卸载一起翻面**的那个量。

    fail-closed：判不出来就当"没装"。宁可少一块（用户看得见、能查），
    也不能多一块（用户以为这个站点有该功能）。
    """
    if not addon:
        # provider 显式声明"我是全局区块"。这是它的选择，文档里有警告。
        return True

    profile_ids = [addon] if ":" in addon else ["%s:default" % addon]

    try:
        setup = getToolByName(portal, "portal_setup")
    except Exception:
        logger.exception(
            "Dashboard: portal_setup unavailable; hiding the section of '%s'",
            addon)
        return False

    for profile_id in profile_ids:
        try:
            version = setup.getLastVersionForProfile(profile_id)
        except Exception:
            logger.exception(
                "Dashboard: could not read the version of profile '%s'",
                profile_id)
            continue
        if version and version != "unknown":
            return True

    return False


def get_dashboard_section_providers(portal):
    """当前站点可用的插件区块：``[(注册名, provider), ...]``（按注册名排序）

    任何一步失败都只影响它自己：注册表取不到 -> 返回空列表（core 的三个
    区块照常渲染）；某个 provider 判定失败 -> 只丢它一个。
    排序是为了让区块顺序**稳定**（注册顺序在不同进程里不保证一致，
    不稳定的话页面每次刷新区块位置会跳）。
    """
    try:
        utilities = list(getUtilitiesFor(IDashboardSection))
    except Exception:
        logger.exception("Dashboard: could not enumerate IDashboardSection")
        return []

    providers = sorted(utilities, key=lambda item: item[0])
    available, unavailable, invalid = section_utils.partition_providers(
        providers,
        lambda provider: is_addon_installed(
            portal, getattr(provider, "addon", None)))

    for name, provider in unavailable:
        # 正常情况：该 add-on 没装在**这个**站点上。
        # 记 info（不记 warning）——排查"我装了怎么没出来"时这一行就是答案，
        # 但它不该和真正的故障长得一样。
        logger.info(
            "Dashboard: section provider '%s' hidden — add-on '%s' is not "
            "installed on this site", name, getattr(provider, "addon", None))

    for name, reason in invalid:
        logger.warning(
            "Dashboard: skipping section provider '%s': %s", name, reason)

    return available


def get_dashboard_section_provider(portal, section_id):
    """按 id 取 provider（已经是站点级筛选后的那一份）"""
    for _name, provider in get_dashboard_section_providers(portal):
        if getattr(provider, "section_id", None) == section_id:
            return provider
    return None


def get_section_permission(provider):
    """provider 声明的权限（默认 ``View Dashboard``）"""
    return section_utils.get_provider_permission(provider)


def get_static_version():
    """``dashboard.js`` / ``dashboard.css`` 的版本号（= 文件 mtime）

    ★ 为什么需要它（2026-10-14 线上实测踩到）：

      这两个是 ``++resource++`` **静态资源**，浏览器会长期缓存；而页面骨架
      （HTML）是**动态**的。一旦 HTML 里多出一个区块容器、而浏览器里的 JS
      还是旧的（不认识这个新 id），那一块就会**永远转圈** —— 现场日志里
      浏览器连一个 ``?section=stability`` 请求都没发，看起来像服务端坏了。

      给 URL 挂一个随文件变化的 ``?v=`` 后：改文件 / 重建镜像 -> URL 变 ->
      缓存自然失效，不必指望每个用户都去 Ctrl+F5。

    不缓存这个值（每次渲染一次 ``stat``），否则在不重启进程的情况下改了
    静态文件，版本号不会跟着变 —— 那正是它要解决的问题。
    """
    path = os.path.join(os.path.dirname(__file__),
                        "static", "js", "dashboard.js")
    try:
        return str(int(os.path.getmtime(path)))
    except Exception:
        # 取不到 mtime 时退回固定值：行为与改造前一致，不是错误
        logger.warning("Dashboard: could not stat %s", path)
        return "1"


# -------------------------------------------------------
# DashboardView
# -------------------------------------------------------

class DashboardView(BrowserView):
    """Main dashboard view

    Renders the page skeleton and provides data methods
    used by both the template and the JSON data endpoint.
    """
    template = ViewPageTemplateFile("templates/dashboard.pt")

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        self.dashboard_cookie = None
        self.member = None

    def __call__(self):
        # Client contacts go to their client page
        client = get_current_client()
        if client:
            return self.request.response.redirect(
                get_url(client))

        # Anonymous users go to login
        mtool = getToolByName(
            self.context, "portal_membership")
        if mtool.isAnonymousUser():
            login_url = self.portal_url + "/login"
            return self.request.response.redirect(
                login_url)

        self._setup(mtool)
        return self.template()

    def _setup(self, mtool=None):
        """Initialize view state from request

        Called by __call__ and reused by DashboardDataView.
        """
        if mtool is None:
            mtool = getToolByName(
                self.context, "portal_membership")
        self.member = mtool.getAuthenticatedMember()
        self.periodicity = self.request.get(
            "p", PERIODICITY_WEEKLY)
        self.dashboard_cookie = (
            self._read_dashboard_cookie())
        self.date_from, self.date_to = (
            self.get_date_range(self.periodicity))

    # --- Permissions ---

    def has_permission(self, permission):
        sm = getSecurityManager()
        return sm.checkPermission(
            permission, self.context)

    def can_view_statistics(self):
        return self.has_permission(ViewDashboard)

    # --- User info ---

    def get_user_fullname(self):
        user = api.get_current_user()
        return api.get_user_fullname(user)

    def get_current_date(self):
        return datetime.datetime.now().strftime(
            "%A, %d %B %Y")

    def get_current_time(self):
        return datetime.datetime.now().strftime("%H:%M")

    # --- Status cards ---

    def get_status_cards(self):
        cards = []
        for perm, title, ptype, state, cat, url, icon \
                in STATUS_CARD_DEFS:
            if not self.has_permission(perm):
                continue
            count = len(search({
                "portal_type": ptype,
                "review_state": state,
            }, cat))
            cards.append({
                "title": title,
                "count": count,
                "url": "%s/%s" % (self.portal_url, url),
                "icon": icon,
            })
        return cards

    # --- Quick links ---

    def get_quick_links(self):
        links = []
        for perm, title, url, icon in QUICK_LINK_DEFS:
            if not self.has_permission(perm):
                continue
            links.append({
                "title": title,
                "url": "%s/%s" % (self.portal_url, url),
                "icon": icon,
            })
        return links

    # --- Statistics sections ---

    def get_section_ids(self):
        """页面骨架用的区块 id 列表（**廉价**：不建数据、不查库）

        骨架只需要知道"要预留几个容器"，绝不能为此把所有区块的数据算一遍
        （core 的两张图要遍历整个 catalog）。所以这里只读 provider 的
        **声明式属性** ``section_id`` / ``permission``，
        :meth:`get_dashboard_section` 只在真正取那一块时才调用。
        """
        if not self.can_view_statistics():
            return []

        ids = list(CORE_SECTION_IDS)
        sm = getSecurityManager()
        for _name, provider in get_dashboard_section_providers(self.context):
            try:
                section_id = getattr(provider, "section_id", None)
                if not section_id or section_id in ids:
                    continue
                if not sm.checkPermission(
                        get_section_permission(provider), self.context):
                    # 没权限就不留容器：留了会一直转圈（JS 拉数据拿 403）
                    continue
                ids.append(section_id)
            except Exception:
                logger.exception(
                    "Dashboard: could not add section id of provider %r",
                    getattr(provider, "section_id", provider))
        return ids

    def get_section_ids_json(self):
        """给模板 -> dashboard.js 的 ``data-sections``（JSON 数组）

        JS 里那份写死的 ``["analysisrequests", "analyses", "worksheets"]``
        改成读它，插件区块才可能被前端取到。
        """
        return json.dumps(self.get_section_ids())

    def get_error_text(self):
        """某一块加载失败时页面上显示的那行字（dashboard.js 读它）

        刻意**不是**"静默留白"：静默失效最难查（R9）。
        """
        return _(u"Failed to load this section")

    def get_static_version(self):
        """静态资源的 ``?v=``（见模块级 :func:`get_static_version`）"""
        return get_static_version()

    def get_sections(self):
        if not self.can_view_statistics():
            return []

        sections = [
            self._build_samples_section(),
            self._build_analyses_section(),
            self._build_worksheets_section(),
        ]

        # 插件区块追加在后面。core 的三块**一个字段都没动** ——
        # 这是"装/卸 add-on 不影响原有图表"最直接的那条保证。
        for _name, provider in get_dashboard_section_providers(self.context):
            section = self._build_provider_section(provider)
            if section is not None:
                sections.append(section)
        return sections

    def _build_provider_section(self, provider):
        """取一个插件区块的数据，**失败只降级这一块**"""
        section_id = getattr(provider, "section_id", provider)
        try:
            raw = provider.get_dashboard_section()
        except Exception:
            logger.exception(
                "Dashboard: section provider '%s' failed", section_id)
            return None

        section, reason = section_utils.normalize_section(
            raw, expected_id=getattr(provider, "section_id", None))
        if section is None:
            logger.warning(
                "Dashboard: section provider '%s' returned an unusable "
                "section: %s", section_id, reason)
            return None
        if section.get("dropped_panels"):
            logger.warning(
                "Dashboard: section '%s' dropped panels: %s",
                section["id"], "; ".join(section["dropped_panels"]))
        return section

    def _build_samples_section(self):
        catalog = getToolByName(
            self.context, SAMPLE_CATALOG)
        query = {
            "portal_type": "AnalysisRequest",
            "is_active": True,
        }
        query = self._apply_cookie_filter(
            query, "analysisrequests")
        total = self._cached_count(query, catalog.id)

        panels = []
        bika_setup = self.context.bika_setup

        if bika_setup.getSamplingWorkflowEnabled():
            panels += [
                self._panel(
                    "待取样", "to_be_sampled",
                    "samples", catalog, query, total),
                self._panel(
                    "待保存", "to_be_preserved",
                    "samples", catalog, query, total),
                self._panel(
                    "采样计划",
                    "scheduled_sampling",
                    "samples", catalog, query, total),
            ]

        panels += [
            self._panel(
                "待接收", "sample_due",
                "samples", catalog, query, total),
            self._panel(
                "等待结果", "sample_received",
                "samples", catalog, query, total),
            self._panel(
                "待复核", "to_be_verified",
                "samples", catalog, query, total),
            self._panel(
                "已复核", "verified",
                "samples", catalog, query, total),
            self._panel(
                "已发布", "published",
                "samples", catalog, query, total),
        ]

        if bika_setup.getPrintingWorkflowEnabled():
            q = dict(query, getPrinted="0",
                     review_state=["published"])
            count = self._cached_count(q, catalog.id)
            panels.append({
                "type": "simple-panel",
                "description": "待打印",
                "number": count,
                "percentage": self._pct(count, total),
                "legend": self._legend(count, total),
                "link": "%s/samples?samples_getPrinted=0"
                        % self.portal_url,
            })

        panels.append(self._chart_panel(
            "样本趋势", catalog, query))

        return {
            "id": "analysisrequests",
            "title": "样本",
            "panels": panels,
        }

    def _build_analyses_section(self):
        catalog = getToolByName(
            self.context, ANALYSIS_CATALOG)
        query = {
            "portal_type": "Analysis",
            "is_active": True,
        }
        query = self._apply_cookie_filter(
            query, "analyses")
        total = self._cached_count(query, catalog.id)

        panels = [
            self._panel(
                "等待分配", "unassigned",
                None, catalog, query, total),
        ]

        # "Results pending" counts both states
        q = dict(query,
                 review_state=["unassigned", "assigned"])
        count = self._cached_count(q, catalog.id)
        panels.append({
            "type": "simple-panel",
            "description": "等待结果",
            "number": count,
            "percentage": self._pct(count, total),
            "legend": self._legend(count, total),
            "link": "#",
        })

        panels += [
            self._panel(
                "待复核", "to_be_verified",
                None, catalog, query, total),
            self._panel(
                "已复核", "verified",
                None, catalog, query, total),
        ]

        panels.append(self._chart_panel(
            "检验项目趋势", catalog, query))

        return {
            "id": "analyses",
            "title": "检验项目",
            "panels": panels,
        }

    def _build_worksheets_section(self):
        catalog = getToolByName(
            self.context, WORKSHEET_CATALOG)
        query = {"portal_type": "Worksheet"}
        query = self._apply_cookie_filter(
            query, "worksheets")
        total = self._cached_count(query, catalog.id)

        panels = [
            self._panel(
                "等待结果", "open",
                "worksheets", catalog, query, total),
            self._panel(
                "待复核", "to_be_verified",
                "worksheets", catalog, query, total),
            self._panel(
                "已复核", "verified",
                "worksheets", catalog, query, total),
        ]

        panels.append(self._chart_panel(
            "工作表趋势",
            catalog, query))

        return {
            "id": "worksheets",
            "title": "工作表",
            "panels": panels,
        }

    # --- Panel builders ---

    def _panel(self, description, review_state,
               listing_view, catalog, base_query, total):
        """Build a simple statistics panel
        """
        q = dict(base_query,
                 review_state=[review_state])
        count = self._cached_count(q, catalog.id)

        if listing_view:
            link = "%s/%s?%s_review_state=%s" % (
                self.portal_url, listing_view,
                listing_view, review_state)
        else:
            link = "#"

        return {
            "type": "simple-panel",
            "description": description,
            "number": count,
            "percentage": self._pct(count, total),
            "legend": self._legend(count, total),
            "link": link,
        }

    def _chart_panel(self, title, catalog, query):
        """Build an evolution bar chart panel
        """
        evo_data = self._evolution_data(
            catalog, query)
        return {
            "type": "bar-chart-panel",
            "name": title,
            "description": title,
            "data": json.dumps(evo_data),
            "datacolors": json.dumps(
                build_colors_palette()),
        }

    # --- Percentage / legend ---

    def _pct(self, count, total):
        if total == 0 or count == 0:
            return 0.0
        return round(
            (float(count) / float(total)) * 100, 1)

    def _legend(self, count, total):
        pct = self._pct(count, total)
        return "共 %s (%s%%)" % (
            total, pct)

    # --- Cookie filter ---

    def _read_dashboard_cookie(self):
        cookie_raw = self.request.get(
            DASHBOARD_FILTER_COOKIE, None)
        if cookie_raw is None:
            cookie_raw = {}
            self.request.response.setCookie(
                DASHBOARD_FILTER_COOKIE,
                json.dumps(cookie_raw),
                quoted=False,
                path="/")
            return cookie_raw
        return get_strings(json.loads(cookie_raw))

    def _apply_cookie_filter(self, query, section_name):
        if self.dashboard_cookie is None:
            return query
        if self.dashboard_cookie.get(
                section_name) == "mine":
            query["Creator"] = self.member.getId()
        return query

    # --- Date range ---

    def get_date_range(
            self, periodicity=PERIODICITY_WEEKLY):
        today = datetime.date.today()

        if periodicity == PERIODICITY_DAILY:
            return DateTime() - 30, DateTime() + 1

        if periodicity == PERIODICITY_MONTHLY:
            min_year = (today.year - 1
                        if today.month == 12
                        else today.year - 2)
            min_month = (1 if today.month == 12
                         else today.month)
            return (
                DateTime(min_year, min_month, 1),
                DateTime(today.year, today.month,
                         monthrange(
                             today.year,
                             today.month)[1],
                         23, 59, 59))

        if periodicity == PERIODICITY_QUARTERLY:
            m = (((today.month - 1) / 3) * 3) + 1
            years_back = 4 if today.month == 12 else 5
            return (
                DateTime(today.year - years_back, m, 1),
                DateTime(today.year, m + 2,
                         monthrange(
                             today.year, m + 2)[1],
                         23, 59, 59))

        if periodicity == PERIODICITY_BIANNUAL:
            m = (((today.month - 1) / 6) * 6) + 1
            years_back = 10 if today.month == 12 else 11
            return (
                DateTime(today.year - years_back, m, 1),
                DateTime(today.year, m + 5,
                         monthrange(
                             today.year, m + 5)[1],
                         23, 59, 59))

        if periodicity in (PERIODICITY_YEARLY,
                           PERIODICITY_ALL):
            years_back = 15 if today.month == 12 else 16
            return (
                DateTime(today.year - years_back, 1, 1),
                DateTime(today.year, 12, 31, 23, 59, 59))

        # Default: weekly (last 6 months)
        _year, _weeknum, dow = today.isocalendar()
        min_year = (today.year if today.month > 6
                    else today.year - 1)
        min_month = (today.month - 6 if today.month > 6
                     else (today.month - 6) + 12)
        return (
            DateTime(min_year, min_month, 1),
            DateTime() - dow + 7)

    # --- Cached search count ---

    def _cached_count(self, query, catalog_name):
        sorted_query = collections.OrderedDict(
            sorted(query.items()))
        query_json = json.dumps(sorted_query)
        return self._search_count(
            query_json, catalog_name)

    def _search_count_cachekey(
            func, instance, query_json, catalog_name):
        period = time() // SEARCH_CACHE_TTL
        return period, catalog_name, query_json

    @ram.cache(_search_count_cachekey)
    def _search_count(self, query_json, catalog_name):
        query = json.loads(query_json)
        return len(search(query, catalog_name))

    # --- Evolution chart data ---

    def _evolution_data(self, catalog, query):
        sorted_query = collections.OrderedDict(
            sorted(query.items()))
        query_json = json.dumps(sorted_query)
        return self._fill_evolution(
            query_json, catalog.id, self.periodicity)

    def _fill_evolution_cachekey(
            func, instance, query_json, catalog_name,
            periodicity):
        hour = time() // (60 * 60 * 2)
        return hour, catalog_name, query_json, periodicity

    @ram.cache(_fill_evolution_cachekey)
    def _fill_evolution(
            self, query_json, catalog_name, periodicity):
        """Build evolution chart data grouped by period

        Returns {"data": [...], "states": [...]}.
        Cached for 2 hours.
        """
        days = PERIODICITY_DAYS.get(periodicity, 7)
        date_from, date_to = self.get_date_range(
            periodicity)

        query = json.loads(query_json)
        query.pop("review_state", None)
        query["sort_on"] = "created"
        query["created"] = {
            "query": (date_from, date_to),
            "range": "min:max",
        }

        portal_type = query["portal_type"]
        statesmap = STATES_MAP.get(portal_type, {})
        other_label = OTHER_STATE_LABEL

        # Initialize time buckets
        buckets, bucket_index = (
            self._init_buckets(
                date_from, date_to, days,
                periodicity, statesmap, other_label))

        # Count per state per bucket
        state_totals = self._count_per_bucket(
            query, catalog_name, statesmap,
            other_label, periodicity,
            buckets, bucket_index)

        # Remove empty states
        self._remove_empty_states(
            buckets, state_totals)

        # Sort states by total count descending
        sorted_states = [
            s for s, _ in sorted(
                state_totals.items(),
                key=itemgetter(1),
                reverse=True)]

        return {"data": buckets, "states": sorted_states}

    def _init_buckets(self, date_from, date_to, days,
                      periodicity, statesmap,
                      other_label):
        """Create empty time buckets for the chart
        """
        labels = list(statesmap.values())
        labels.sort()
        labels.append(other_label)

        buckets = []
        bucket_index = {}
        curr = date_from.asdatetime()
        end = date_to.asdatetime()

        while curr < end:
            label = format_date_label(
                periodicity, DateTime(curr))
            if label not in bucket_index:
                bucket = {"date": label}
                for s in labels:
                    bucket[s] = 0
                buckets.append(bucket)
                bucket_index[label] = len(buckets) - 1
            curr += datetime.timedelta(days=days)

        return buckets, bucket_index

    def _count_per_bucket(self, query, catalog_name,
                          statesmap, other_label,
                          periodicity, buckets,
                          bucket_index):
        """Iterate brains and tally counts per bucket
        """
        state_totals = {
            v: 0 for v in list(statesmap.values())
            + [other_label]}

        for brain in search(query, catalog_name):
            state = brain.review_state
            if state not in statesmap:
                logger.warn(
                    "'%s' State for '%s' not available"
                    % (state, query["portal_type"]))
            label = statesmap.get(state, other_label)
            date_label = format_date_label(
                periodicity, brain.created)

            state_totals[label] += 1

            if date_label in bucket_index:
                idx = bucket_index[date_label]
                buckets[idx][label] = (
                    buckets[idx].get(label, 0) + 1)
            else:
                buckets.append({
                    "date": date_label, label: 1})

        return state_totals

    def _remove_empty_states(self, buckets,
                             state_totals):
        """Remove states with zero total from all buckets
        """
        empty = [k for k, v in state_totals.items()
                 if v == 0]
        for bucket in buckets:
            for state in empty:
                bucket.pop(state, None)


# -------------------------------------------------------
# DashboardDataView (JSON endpoint)
# -------------------------------------------------------

#: core 自带区块 id -> 取值方法名。
#:
#: ★ 这张表**只列 core 自己的区块**。插件区块（``IDashboardSection``）不写
#:   在这里、也永远不需要改这张表 —— 那正是"装/卸 add-on 不用动 core"的
#:   意思（见 :class:`DashboardDataView`）。
SECTION_HANDLERS = {
    "status_cards": "get_status_cards",
    "quick_links": "get_quick_links",
    "analysisrequests": "_build_samples_section",
    "analyses": "_build_analyses_section",
    "worksheets": "_build_worksheets_section",
}


class DashboardDataView(BrowserView):
    """JSON endpoint for async dashboard data loading

    Accepts a ``section`` parameter and returns the
    corresponding data as JSON.

    两种区块的取数路径：

    * **core 自带**（:data:`SECTION_HANDLERS`）—— 与改造前完全一致；
    * **插件区块** —— 按 id 现找 provider。找不到 -> 400（与"未知区块"
      的老行为一致）；provider 抛异常 -> **HTTP 200 + ``error`` 标记**，
      前端把这一块画成"加载失败"，**其余区块不受影响**（每个区块本来就是
      各自一次请求，这里只是把失败钉在这一块里）。
    """

    def __call__(self):
        self.request.response.setHeader(
            "Content-Type", "application/json")

        mtool = getToolByName(
            self.context, "portal_membership")
        if mtool.isAnonymousUser():
            self.request.response.setStatus(403)
            return json.dumps({"error": "Unauthorized"})

        section = self.request.get("section", "")
        handler_name = SECTION_HANDLERS.get(section)
        if handler_name:
            view = DashboardView(self.context, self.request)
            view._setup(mtool)
            data = getattr(view, handler_name)()
            return json.dumps(data)

        return self.render_plugin_section(section)

    def render_plugin_section(self, section):
        """插件区块的取数 + 全部失败处置"""
        provider = get_dashboard_section_provider(self.context, section)
        if provider is None:
            # 没装该 add-on 的站点也走这里 —— 注册表是进程级的，
            # 但 provider 已经过站点级筛选，所以不会"漏"给别的站点。
            self.request.response.setStatus(400)
            return json.dumps({"error": "Unknown section"})

        if not getSecurityManager().checkPermission(
                get_section_permission(provider), self.context):
            self.request.response.setStatus(403)
            return json.dumps({"error": "Unauthorized"})

        try:
            raw = provider.get_dashboard_section()
        except Exception:
            logger.exception("Dashboard: section '%s' failed", section)
            return json.dumps(self._failed_section(section))

        normalized, reason = section_utils.normalize_section(
            raw, expected_id=section)
        if normalized is None:
            logger.warning(
                "Dashboard: section '%s' is unusable: %s", section, reason)
            return json.dumps(self._failed_section(section))

        if normalized.get("dropped_panels"):
            logger.warning(
                "Dashboard: section '%s' dropped panels: %s",
                section, "; ".join(normalized["dropped_panels"]))
        return json.dumps(normalized)

    def _failed_section(self, section):
        """失败时返回的**空区块**：HTTP 仍是 200，前端显示"加载失败"

        为什么不用 500：dashboard.js 是逐个 section fetch 的，500 会走它
        的 ``catch``（只在 console 里留一行），页面上要么一直转圈要么空白。
        给一个带 ``error`` 的空区块，页面能明确说出"这块没加载出来"。
        """
        return {"id": section, "title": section, "panels": [], "error": True}
