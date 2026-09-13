/* PepperSign - ps-modal.js
   Gestione apertura/chiusura video modal + debug disattivato a schermo.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.modal = PS.modal || {};

    var currentVideoUrl = "";
    var debugPanel = null;
    var debugBody = null;
    var debugCounter = 0;
    var lastTimeUpdateTs = 0;

    /*
       Impostare a true solo durante i test.
       false = il pannello debug non viene creato e quindi resta invisibile sul tablet.
       I messaggi restano comunque disponibili nella console del browser.
    */
    var DEBUG_PANEL_VISIBLE = false;

    function nowStr() {
        var d = new Date();
        function pad(v) { return v < 10 ? "0" + v : "" + v; }
        return pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }

    function safeString(value) {
        if (value === null) return "null";
        if (typeof value === "undefined") return "undefined";
        try { return String(value); } catch (e) { return "[unprintable]"; }
    }

    function mediaErrorText(code) {
        if (code === 1) return "MEDIA_ERR_ABORTED";
        if (code === 2) return "MEDIA_ERR_NETWORK";
        if (code === 3) return "MEDIA_ERR_DECODE";
        if (code === 4) return "MEDIA_ERR_SRC_NOT_SUPPORTED";
        return "UNKNOWN";
    }

    function readyStateText(v) {
        if (!v) return "n/a";
        if (v.readyState === 0) return "HAVE_NOTHING";
        if (v.readyState === 1) return "HAVE_METADATA";
        if (v.readyState === 2) return "HAVE_CURRENT_DATA";
        if (v.readyState === 3) return "HAVE_FUTURE_DATA";
        if (v.readyState === 4) return "HAVE_ENOUGH_DATA";
        return safeString(v.readyState);
    }

    function networkStateText(v) {
        if (!v) return "n/a";
        if (v.networkState === 0) return "NETWORK_EMPTY";
        if (v.networkState === 1) return "NETWORK_IDLE";
        if (v.networkState === 2) return "NETWORK_LOADING";
        if (v.networkState === 3) return "NETWORK_NO_SOURCE";
        return safeString(v.networkState);
    }

    function ensureDebugPanel() {
        var header, title, btnClear, btnHide, body;

        /*
           Se DEBUG_PANEL_VISIBLE è false, il pannello non viene proprio creato.
           In questo modo sul tablet non appare più il box nero in basso.
        */
        if (!DEBUG_PANEL_VISIBLE) return;
        if (debugPanel) return;

        debugPanel = document.createElement("div");
        debugPanel.id = "ps-video-debug-panel";
        debugPanel.style.position = "fixed";
        debugPanel.style.left = "0";
        debugPanel.style.right = "0";
        debugPanel.style.bottom = "0";
        debugPanel.style.zIndex = "99999";
        debugPanel.style.background = "rgba(0,0,0,0.92)";
        debugPanel.style.color = "#00ff90";
        debugPanel.style.fontFamily = "monospace";
        debugPanel.style.fontSize = "12px";
        debugPanel.style.lineHeight = "1.35";
        debugPanel.style.borderTop = "2px solid #00ff90";
        debugPanel.style.maxHeight = "42vh";
        debugPanel.style.display = "block";

        header = document.createElement("div");
        header.style.display = "flex";
        header.style.justifyContent = "space-between";
        header.style.alignItems = "center";
        header.style.padding = "8px 10px";
        header.style.background = "rgba(20,20,20,0.98)";
        header.style.borderBottom = "1px solid rgba(0,255,144,0.35)";

        title = document.createElement("div");
        title.textContent = "DEBUG VIDEO TABLET";
        title.style.fontWeight = "bold";

        btnClear = document.createElement("button");
        btnClear.type = "button";
        btnClear.textContent = "Pulisci";
        btnClear.style.marginRight = "8px";
        btnClear.style.padding = "6px 10px";
        btnClear.style.cursor = "pointer";
        btnClear.addEventListener("click", function () {
            if (debugBody) debugBody.innerHTML = "";
            debugCounter = 0;
            debug("Log pulito");
        });

        btnHide = document.createElement("button");
        btnHide.type = "button";
        btnHide.textContent = "Nascondi";
        btnHide.style.padding = "6px 10px";
        btnHide.style.cursor = "pointer";
        btnHide.addEventListener("click", function () {
            if (!debugBody) return;
            if (debugBody.style.display === "none") {
                debugBody.style.display = "block";
                btnHide.textContent = "Nascondi";
            } else {
                debugBody.style.display = "none";
                btnHide.textContent = "Mostra";
            }
        });

        body = document.createElement("div");
        body.style.padding = "8px 10px";
        body.style.overflowY = "auto";
        body.style.maxHeight = "calc(42vh - 44px)";
        body.style.whiteSpace = "pre-wrap";
        body.style.wordBreak = "break-word";

        header.appendChild(title);

        var btnWrap = document.createElement("div");
        btnWrap.appendChild(btnClear);
        btnWrap.appendChild(btnHide);
        header.appendChild(btnWrap);

        debugPanel.appendChild(header);
        debugPanel.appendChild(body);

        debugBody = body;

        document.body.appendChild(debugPanel);
    }

    function debug(msg) {
        var line;

        /*
           Il log resta nella console del browser, ma non viene mostrato a schermo.
           Utile se in futuro ti serve ancora fare debug da PC.
        */
        try { console.log("[PS-VIDEO-DEBUG] " + msg); } catch (e) {}

        if (!DEBUG_PANEL_VISIBLE) return;

        ensureDebugPanel();

        if (!debugBody) return;

        line = document.createElement("div");
        line.textContent = "[" + nowStr() + "] " + (++debugCounter) + ". " + msg;
        line.style.padding = "2px 0";

        debugBody.appendChild(line);
        debugBody.scrollTop = debugBody.scrollHeight;
    }

    function dumpPlayerState(player, label) {
        if (!player) {
            debug(label + " | player assente");
            return;
        }

        debug(
            label +
            " | paused=" + safeString(player.paused) +
            " currentTime=" + safeString(player.currentTime) +
            " duration=" + safeString(player.duration) +
            " readyState=" + readyStateText(player) +
            " networkState=" + networkStateText(player) +
            " src=" + safeString(player.currentSrc || player.src)
        );
    }

    function resetPlayer(player) {
        if (!player) return;

        try { player.pause(); } catch (e) {}
        try { player.currentTime = 0; } catch (e2) {}

        player.removeAttribute("src");

        try { player.load(); } catch (e3) {}
    }

    function close() {
        var refs = PS.state.getRefs();
        if (!refs.videoModal || !refs.videoPlayer) return;

        debug("close() chiamata");
        refs.videoModal.style.display = "none";
        currentVideoUrl = "";
        resetPlayer(refs.videoPlayer);
        dumpPlayerState(refs.videoPlayer, "Stato dopo close");
    }

    function open(videoUrl) {
        var refs = PS.state.getRefs();
        var player;
        var playPromise;

        if (!refs.videoModal || !refs.videoPlayer) return;

        ensureDebugPanel();

        if (!videoUrl) {
            debug("ERRORE: URL video mancante");
            return;
        }

        player = refs.videoPlayer;
        currentVideoUrl = videoUrl;

        debug("========================================");
        debug("open() chiamata");
        debug("UA: " + safeString(navigator.userAgent));
        debug("isSecureContext: " + safeString(window.isSecureContext));
        debug("location.href: " + safeString(window.location.href));
        debug("videoUrl: " + safeString(videoUrl));
        debug("canPlayType(video/mp4): " + safeString(player.canPlayType("video/mp4")));
        debug("canPlayType(baseline+aac): " + safeString(player.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"')));
        debug("canPlayType(high): " + safeString(player.canPlayType('video/mp4; codecs="avc1.64000D"')));

        resetPlayer(player);
        dumpPlayerState(player, "Stato dopo reset");

        player.setAttribute("preload", "metadata");
        player.setAttribute("playsinline", "playsinline");
        player.src = videoUrl;
        refs.videoModal.style.display = "flex";

        debug("src assegnato al player");
        dumpPlayerState(player, "Stato dopo src");

        try {
            player.load();
            debug("load() eseguito");
        } catch (e) {
            debug("load() non disponibile/errore: " + safeString(e && e.message ? e.message : e));
        }

        dumpPlayerState(player, "Stato dopo load");

        try {
            playPromise = player.play();
            debug("play() invocato");

            if (playPromise && typeof playPromise.then === "function") {
                playPromise.then(function () {
                    debug("play() resolved");
                    dumpPlayerState(player, "Stato dopo play resolved");
                }).catch(function (err) {
                    debug("play() rejected: " +
                        safeString(err && err.name) + " | " +
                        safeString(err && err.message));
                    dumpPlayerState(player, "Stato dopo play rejected");
                });
            } else {
                debug("play() senza Promise");
            }
        } catch (e2) {
            debug("play() eccezione: " + safeString(e2 && e2.message ? e2.message : e2));
            dumpPlayerState(player, "Stato dopo eccezione play()");
        }
    }

    function bind() {
        var refs = PS.state.getRefs();
        var player;

        ensureDebugPanel();

        if (refs.closeModalBtn) {
            refs.closeModalBtn.addEventListener("click", close);
        }

        player = refs.videoPlayer;

        if (player) {
            player.addEventListener("loadstart", function () {
                debug("evento: loadstart");
                dumpPlayerState(player, "loadstart");
            });

            player.addEventListener("loadedmetadata", function () {
                debug("evento: loadedmetadata | size=" +
                    safeString(player.videoWidth) + "x" + safeString(player.videoHeight) +
                    " duration=" + safeString(player.duration));
                dumpPlayerState(player, "loadedmetadata");
            });

            player.addEventListener("loadeddata", function () {
                debug("evento: loadeddata");
                dumpPlayerState(player, "loadeddata");
            });

            player.addEventListener("progress", function () {
                debug("evento: progress");
            });

            player.addEventListener("canplay", function () {
                debug("evento: canplay");
                dumpPlayerState(player, "canplay");
            });

            player.addEventListener("canplaythrough", function () {
                debug("evento: canplaythrough");
                dumpPlayerState(player, "canplaythrough");
            });

            player.addEventListener("play", function () {
                debug("evento: play");
                dumpPlayerState(player, "play");
            });

            player.addEventListener("playing", function () {
                debug("evento: playing");
                dumpPlayerState(player, "playing");
            });

            player.addEventListener("pause", function () {
                debug("evento: pause");
                dumpPlayerState(player, "pause");
            });

            player.addEventListener("waiting", function () {
                debug("evento: waiting");
                dumpPlayerState(player, "waiting");
            });

            player.addEventListener("stalled", function () {
                debug("evento: stalled");
                dumpPlayerState(player, "stalled");
            });

            player.addEventListener("suspend", function () {
                debug("evento: suspend");
                dumpPlayerState(player, "suspend");
            });

            player.addEventListener("seeking", function () {
                debug("evento: seeking");
                dumpPlayerState(player, "seeking");
            });

            player.addEventListener("seeked", function () {
                debug("evento: seeked");
                dumpPlayerState(player, "seeked");
            });

            player.addEventListener("abort", function () {
                debug("evento: abort");
                dumpPlayerState(player, "abort");
            });

            player.addEventListener("emptied", function () {
                debug("evento: emptied");
                dumpPlayerState(player, "emptied");
            });

            player.addEventListener("ended", function () {
                debug("evento: ended");
                dumpPlayerState(player, "ended");
            });

            player.addEventListener("timeupdate", function () {
                var now = new Date().getTime();
                if (now - lastTimeUpdateTs > 700) {
                    lastTimeUpdateTs = now;
                    debug("evento: timeupdate | currentTime=" + safeString(player.currentTime));
                }
            });

            player.addEventListener("error", function () {
                var code = player.error ? player.error.code : null;
                var msg = player.error ? player.error.message : null;

                debug("evento: error | code=" + safeString(code) +
                    " (" + mediaErrorText(code) + ")" +
                    " | message=" + safeString(msg));
                dumpPlayerState(player, "error");
            });
        }

        window.addEventListener("click", function (e) {
            if (refs.videoModal && e.target === refs.videoModal) {
                close();
            }
        });

        debug("bind() completato");
    }

    function init() {
        ensureDebugPanel();
        debug("init() modal");
        bind();
    }

    PS.modal.init = init;
    PS.modal.open = open;
    PS.modal.close = close;
})(window);