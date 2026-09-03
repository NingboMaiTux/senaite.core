/* Session expiry guard for AJAX requests.
 *
 * Once the session times out (see `Automatic log-off` in the setup), Plone
 * answers *any* request with a 302 to `require_login`, which ends at the login
 * form. `fetch` follows redirects transparently, so an AJAX caller gets back
 * HTTP 200 carrying the login page's HTML instead of its JSON. Every caller
 * then trips over the same thing in `response.json()`:
 *
 *     Unexpected token '<', " <!DOCTYPE "... is not valid JSON
 *
 * ... and the user is left staring at an error box on a page they are no
 * longer logged into, with no hint that they simply need to log in again.
 *
 * Wrapping the global `fetch` catches this once for every caller, instead of
 * repeating the check in each of them: the ajax edit forms here, the listing
 * in `senaite.app.listing`, spotlight, and any add-on doing the same. None of
 * them look at `response.redirected` on their own.
 */

// Paths Plone/PAS lands on when the session is gone. Matched against the end
// of the final response path, which is prefixed by the portal id.
const LOGIN_PATHS = [
  "/login",
  "/login_form",
  "/require_login",
  "/logged_out",
];

// Set once we start navigating away, so that the other in-flight requests of
// the same page do not each fire their own reload.
var redirecting = false;


/**
 * Check whether a response is the login form served after a session timeout
 *
 * @param response {Response} The response to check
 * @returns {boolean}
 */
const is_login_redirect = (response) => {
  // a response that was not redirected is the one the caller asked for
  if (!response || !response.redirected || !response.url) {
    return false;
  }
  let path = null;
  try {
    path = new URL(response.url, window.location.href).pathname;
  } catch (error) {
    return false;
  }
  return LOGIN_PATHS.some((login_path) => path.endsWith(login_path));
}


/**
 * Wrap the global `fetch` so that a session timeout sends the browser to the
 * login form instead of failing inside the caller's JSON parsing
 */
export function installSessionGuard() {
  if (!window.fetch || window.fetch.senaite_session_guard) {
    return;
  }

  const native_fetch = window.fetch.bind(window);

  const guarded_fetch = (...args) => {
    return native_fetch(...args).then((response) => {
      if (!is_login_redirect(response)) {
        return response;
      }
      console.info("*** SESSION EXPIRED -> redirecting to the login form ***");
      if (!redirecting) {
        redirecting = true;
        // Reload the current location so that Plone issues the challenge for
        // *this* page. The login form then comes back with a `came_from` that
        // returns the user here, instead of to the AJAX endpoint they hit.
        window.location.reload();
      }
      // Leave the caller's promise pending on purpose: the document is
      // navigating away, and resolving it would only let the caller render an
      // error for a page nobody is going to see.
      return new Promise(() => {});
    });
  }
  guarded_fetch.senaite_session_guard = true;

  window.fetch = guarded_fetch;
}
