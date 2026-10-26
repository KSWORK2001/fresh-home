/* Fresh Home — launcher logic
   Grid: pinned system tiles (Live TV, Web Browser) → apps by use → Get Apps.
   Get Apps screen: browse the full catalog, add/remove tiles with the d-pad,
   jump into Samsung's store. No typing required. */
(function () {
  'use strict';

  var TILE = 248, GAP = 26, PAD_X = 96, MIN_COLS = 4, MAX_COLS = 7;
  var STAGE_W = 1920;                 // design canvas; scaled to the real viewport

  var appEl = document.getElementById('app');

  /* Tizen reports a 1920x1080 UI canvas on every panel (UHD included).
     If the engine ever hands us a different size, scale the stage to fit —
     everything inside keeps its 1920-space geometry. */
  function stageScale() {
    var s = window.innerWidth / STAGE_W;
    appEl.style.transform = 'scale(' + s + ')';
  }

  var PINNED = [
    { name: 'Live TV', appId: 'org.tizen.tv-viewer', color: '#E8E8E8',
      alt: ['org.tizen.live-tv'], system: true },
    { name: 'Web Browser', appId: 'org.tizen.browser', color: '#9BB0C4',
      alt: ['3201907018784', '3202010022079'], system: true },
    { name: 'Games', appId: '__games', system: true },
  ];
  var GET_APPS = { name: 'Get Apps', appId: '__getapps', system: true };
  var STORE_IDS = ['3202102019960', 'org.tizen.apps-store', 'org.tizen.apps'];

  var GAMES = [
    { name: 'Snake', url: 'games/snake.html' },
    { name: 'Breakout', url: 'games/breakout.html' },
    { name: '2048', url: 'games/g2048.html' },
  ];
  /* Cloud & streaming open in the TV's stock browser — the only context with
     DRM video and native gamepad support (pair the controller to the TV).
     "Open URL…" covers self-hosted web clients (AnyPS5-style remote play). */
  var CLOUD = [
    { name: 'Xbox Cloud Gaming', url: 'https://www.xbox.com/play' },
    { name: 'GeForce NOW', url: 'https://play.geforcenow.com' },
    { name: 'Amazon Luna', url: 'https://luna.amazon.com' },
    { name: 'PS Remote Play', url: 'https://remoteplay.dl.playstation.net/' },
    { name: 'Steam Link', appId: '3201702011851', alt: ['3201702011851'] },
  ];
  var BRIDGE_PORT = 8590;
  var KB_ROWS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '.'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm', 'DEL', 'OK']
  ];
  var KB_ROWS_URL = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '.', '/', ':', '-'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm', 'DEL', 'OK']
  ];

  var catalog = (typeof CATALOG !== 'undefined' ? CATALOG : [])
    .filter(function (a) { return a.name !== 'Web Browser'; });
  var extra = typeof CATALOG_EXTRA !== 'undefined' ? CATALOG_EXTRA : [];

  var grid = document.getElementById('grid');
  var viewport = document.getElementById('viewport');
  var toastEl = document.getElementById('toast');
  var browseEl = document.getElementById('browse');
  var browseList = document.getElementById('browse-list');
  var browseViewport = document.getElementById('browse-viewport');
  var gamesEl = document.getElementById('games');
  var gamesList = document.getElementById('games-list');
  var gamesViewport = document.getElementById('games-viewport');
  var gameHost = document.getElementById('game-host');
  var gameFrame = document.getElementById('game-frame');
  var hostKb = document.getElementById('hostkb');
  var kbRowsEl = document.getElementById('kb-rows');
  var kbValue = document.getElementById('kb-value');

  var cols = 6, index = 0, topRow = 0, orderedList = [], tiles = [];
  var mode = 'grid';
  var browseIndex = 0, browseTop = 0, browseRows = [];
  var gamesIndex = 0, gamesTop = 0, gamesRows = [];
  var kbRow = 0, kbCol = 0, kbBuf = '', kbKeys = [];
  var ROW_H = 76;

  // ---- storage --------------------------------------------------------------

  function ls(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; }
    catch (e) { return fallback; }
  }
  function lsSet(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }
  function loadFreq() { return ls('freshhome.freq', {}); }
  function loadCustom() { return ls('freshhome.custom', []); }
  function loadHidden() { return ls('freshhome.hidden', []); }

  /* Pinned tiles stay fixed; everything else is frequency-tiered and stable. */
  function ordered() {
    var f = loadFreq();
    var pool = catalog.concat(loadCustom())
      .filter(function (a) { return loadHidden().indexOf(a.appId) < 0; });
    pool = pool.map(function (a, i) { return { app: a, order: i, count: f[a.appId] || 0 }; })
      .sort(function (x, y) { return (y.count - x.count) || (x.order - y.order); })
      .map(function (e) { return e.app; });
    return PINNED.concat(pool, [GET_APPS]);
  }

  // ---- color normalization -----------------------------------------------------

  function normColor(hex, name) {
    if (!hex) {
      var h = 0;
      for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
      return 'hsl(' + h + ', 48%, 68%)';
    }
    var m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return '#F4F5F7';
    var n = parseInt(m[1], 16), r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var l = (max + min) / 2, h = 0, s = 0, d = max - min;
    if (d > 1e-4) {
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
    }
    s = Math.min(s, 0.9);
    l = Math.min(Math.max(l, 0.62), 0.74);
    var c = (1 - Math.abs(2 * l - 1)) * s;
    var x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    var m2 = l - c / 2, hh = Math.floor(h / 60) % 6, rp, gp, bp;
    if (hh === 0)      { rp = c; gp = x; bp = 0; }
    else if (hh === 1) { rp = x; gp = c; bp = 0; }
    else if (hh === 2) { rp = 0; gp = c; bp = x; }
    else if (hh === 3) { rp = 0; gp = x; bp = c; }
    else if (hh === 4) { rp = x; gp = 0; bp = c; }
    else               { rp = c; gp = 0; bp = x; }
    return 'rgb(' + Math.round((rp + m2) * 255) + ',' +
                    Math.round((gp + m2) * 255) + ',' +
                    Math.round((bp + m2) * 255) + ')';
  }

  // ---- grid ----------------------------------------------------------------

  function computeCols() {
    cols = Math.max(MIN_COLS,
           Math.min(MAX_COLS, Math.floor((STAGE_W - 2 * PAD_X + GAP) / (TILE + GAP))));
  }

  function build(keepAppId) {
    computeCols();
    grid.style.gridTemplateColumns = 'repeat(' + cols + ', ' + TILE + 'px)';
    grid.innerHTML = '';
    tiles = [];
    orderedList = ordered();

    orderedList.forEach(function (app, i) {
      var t = document.createElement('button');
      t.type = 'button';
      t.tabIndex = -1;
      t.className = 'tile' + (app.system ? ' system' : '');
      t.setAttribute('role', 'option');
      var g = document.createElement('span');
      g.className = 'glyph';
      g.textContent = glyphFor(app);
      g.style.color = normColor(app.color, app.name);
      var l = document.createElement('span');
      l.className = 'label';
      l.textContent = app.name;
      t.appendChild(g);
      t.appendChild(l);
      t.addEventListener('click', function () { focusIndex(i); activate(); });
      grid.appendChild(t);
      tiles.push(t);
    });

    var target = 0;
    if (keepAppId) {
      for (var i = 0; i < orderedList.length; i++) {
        if (orderedList[i].appId === keepAppId) { target = i; break; }
      }
    } else {
      target = Math.min(parseInt(ls('freshhome.index', 0), 10) || 0, tiles.length - 1);
    }
    index = target;
    applyFocus(false);
  }

  function glyphFor(app) {
    if (app.appId === '__getapps') return '+';
    if (app.appId === '__games') return '\u25b8';
    if (app.appId === 'org.tizen.tv-viewer') return 'TV';
    return (app.name.trim()[0] || '?').toUpperCase();
  }

  function applyFocus(animate) {
    tiles.forEach(function (t, i) { t.classList.toggle('focused', i === index); });

    var stride = TILE + GAP;
    var row = Math.floor(index / cols);
    var visibleRows = Math.max(1, Math.floor((viewport.clientHeight + GAP) / stride));
    if (row < topRow) topRow = row;
    if (row >= topRow + visibleRows) topRow = row - visibleRows + 1;
    topRow = Math.min(topRow, Math.max(0, Math.ceil(tiles.length / cols) - visibleRows));

    if (animate === false) grid.style.transition = 'none';
    grid.style.transform = 'translateX(-50%) translateY(' + (-topRow * stride) + 'px)';
    if (animate === false) {
      void grid.offsetHeight;
      grid.style.transition = '';
    }
    lsSet('freshhome.index', index);
  }

  function focusIndex(i) {
    index = Math.max(0, Math.min(i, tiles.length - 1));
    applyFocus(true);
  }

  function move(dc, dr) {
    var r = Math.floor(index / cols), c = index % cols;
    var nr = r + dr, nc = c + dc;
    if (nr < 0 || nc < 0 || nc >= cols) return;
    var target = nr * cols + nc;
    if (target >= tiles.length) return;
    focusIndex(target);
  }

  // ---- get-apps screen --------------------------------------------------------

  function browsePool() {
    var onGrid = {};
    catalog.concat(loadCustom()).forEach(function (a) { onGrid[a.appId] = true; });
    return extra.concat(catalog)
      .filter(function (a) { return loadHidden().indexOf(a.appId) < 0 || onGrid[a.appId]; })
      .map(function (a) { return { name: a.name, appId: a.appId, color: a.color,
                                   onGrid: !!onGrid[a.appId] }; })
      .sort(function (x, y) {
        if (x.onGrid !== y.onGrid) return x.onGrid ? -1 : 1;
        return x.name.toLowerCase() < y.name.toLowerCase() ? -1 : 1;
      });
  }

  function openBrowse() {
    mode = 'browse';
    browseIndex = 0;
    browseTop = 0;
    buildBrowseList();
    browseEl.hidden = false;
  }

  function closeBrowse() {
    mode = 'grid';
    browseEl.hidden = true;
    build(ls('freshhome.lastApp', null));
  }

  function buildBrowseList() {
    var pool = browsePool();
    browseList.innerHTML = '';
    browseRows = [];

    var store = document.createElement('button');
    store.type = 'button';
    store.className = 'browse-row store';
    store.dataset.appId = '';
    store.innerHTML = '<span class="browse-name">Open Samsung App Store</span>' +
                      '<span class="browse-id">install more apps</span>';
    store.addEventListener('click', function () { launchStore(); });
    browseList.appendChild(store);
    browseRows.push(store);

    pool.forEach(function (entry) {
      var row = document.createElement('button');
      row.type = 'button';
      row.dataset.appId = entry.appId;
      row.className = 'browse-row' + (entry.onGrid ? ' added' : '');
      row.innerHTML =
        '<span class="browse-dot" style="background:' + normColor(entry.color, entry.name) + '"></span>' +
        '<span class="browse-name">' + escapeHtml(entry.name) + '</span>' +
        '<span class="browse-id">' + escapeHtml(entry.appId) + '</span>' +
        '<span class="browse-state">' + (entry.onGrid ? 'ON GRID' : 'ADD') + '</span>';
      row.addEventListener('click', function () { toggleApp(entry.appId); });
      browseList.appendChild(row);
      browseRows.push(row);
    });

    applyBrowseFocus(false);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function applyBrowseFocus(animate) {
    browseRows.forEach(function (r, i) { r.classList.toggle('focused', i === browseIndex); });
    var vh = browseViewport.clientHeight;
    var visible = Math.max(1, Math.floor(vh / ROW_H));
    if (browseIndex < browseTop) browseTop = browseIndex;
    if (browseIndex >= browseTop + visible) browseTop = browseIndex - visible + 1;
    browseTop = Math.max(0, Math.min(browseTop, browseRows.length - visible));
    if (animate === false) browseList.style.transition = 'none';
    browseList.style.transform = 'translateY(' + (-browseTop * ROW_H) + 'px)';
    if (animate === false) {
      void browseList.offsetHeight;
      browseList.style.transition = '';
    }
  }

  function browseMove(delta) {
    var next = browseIndex + delta;
    if (next < 0 || next >= browseRows.length) return;
    browseIndex = next;
    applyBrowseFocus(true);
  }

  /* Toggle a catalog/extra app on the grid. Built-ins get hidden; extras and
     re-shows go through the custom list. */
  function toggleApp(appId) {
    var hidden = loadHidden();
    var custom = loadCustom();
    var inCatalog = catalog.some(function (a) { return a.appId === appId; }) ||
                    extra.some(function (a) { return a.appId === appId; });
    var entry = null, source = null;
    catalog.concat(extra).forEach(function (a) {
      if (a.appId === appId) { entry = a; }
    });
    var onGrid = custom.some(function (a) { return a.appId === appId; }) ||
                 (hidden.indexOf(appId) < 0 && catalog.some(function (a) { return a.appId === appId; }));

    if (onGrid) {
      var hi = hidden.indexOf(appId);
      if (inCatalog && !custom.some(function (a) { return a.appId === appId; })) {
        hidden.push(appId);                        // hide a built-in
      } else if (hi >= 0) {
        hidden.splice(hi, 1);                      // un-hide
      } else {
        custom = custom.filter(function (a) { return a.appId !== appId; });
        if (!catalog.some(function (a) { return a.appId === appId; })) {
          hidden.push(appId);                      // remove a custom add
        }
      }
      lsSet('freshhome.hidden', hidden);
      lsSet('freshhome.custom', custom);
      toast('Removed ' + (entry ? entry.name : appId));
    } else {
      var h2 = loadHidden().filter(function (id) { return id !== appId; });
      lsSet('freshhome.hidden', h2);
      if (entry && !custom.some(function (a) { return a.appId === appId; })) {
        custom.push({ name: entry.name, appId: entry.appId, color: entry.color });
        lsSet('freshhome.custom', custom);
      }
      toast('Added ' + (entry ? entry.name : appId));
    }
    buildBrowseList();
    // the list re-sorts on toggle; keep focus on the app that changed
    for (var j = 0; j < browseRows.length; j++) {
      if (browseRows[j].dataset.appId === appId) { browseIndex = j; break; }
    }
    applyBrowseFocus(true);
  }

  function launchStore() {
    var ids = STORE_IDS;
    (function attempt(i) {
      if (i >= ids.length) { toast('Could not open the store'); return; }
      try {
        tizen.application.launch(ids[i], null, function () { attempt(i + 1); });
      } catch (e) { attempt(i + 1); }
    })(0);
  }

  // ---- games screen + play -------------------------------------------------

  function openGames() {
    mode = 'games';
    gamesIndex = 0;
    gamesTop = 0;
    buildGamesList();
    gamesEl.hidden = false;
    connectBridge();
  }

  function closeGames() {
    mode = 'grid';
    gamesEl.hidden = true;
    build(ls('freshhome.lastApp', null));
  }

  function buildGamesList() {
    gamesList.innerHTML = '';
    gamesRows = [];

    function row(html, cls, onOk) {
      var r = document.createElement('button');
      r.type = 'button';
      r.className = 'browse-row' + (cls ? ' ' + cls : '');
      r.innerHTML = html;
      r.addEventListener('click', onOk);
      gamesList.appendChild(r);
      gamesRows.push(r);
      return r;
    }

    GAMES.forEach(function (g) {
      row('<span class="browse-dot" style="background:#F4F5F7"></span>' +
          '<span class="browse-name">' + g.name + '</span>' +
          '<span class="browse-id">bundled · offline</span>' +
          '<span class="browse-state">PLAY</span>',
          '', function () { playGame(g.url); });
    });

    row('<span class="browse-dot" style="background:#B4B8C0"></span>' +
        '<span class="browse-name">Open URL…</span>' +
        '<span class="browse-id">any web client · e.g. a self-hosted AnyPS5</span>' +
        '<span class="browse-state">OPEN</span>',
        '', function () { openKb('url', 'https://', function (v) { openUrl(v); }); });

    CLOUD.forEach(function (c) {
      row('<span class="browse-dot" style="background:#4C9EF8"></span>' +
          '<span class="browse-name">' + c.name + '</span>' +
          '<span class="browse-id">' + (c.appId ? 'TV app' : escapeHtml(c.url.replace('https://', ''))) + '</span>' +
          '<span class="browse-state">OPEN</span>',
          '', function () {
            if (c.appId) { launchApp({ name: c.name, appId: c.appId, alt: c.alt || [] }); }
            else { openUrl(c.url); }
          });
    });

    row('<span class="browse-dot" style="background:#9BB0C4"></span>' +
        '<span class="browse-name">Controller Bridge</span>' +
        '<span class="browse-id">open http://' + bridge.host + ':' + BRIDGE_PORT + '/bridge on your Mac</span>' +
        '<span class="browse-state" id="bridge-status">' + bridgeStatusLabel() + '</span>',
        'status-' + bridge.status, function () {
          if (bridge.status === 'on') bridgeDisconnect();
          else connectBridge();
          refreshBridgeRow();
        });

    row('<span class="browse-dot" style="background:#9BB0C4"></span>' +
        '<span class="browse-name">Bridge Host</span>' +
        '<span class="browse-id">companion server address</span>' +
        '<span class="browse-state">' + escapeHtml(bridge.host) + '</span>',
        '', function () { openHostKb(); });

    applyListFocus(gamesRows, gamesIndex, gamesViewport, false);
  }

  function refreshBridgeRow() {
    var el = document.getElementById('bridge-status');
    if (el) el.textContent = bridgeStatusLabel();
    var r = gamesRows[GAMES.length];
    if (r) r.className = 'browse-row status-' + bridge.status +
      (r.classList.contains('focused') ? ' focused' : '');
  }

  function playGame(url) {
    mode = 'play';
    gameFrame.src = url;
    gameHost.hidden = false;
    gameFrame.focus();
  }

  function exitGame() {
    mode = 'games';
    gameFrame.src = 'about:blank';
    gameHost.hidden = true;
  }

  // ---- controller bridge (Mac/phone -> LAN websocket -> here) ---------------

  var bridge = {
    ws: null, status: 'off', timer: null,
    host: (function () {
      try { return localStorage.getItem('freshhome.bridge_host') || '10.0.0.157'; }
      catch (e) { return '10.0.0.157'; }
    })()
  };

  function bridgeStatusLabel() {
    return bridge.status === 'on' ? 'CONNECTED' :
           bridge.status === 'connecting' ? 'CONNECTING…' : 'OFFLINE';
  }

  function connectBridge() {
    bridgeDisconnect();
    bridge.status = 'connecting';
    refreshBridgeRow();
    try {
      var ws = new WebSocket('ws://' + bridge.host + ':' + BRIDGE_PORT + '/ws/feed');
      bridge.ws = ws;
      ws.onopen = function () { bridge.status = 'on'; refreshBridgeRow(); };
      ws.onclose = function () {
        bridge.status = 'off'; bridge.ws = null; refreshBridgeRow();
        clearTimeout(bridge.timer);
        bridge.timer = setTimeout(function () {
          if (mode === 'games' || mode === 'play') connectBridge();
        }, 5000);
      };
      ws.onmessage = function (ev) {
        if (mode !== 'play') return;
        try {
          var m = JSON.parse(ev.data);
          if (m.t === 's' && gameFrame.contentWindow) {
            gameFrame.contentWindow.postMessage({ fresh: 'input', s: m.s }, '*');
          }
        } catch (e) {}
      };
    } catch (e) {
      bridge.status = 'off';
      refreshBridgeRow();
    }
  }

  function bridgeDisconnect() {
    clearTimeout(bridge.timer);
    if (bridge.ws) {
      var w = bridge.ws;
      bridge.ws = null;
      w.onclose = null;
      try { w.close(); } catch (e) {}
    }
  }

  function openUrl(url) {
    if (typeof tizen === 'undefined' || !tizen.application) {
      toast('Preview — would open ' + url.replace('https://', ''));
      return;
    }
    try {
      var ac = new tizen.ApplicationControl(
        'http://tizen.org/appcontrol/operation/view', url);
      tizen.application.launchAppControl(ac, 'org.tizen.browser',
        null, function () { toast('Could not open the browser'); },
        function () { toast('Browser failed'); });
    } catch (e) {
      toast('Browser failed');
    }
  }

  // ---- bridge-host keyboard ---------------------------------------------------

  var kbKind = 'host', kbOnSave = null;
  var KB_LAYOUTS = { host: KB_ROWS, url: KB_ROWS_URL };

  function openKb(kind, initial, onSave) {
    mode = 'hostkb';
    kbKind = kind;
    kbOnSave = onSave || null;
    kbBuf = initial || '';
    kbRow = 0; kbCol = 0;
    kbRowsEl.innerHTML = '';
    kbKeys = [];
    KB_LAYOUTS[kind].forEach(function (keys, r) {
      var rowEl = document.createElement('div');
      rowEl.className = 'kb-row';
      var rowKeys = [];
      keys.forEach(function (k) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'kb-key' + (k.length > 1 ? ' wide' : '');
        b.textContent = k === 'DEL' ? '\u232b' : k === 'OK' ? 'OK' : k;
        b.addEventListener('click', function () { kbPress(k); });
        rowEl.appendChild(b);
        rowKeys.push(b);
      });
      kbRowsEl.appendChild(rowEl);
      kbKeys.push(rowKeys);
    });
    document.querySelector('.kb-title').textContent =
      kind === 'url' ? 'OPEN URL' : 'BRIDGE HOST';
    kbValue.textContent = kbBuf;
    hostKb.hidden = false;
    applyKbFocus();
  }

  function openHostKb() {
    openKb('host', bridge.host, function (v) {
      bridge.host = v;
      try { localStorage.setItem('freshhome.bridge_host', v); } catch (e) {}
      connectBridge();
    });
  }

  function closeHostKb(save) {
    if (save && kbBuf) {
      if (kbKind === 'host') {
        bridge.host = kbBuf;
        try { localStorage.setItem('freshhome.bridge_host', kbBuf); } catch (e) {}
        connectBridge();
      } else if (kbOnSave) {
        kbOnSave(kbBuf);
      }
    }
    hostKb.hidden = true;
    mode = 'games';
    buildGamesList();
  }

  function applyKbFocus() {
    kbKeys.forEach(function (row, r) {
      row.forEach(function (b, c) { b.classList.toggle('focused', r === kbRow && c === kbCol); });
    });
    kbValue.textContent = kbBuf;
  }

  function kbPress(k) {
    if (k === 'DEL') kbBuf = kbBuf.slice(0, -1);
    else if (k === 'OK') { closeHostKb(true); return; }
    else if (kbBuf.length < 120) kbBuf += k;
    applyKbFocus();
  }

  function kbMove(dr, dc) {
    kbCol = Math.max(0, Math.min(KB_LAYOUTS[kbKind][kbRow].length - 1, kbCol + dc));
    kbRow = Math.max(0, Math.min(KB_LAYOUTS[kbKind].length - 1, kbRow + dr));
    if (kbCol >= KB_LAYOUTS[kbKind][kbRow].length) kbCol = KB_LAYOUTS[kbKind][kbRow].length - 1;
    applyKbFocus();
  }

  // shared windowed-list focus (games screen uses the same row height/behavior)
  function applyListFocus(rows, idx, viewportEl, animate) {
    rows.forEach(function (r, i) { r.classList.toggle('focused', i === idx); });
    var vh = viewportEl.clientHeight;
    var visible = Math.max(1, Math.floor(vh / ROW_H));
    var top = parseInt(viewportEl.dataset.top || '0', 10);
    if (idx < top) top = idx;
    if (idx >= top + visible) top = idx - visible + 1;
    top = Math.max(0, Math.min(top, rows.length - visible));
    viewportEl.dataset.top = String(top);
    var listEl = viewportEl.firstElementChild;
    if (animate === false) listEl.style.transition = 'none';
    listEl.style.transform = 'translateY(' + (-top * ROW_H) + 'px)';
    if (animate === false) {
      void listEl.offsetHeight;
      listEl.style.transition = '';
    }
  }

  function gamesMove(delta) {
    var next = gamesIndex + delta;
    if (next < 0 || next >= gamesRows.length) return;
    gamesIndex = next;
    applyListFocus(gamesRows, gamesIndex, gamesViewport, true);
  }

  // ---- launching ---------------------------------------------------------------

  function activate() {
    var app = orderedList[index];
    if (!app) return;
    if (app.appId === '__getapps') { openBrowse(); return; }
    if (app.appId === '__games') { openGames(); return; }

    var f = loadFreq();
    f[app.appId] = (f[app.appId] || 0) + 1;
    lsSet('freshhome.freq', f);
    lsSet('freshhome.lastApp', app.appId);
    launchApp(app);
  }

  function launchApp(app) {
    if (typeof tizen === 'undefined' || !tizen.application) {
      toast('Preview — would open ' + app.name);
      return;
    }
    var ids = [app.appId].concat(app.alt || []);
    (function attempt(i) {
      if (i >= ids.length) { toast('Could not open ' + app.name); return; }
      try {
        tizen.application.launch(ids[i], null, function () { attempt(i + 1); });
      } catch (e) { attempt(i + 1); }
    })(0);
  }

  // ---- toast -------------------------------------------------------------------

  var toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2200);
  }

  // ---- clock -------------------------------------------------------------------

  var WD = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
  var MO = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
            'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  function tick() {
    var d = new Date(), h = d.getHours(), m = d.getMinutes();
    var ampm = h >= 12 ? 'AM' : 'PM';
    h = h % 12; if (h === 0) h = 12;
    document.getElementById('time').textContent = h + ':' + (m < 10 ? '0' : '') + m;
    document.getElementById('ampm').textContent = ampm;
    document.getElementById('date').textContent =
      WD[d.getDay()] + ' \u00b7 ' + MO[d.getMonth()] + ' ' + d.getDate();
  }

  // ---- input -------------------------------------------------------------------

  document.addEventListener('keydown', function (e) {
    var k = e.keyCode || e.which;

    if (mode === 'play') {
      // iframe normally has focus; forward to the game if it does not
      if (gameFrame.contentWindow) {
        gameFrame.contentWindow.postMessage({ fresh: 'key', k: k, down: true }, '*');
      }
      e.preventDefault();
      return;
    }
    if (mode === 'hostkb') {
      switch (k) {
        case 37: kbMove(0, -1); break;
        case 38: kbMove(-1, 0); break;
        case 39: kbMove(0, 1); break;
        case 40: kbMove(1, 0); break;
        case 13: case 32: kbPress(KB_LAYOUTS[kbKind][kbRow][kbCol]); break;
        case 8: kbPress('DEL'); break;
        case 27: case 461: case 10009: closeHostKb(false); break;
        default: return;
      }
      e.preventDefault();
      return;
    }

    if (mode === 'games') {
      switch (k) {
        case 38: gamesMove(-1); break;
        case 40: gamesMove(1); break;
        case 13: case 32: gamesRows[gamesIndex].click(); break;
        case 8: case 27: case 461: case 10009: closeGames(); break;
        default: return;
      }
      e.preventDefault();
      return;
    }

    if (mode === 'browse') {
      switch (k) {
        case 38: browseMove(-1); break;                       // Up
        case 40: browseMove(1); break;                        // Down
        case 13: case 32: browseRows[browseIndex].click(); break; // OK
        case 8: case 27: case 461: case 10009: closeBrowse(); break;
        default: return;
      }
      e.preventDefault();
      return;
    }
    switch (k) {
      case 37: move(-1, 0); break;                 // Left
      case 38: move(0, -1); break;                 // Up
      case 39: move(1, 0); break;                  // Right
      case 40: move(0, 1); break;                  // Down
      case 13: case 32: activate(); break;         // OK / Enter
      case 8: case 27: case 461: case 10009:       // Back → reset
        focusIndex(0);
        break;
      default: return;
    }
    e.preventDefault();
  });

  document.addEventListener('keyup', function (e) {
    if (mode === 'play' && gameFrame.contentWindow) {
      gameFrame.contentWindow.postMessage(
        { fresh: 'key', k: e.keyCode || e.which, down: false }, '*');
    }
  });

  // bundled games ask to exit via postMessage (Back inside the iframe)
  window.addEventListener('message', function (ev) {
    if (ev.data === 'freshhome:exit' && mode === 'play') exitGame();
  });

  // Background web apps are suspended on Tizen — resync when we come back.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && mode === 'grid') { tick(); build(ls('freshhome.lastApp', null)); }
  });

  window.addEventListener('resize', function () {
    stageScale();
    build(ls('freshhome.lastApp', null));
  });

  tick();
  setInterval(tick, 15000);
  stageScale();
  build(null);
})();
