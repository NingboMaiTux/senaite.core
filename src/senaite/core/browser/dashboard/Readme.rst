Dashboard
=========

The unified SENAITE dashboard combines a personalized greeting,
status overview, quick action links, and detailed statistics into
a single view at ``/senaite-dashboard``.


Sections
--------

The dashboard renders in three tiers:

1. **Greeting and status cards** -- personalized welcome with the
   user's full name, current date/time, and permission-gated status
   cards showing sample/worksheet counts.

2. **Quick action links** -- role-aware navigation shortcuts
   (Register Samples, Worksheets, Verify, Publish, Setup).

3. **Statistics sections** -- detailed breakdown by workflow state
   with evolution bar charts. Only visible to users with the
   ``senaite.core: View Dashboard`` permission.


Permissions
-----------

``senaite.core: View Dashboard``
    Controls visibility of the statistics sections (Samples,
    Analyses, Worksheets panels with charts). Granted by default
    to LabClerk, LabManager, and Manager via ``rolemap.xml``.

The status cards and quick action links use individual permissions
(e.g., ``TransitionReceiveSample``, ``TransitionVerify``,
``EditResults``, ``AddAnalysisRequest``, ``ManageBika``) to
determine which cards and links each user sees.


Async Loading
-------------

The dashboard page skeleton (greeting, quick links, section
headings) renders immediately without database queries. Status
cards and statistics sections load asynchronously via the
``@@senaite-dashboard-data`` JSON endpoint.

Each section is fetched independently, so slow queries in one
section do not block the others.


Caching
-------

Search counts use ``@ram.cache`` with a 5-minute TTL, shared
across all users and requests. The cache key includes the full
query and catalog name, so different filters ("mine" vs "all")
produce separate cache entries.

Evolution chart data is cached for 2 hours.


Extending the dashboard from an add-on
--------------------------------------

Add-ons add their own statistics section through
``senaite.core.browser.dashboard.interfaces.IDashboardSection`` --
a ZCML-registered **utility**, not a view override::

    <utility
        factory=".dashboardsection.MyDashboardSection"
        provides="my.addon.dashboardsection.IDashboardSection"
        name="my.addon"
        />

Use ``factory=``, not ``component=``: ``component`` registers the
class object itself, and calling ``get_dashboard_section()`` on it is
an unbound-method call under Python 2 (TypeError). ``factory``
instantiates it.

The provider declares three cheap attributes -- ``section_id``,
``addon`` and (optionally) ``permission`` -- plus one method,
``get_dashboard_section()`` that returns the section payload (see the
interface docstring for the panel contract). Charts carry their own
buckets and series, so an add-on is not forced into the
``created`` x workflow-state shape of the core charts.

Two guarantees matter here, and both are enforced in code:

**Installing or uninstalling an add-on never touches the three core
sections.** ``CORE_SECTION_IDS`` is a plain constant and each core
section has its own handler in ``SECTION_HANDLERS``; plugin sections
are only *appended*. With no add-on installed, ``get_section_ids()``
returns exactly the original three and the page is unchanged.

**A section only appears on sites where its add-on is installed.**
ZCML registration is process-wide, so "is it registered?" is not the
question to ask -- ``IDashboardSection.addon`` is resolved against the
*site's* ``portal_setup`` profile version on every request
(``<addon>:default`` installed -> a version tuple; never installed or
uninstalled -> ``unknown``), fail-closed. Uninstall the add-on and the
section disappears while the rest of the dashboard keeps working.

Do **not** use ``portal_quickinstaller.isProductInstalled(name)`` for
this: it checks for a child object of that exact name, while the
Add-ons panel uninstalls by passing ``<name>:default`` -- the
``<name>`` child survives, so it keeps reporting True after an
uninstall (hit for real on 2026-10-14).

**One broken section cannot break the others.** Every section is
fetched by its own request; a provider that raises, returns a bad
payload or declares an unsupported ``api_version`` degrades to an
empty section flagged ``error`` (HTTP 200) that the front end renders
as "failed to load". Core sections are unaffected.

Why a utility instead of overriding ``@@senaite-dashboard``: ZCML
view registrations are also process-wide, and when two add-ons
override the same view name the winner depends on the request's
``__iro__`` order -- one of them silently stops working. Utilities
are enumerable, so N add-ons never conflict.


Files
-----

``dashboard.py``
    View classes: ``DashboardView`` (main page) and
    ``DashboardDataView`` (JSON endpoint).

``interfaces.py``
    ``IDashboardSection`` -- the dashboard extension point.

``sections.py``
    Pure logic for the extension point (id validation, payload
    normalisation, provider selection). No Zope imports, so it is
    unit tested offline (``tests/test_dashboard_sections.py``).

``templates/dashboard.pt``
    Page template with async JS loading.

``static/css/dashboard.css``
    Styles for bar charts and statistics panels.

``static/js/dashboard.js``
    Async loading, DOM rendering, D3 bar charts.

``configure.zcml``
    View and resource registrations.
