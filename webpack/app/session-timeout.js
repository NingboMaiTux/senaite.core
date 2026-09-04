/* Idle session timeout: renew on activity, warn, then log out.
 *
 * `Automatic log-off` in the setup says how many minutes end a session; the
 * value reaches the page as `data-auto-logoff` on <body>.
 *
 * Nothing on the client read that attribute before, and nothing renewed the
 * session ticket either -- this site does not register plone.session's own
 * refresh bundle. The ticket therefore expired a fixed number of minutes after
 * *login* rather than after the last action: users were cut off in the middle
 * of a task, with no warning, on a page that went on looking signed in until
 * some later request happened to fail.
 *
 * This module gives the setting the behaviour an idle timeout is expected to
 * have:
 *
 *   - real user activity renews the ticket, so the countdown measures idle
 *     time instead of time since login
 *   - a dialog warns before the session ends, counting down, with a button to
 *     stay signed in
 *   - reaching zero logs out and lands on the login form, saying why
 *   - all tabs of the same browser share one countdown, so working in one keeps
 *     the others alive and a logout in one takes the rest with it
 *
 * `session-guard.js` remains the backstop for when client and server disagree.
 */

import {_t} from "./i18n-wrapper.js"
import {nativeFetch} from "./session-guard.js"

// How long the countdown dialog is shown before the deadline. Clamped to half
// the timeout below, so that a very short setting still gets a usable warning.
const WARNING_SECONDS = 60;
// Renew the server-side ticket at most this often, however busy the user is.
const RENEW_INTERVAL_MS = 30 * 1000;
// How often the countdown is re-evaluated.
const TICK_MS = 1000;

// Shared between the tabs of one browser. Same-origin localStorage is what
// makes the countdown a session-wide one rather than a per-tab one.
const ACTIVITY_KEY = "senaite.session.last_activity";
const LOGOUT_KEY = "senaite.session.logged_out";
const EXPIRED_KEY = "senaite.session.expired";

// What counts as "the user is still there".
//
// `mousemove` is deliberately absent: a nudged desk or a page animating the
// cursor would keep an unattended workstation signed in forever, which is the
// one thing an automatic log-off exists to prevent. For the same reason
// outgoing AJAX is not treated as activity either -- background polling must
// not hold a session open on nobody's behalf.
const ACTIVITY_EVENTS = ["mousedown", "keydown", "wheel", "touchstart"];


/**
 * localStorage that tolerates being unavailable
 *
 * Private windows and locked-down browser profiles throw on access rather than
 * returning null, and a session timeout is not worth breaking a page over.
 */
const storage = {
  get: (key) => {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  },
  set: (key, value) => {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // no cross-tab coordination, but this tab still counts down correctly
    }
  },
  remove: (key) => {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
      // see above
    }
  },
};


class SessionTimeout {

  constructor(minutes, portal_url) {
    this.timeout_ms = minutes * 60 * 1000;
    // Warn for a minute, unless the timeout is so short that a minute would
    // mean warning from the very start.
    this.warning_ms = Math.min(WARNING_SECONDS * 1000, this.timeout_ms / 2);
    this.portal_url = portal_url;
    this.last_activity = Date.now();
    this.last_renew = 0;
    this.dialog = null;
    this.timer = null;
    this.leaving = false;

    this.on_activity = this.on_activity.bind(this);
    this.on_storage = this.on_storage.bind(this);
    this.tick = this.tick.bind(this);
  }

  start() {
    this.touch(true);
    for (const name of ACTIVITY_EVENTS) {
      document.addEventListener(name, this.on_activity, {
        passive: true, capture: true
      });
    }
    window.addEventListener("storage", this.on_storage);
    this.timer = window.setInterval(this.tick, TICK_MS);
  }

  stop() {
    for (const name of ACTIVITY_EVENTS) {
      document.removeEventListener(name, this.on_activity, {capture: true});
    }
    window.removeEventListener("storage", this.on_storage);
    if (this.timer !== null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }

  /**
   * Milliseconds left before the session ends
   */
  remaining() {
    const stored = parseInt(storage.get(ACTIVITY_KEY), 10);
    if (!isNaN(stored) && stored > this.last_activity) {
      // another tab saw the user more recently than this one
      this.last_activity = stored;
    }
    return this.timeout_ms - (Date.now() - this.last_activity);
  }

  /**
   * Record activity and, at most every RENEW_INTERVAL_MS, renew the ticket
   *
   * @param {boolean} force Renew regardless of when the last renewal was
   */
  touch(force) {
    const now = Date.now();
    this.last_activity = now;
    storage.set(ACTIVITY_KEY, String(now));
    if (force || now - this.last_renew >= RENEW_INTERVAL_MS) {
      this.last_renew = now;
      this.renew();
    }
  }

  /**
   * Push the server-side expiry back
   *
   * plone.session's own refresh view re-issues the ticket with a fresh
   * timestamp. Calling it only when the user has actually done something is
   * what turns the server's fixed expiry into an idle one.
   */
  renew() {
    const url = `${this.portal_url}/acl_users/session/refresh?type=gif`;
    nativeFetch(url, {credentials: "include", cache: "no-store"})
      .catch(() => {
        // A missed renewal is not fatal: the countdown keeps running, and
        // session-guard.js still catches an expiry this module got wrong.
      });
  }

  on_activity() {
    // While the dialog is up, only its button extends the session. A stray
    // keypress must not silently dismiss a warning nobody read -- the point of
    // warning is that the user knows the session was about to end.
    if (this.dialog) {
      return;
    }
    this.touch();
  }

  on_storage(event) {
    if (event.key === LOGOUT_KEY && event.newValue) {
      // Another tab ended the session. Follow it out rather than sitting on a
      // page whose credentials are already gone.
      this.leave();
      return;
    }
    if (event.key === ACTIVITY_KEY && this.dialog) {
      // The user is alive in another tab.
      if (this.remaining() > this.warning_ms) {
        this.hide_dialog();
      }
    }
  }

  tick() {
    if (this.leaving) {
      return;
    }
    const remaining = this.remaining();
    if (remaining <= 0) {
      this.expire();
    } else if (remaining <= this.warning_ms) {
      this.show_dialog(remaining);
    } else {
      this.hide_dialog();
    }
  }

  expire() {
    storage.set(EXPIRED_KEY, "1");
    // Wake the other tabs, which are counting down on the same clock but may
    // be a tick behind.
    storage.set(LOGOUT_KEY, String(Date.now()));
    this.leave();
  }

  /**
   * Drop the credentials and land on the login form
   */
  leave() {
    if (this.leaving) {
      return;
    }
    this.leaving = true;
    this.stop();
    this.hide_dialog();

    const login_url = `${this.portal_url}/login`;
    // Log out explicitly first. The ticket has normally expired on its own by
    // now, but if this tab counted down slightly early the login form would
    // just bounce a still-authenticated user back where they came from.
    nativeFetch(`${this.portal_url}/logout`, {
      credentials: "include", cache: "no-store"
    })
      .catch(() => null)
      .then(() => window.location.replace(login_url));
  }

  show_dialog(remaining) {
    const seconds = Math.max(0, Math.ceil(remaining / 1000));
    if (this.dialog) {
      this.dialog.counter.textContent = String(seconds);
      return;
    }
    this.dialog = build_dialog({
      seconds: seconds,
      on_stay: () => {
        this.hide_dialog();
        this.touch(true);
      },
      on_leave: () => this.expire(),
    });
    document.body.appendChild(this.dialog.root);
    this.dialog.stay.focus();
  }

  hide_dialog() {
    if (!this.dialog) {
      return;
    }
    this.dialog.root.remove();
    this.dialog = null;
  }
}


/**
 * Build the countdown dialog
 *
 * Styled inline rather than through the stylesheet: this has to render on top
 * of any page, including ones that never loaded the app's CSS, and keeping it
 * self-contained means the warning can never be the thing that fails.
 */
const build_dialog = ({seconds, on_stay, on_leave}) => {
  const root = document.createElement("div");
  root.className = "senaite-session-timeout";
  root.setAttribute("role", "alertdialog");
  root.setAttribute("aria-modal", "true");
  root.style.cssText = [
    "position:fixed", "inset:0", "z-index:2000",
    "background:rgba(0,0,0,.5)",
    "display:flex", "align-items:center", "justify-content:center",
  ].join(";");

  const card = document.createElement("div");
  card.style.cssText = [
    "background:#fff", "border-radius:.3rem", "box-shadow:0 .5rem 1rem rgba(0,0,0,.3)",
    "max-width:26rem", "margin:1rem", "padding:1.25rem",
    "font-size:.9rem", "color:#212529",
  ].join(";");

  const title = document.createElement("h5");
  title.style.cssText = "margin:0 0 .75rem;font-size:1.1rem";
  title.textContent = _t("Session about to expire");

  const text = document.createElement("p");
  text.style.cssText = "margin:0 0 1.25rem";
  const counter = document.createElement("strong");
  counter.textContent = String(seconds);
  // aria-live so that the countdown is announced, not just drawn
  counter.setAttribute("aria-live", "assertive");
  const message = _t("You will be logged out in ${seconds} seconds because of inactivity.");
  const [before, after] = message.split("${seconds}");
  text.appendChild(document.createTextNode(before));
  text.appendChild(counter);
  text.appendChild(document.createTextNode(after === undefined ? "" : after));

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;gap:.5rem;justify-content:flex-end";

  const leave = document.createElement("button");
  leave.type = "button";
  leave.className = "btn btn-sm btn-secondary";
  leave.textContent = _t("Log out now");
  leave.addEventListener("click", on_leave);

  const stay = document.createElement("button");
  stay.type = "button";
  stay.className = "btn btn-sm btn-primary";
  stay.textContent = _t("Stay signed in");
  stay.addEventListener("click", on_stay);

  actions.appendChild(leave);
  actions.appendChild(stay);
  card.appendChild(title);
  card.appendChild(text);
  card.appendChild(actions);
  root.appendChild(card);

  return {root, counter, stay};
}


/**
 * Say why the user is looking at the login form
 *
 * The reason is carried in localStorage rather than the URL: it survives the
 * logout redirect without putting session state into a link somebody could
 * share or bookmark.
 */
const render_expired_notice = () => {
  if (storage.get(EXPIRED_KEY) !== "1") {
    return;
  }
  storage.remove(EXPIRED_KEY);

  const container = document.querySelector("#global_statusmessage");
  if (!container) {
    return;
  }
  const notice = document.createElement("div");
  notice.className = "alert alert-warning";
  notice.setAttribute("role", "status");
  notice.textContent = _t(
    "Your session expired after a period of inactivity. Please log in again.");
  container.prepend(notice);
}


/**
 * Start the idle timeout for this page
 *
 * @returns {SessionTimeout|null} null when there is nothing to time out
 */
export function initSessionTimeout() {
  // Always first: the notice belongs on the login form, where no session is
  // running any more.
  render_expired_notice();

  const minutes = parseInt(document.body.dataset.autoLogoff, 10);
  // 0, absent or unparseable all mean "automatic log-off is switched off"
  if (isNaN(minutes) || minutes <= 0) {
    return null;
  }
  // Anonymous pages have no session to end.
  if (document.body.classList.contains("userrole-anonymous")) {
    return null;
  }

  const controller = new SessionTimeout(
    minutes, document.body.dataset.portalUrl || "");
  controller.start();
  return controller;
}
