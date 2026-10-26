/* FreshInput — unified input for bundled games.
   Merges three sources into one action state:
     - keyboard (arrow keys / WASD / Space / Z / X / Enter)
     - Gamepad API (a Bluetooth or USB controller paired directly to the TV)
     - the Mac/phone bridge (parent page forwards events via postMessage)
   Games poll FreshInput.state() each frame and FreshInput.pressed() for edges. */
(function () {
  'use strict';

  var state = { up: 0, down: 0, left: 0, right: 0, a: 0, b: 0, start: 0 };
  var prev = {};
  var sources = { keyboard: false, gamepad: false, bridge: false };

  function set(action, v, src) {
    if (state[action] === v) return;
    state[action] = v;
    sources[src] = v ? true : sources[src];
  }

  var KEYMAP = {
    38: 'up', 87: 'up',
    40: 'down', 83: 'down',
    37: 'left', 65: 'left',
    39: 'right', 68: 'right',
    32: 'a', 13: 'a', 90: 'a',
    88: 'b', 8: 'b',
    27: 'start', 80: 'start'
  };

  var downKeys = {};
  document.addEventListener('keydown', function (e) {
    var k = e.keyCode || e.which;
    if (k === 10009 && window.parent !== window) {
      // remote BACK inside a game: tell the launcher to exit
      window.parent.postMessage('freshhome:exit', '*');
      e.preventDefault();
      return;
    }
    var a = KEYMAP[k];
    if (a) { downKeys[k] = true; set(a, 1, 'keyboard'); e.preventDefault(); }
  });
  document.addEventListener('keyup', function (e) {
    var a = KEYMAP[e.keyCode || e.which];
    if (a) {
      delete downKeys[e.keyCode || e.which];
      var stillDown = Object.keys(downKeys).some(function (kk) {
        return KEYMAP[kk] === a;
      });
      if (!stillDown) set(a, 0, 'keyboard');
    }
  });

  // gamepad (controller paired directly to the TV)
  function pollGamepads() {
    var pads = navigator.getGamepads ? navigator.getGamepads() : [];
    var on = { up: 0, down: 0, left: 0, right: 0, a: 0, b: 0, start: 0 };
    for (var i = 0; i < pads.length; i++) {
      var p = pads[i];
      if (!p || !p.connected) continue;
      var lx = p.axes[0] || 0, ly = p.axes[1] || 0;
      if ((p.buttons[12] && p.buttons[12].pressed) || ly < -0.5) on.up = 1;
      if ((p.buttons[13] && p.buttons[13].pressed) || ly > 0.5) on.down = 1;
      if ((p.buttons[14] && p.buttons[14].pressed) || lx < -0.5) on.left = 1;
      if ((p.buttons[15] && p.buttons[15].pressed) || lx > 0.5) on.right = 1;
      if (p.buttons[0] && p.buttons[0].pressed) on.a = 1;    // cross / A
      if (p.buttons[1] && p.buttons[1].pressed) on.b = 1;    // circle / B
      if (p.buttons[9] && p.buttons[9].pressed) on.start = 1; // start
    }
    for (var a in on) set(a, on[a], 'gamepad');
  }

  // bridge events forwarded by the launcher (parent) via postMessage
  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d) return;
    if (d.fresh === 'input') {
      for (var a in state) {
        if (d.s && typeof d.s[a] !== 'undefined') set(a, d.s[a] ? 1 : 0, 'bridge');
      }
    } else if (d.fresh === 'key') {
      // raw key forwarded by the parent when the iframe lacks focus
      if (d.k === 10009 && window.parent !== window) {
        if (d.down) window.parent.postMessage('freshhome:exit', '*');
        return;
      }
      var ka = KEYMAP[d.k];
      if (ka) set(ka, d.down ? 1 : 0, 'bridge');
    }
  });

  function tickPrev() {
    for (var a in state) prev[a] = state[a];
  }

  (function loop() {
    pollGamepads();
    window.requestAnimationFrame(loop);
  })();

  window.FreshInput = {
    state: function () { return state; },
    pressed: function (a) { return state[a] && !prev[a]; },
    endFrame: function () { tickPrev(); },
    sources: sources
  };
})();
