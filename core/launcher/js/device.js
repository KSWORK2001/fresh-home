/* FreshDevice — the single platform seam of the launcher UI.
   Everything above this file is brand-agnostic; each platform provides
   these three calls. Tizen is detected at runtime; future platforms
   (webOS ipk, Android WebView shell) register window.FreshDevice before
   app.js loads. */
(function () {
  'use strict';

  if (window.FreshDevice) return;  // platform already registered its own

  window.FreshDevice = {
    platform: (typeof tizen !== 'undefined' && tizen.application)
      ? 'tizen' : 'browser',

    /* Launch an app by ID, trying fallback IDs in order. */
    launch: function (ids, name, onFail) {
      if (typeof tizen === 'undefined' || !tizen.application) {
        return false;  // caller shows a preview toast
      }
      (function attempt(i) {
        if (i >= ids.length) { if (onFail) onFail(); return; }
        try {
          tizen.application.launch(ids[i], null, function () { attempt(i + 1); });
        } catch (e) { attempt(i + 1); }
      })(0);
      return true;
    },

    /* Open a URL — on Tizen this is the stock browser via app-control. */
    openUrl: function (url, onFail) {
      if (typeof tizen === 'undefined' || !tizen.application) return false;
      try {
        var ac = new tizen.ApplicationControl(
          'http://tizen.org/appcontrol/operation/view', url);
        tizen.application.launchAppControl(ac, 'org.tizen.browser',
          null, onFail, onFail);
      } catch (e) {
        if (onFail) onFail();
      }
      return true;
    }
  };
})();
