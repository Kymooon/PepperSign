/* gestureTry_legacy.js (Chrome 49 / Android 5.1 / ES5)
 *
 * Modulo "Prova gesto" per PepperSign.
 *
 * Versione ultra-legacy per tablet Android 5.1 con Chrome 49.0.2623.105.
 *
 * Flusso:
 * 1. Apre overlay responsive con anteprima camera.
 * 2. Registra un breve video WebM del gesto.
 * 3. Invia il video a Tomcat proxy: /<context>/api/try.
 * 4. Riceve subito un sessionId.
 * 5. Interroga periodicamente /api/try/status/<sessionId>.
 * 6. Quando lo stato è "done", carica /api/try/skeleton/<sessionId>.mp4.
 *
 * Note Chrome 49 / Android 5.1:
 * - Usa prima navigator.webkitGetUserMedia / navigator.getUserMedia.
 * - NON usa srcObject per la preview live.
 * - Forza URL.createObjectURL(stream), più compatibile con Chrome 49.
 * - Usa constraints minimi: video:true, audio:false.
 * - Evita object-fit, border-radius e trasformazioni CSS sul video live.
 * - Mantiene ES5: niente let/const, arrow function o template string.
 *
 * API:
 *   GestureTry.init({ appContext, defaultRecordMs, pollIntervalMs })
 *   GestureTry.open({ gestureId, titleText })
 *   GestureTry.close()
 */

var GestureTry = (function () {
    "use strict";

    // ===== CONFIG =====
    var APP_CONTEXT = "";
    var API_BASE = "";

    var DEFAULT_RECORD_MS = 3000;
    var POLL_INTERVAL_MS = 2000;

    var UPLOAD_TIMEOUT_MS = 120000;
    var STATUS_TIMEOUT_MS = 20000;
    var DELETE_TIMEOUT_MS = 10000;

    var MAX_STATUS_NETWORK_RETRIES = 10;

    /*
     * Chrome 49 Android:
     * lasciare true.
     * In questa modalità non usiamo mai video.srcObject.
     */
    var FORCE_LEGACY_CAMERA_MODE = true;

    // ===== STATE =====
    var stream = null;
    var recorder = null;
    var chunks = [];
    var currentGestureId = null;
    var currentSessionId = null;

    var recordTimeoutId = null;
    var timerIntervalId = null;
    var recordStartTs = 0;
    var isRecording = false;

    // DOM
    var overlay = null;
    var panel = null;
    var header = null;
    var bodyWrap = null;
    var footer = null;

    var liveVideo = null;
    var resultVideo = null;
    var statusText = null;
    var percentText = null;
    var feedbackList = null;
    var timerText = null;

    var btnRec = null;
    var btnStop = null;
    var btnClose = null;

    // ===== HELPERS =====
    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    function setText(el, txt) {
        if (el) {
            el.textContent = txt;
        }
    }

    function makeError(message, temporary) {
        var err = new Error(message);
        err.temporary = !!temporary;
        return err;
    }

    function isTemporaryStatusError(err) {
        if (!err) {
            return false;
        }

        if (err.temporary) {
            return true;
        }

        var msg = err.message || String(err);

        return msg.indexOf("Errore di rete") >= 0 ||
            msg.indexOf("Timeout richiesta") >= 0 ||
            msg.indexOf("TEMP_STATUS_ERROR") >= 0;
    }

    function xhrRequest(method, url, options) {
        options = options || {};

        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();

            xhr.open(method, url, true);

            if (typeof options.timeoutMs === "number" && isFinite(options.timeoutMs)) {
                xhr.timeout = options.timeoutMs;
            }

            if (options.headers) {
                for (var k in options.headers) {
                    if (options.headers.hasOwnProperty(k)) {
                        try {
                            xhr.setRequestHeader(k, options.headers[k]);
                        } catch (e) {}
                    }
                }
            }

            if (options.noStore) {
                try {
                    xhr.setRequestHeader("Cache-Control", "no-store");
                } catch (e2) {}

                try {
                    xhr.setRequestHeader("Pragma", "no-cache");
                } catch (e3) {}
            }

            xhr.onload = function () {
                var status = xhr.status;
                var text = xhr.responseText;

                resolve({
                    ok: status >= 200 && status < 300,
                    status: status,
                    text: function () {
                        return Promise.resolve(text);
                    },
                    json: function () {
                        try {
                            return Promise.resolve(JSON.parse(text));
                        } catch (e) {
                            return Promise.reject(e);
                        }
                    }
                });
            };

            xhr.onerror = function () {
                reject(makeError("Errore di rete durante la richiesta a " + url, true));
            };

            xhr.ontimeout = function () {
                reject(makeError("Timeout richiesta dopo " + xhr.timeout + " ms: " + url, true));
            };

            xhr.send(options.body || null);
        });
    }

    function _detectAppContext() {
        var path = window.location.pathname || "";
        var raw = path.split("/");
        var parts = [];
        var i;

        for (i = 0; i < raw.length; i++) {
            if (raw[i]) {
                parts.push(raw[i]);
            }
        }

        return parts.length > 0 ? "/" + parts[0] : "";
    }

    function _ensureApiBase() {
        if (!APP_CONTEXT) {
            APP_CONTEXT = _detectAppContext();
        }

        API_BASE = APP_CONTEXT + "/api/try";
    }

    // ===== RESPONSIVE =====
    function _applyResponsiveLayout() {
        if (!panel) {
            return;
        }

        var vw = Math.max(320, window.innerWidth || 800);
        var vh = Math.max(320, window.innerHeight || 600);

        var widthVw = vw < 480 ? 96 : 92;
        var maxW = vw < 480 ? 360 : (vw < 900 ? 720 : 860);
        var pad = vw < 480 ? 10 : 12;
        var videoH = vh < 520 ? 180 : (vh < 700 ? 220 : 260);

        panel.style.width = widthVw + "vw";
        panel.style.maxWidth = maxW + "px";
        panel.style.maxHeight = "88vh";
        panel.style.overflow = "hidden";

        if (header) {
            header.style.padding = "10px " + pad + "px";
        }

        if (footer) {
            footer.style.padding = "10px " + pad + "px";
        }

        if (bodyWrap) {
            bodyWrap.style.padding = pad + "px " + pad + "px";
            bodyWrap.style.overflowY = "auto";
            bodyWrap.style.webkitOverflowScrolling = "touch";
            bodyWrap.style.maxHeight = (vh - 170) + "px";
        }

        if (liveVideo) {
            liveVideo.style.height = videoH + "px";
        }

        if (resultVideo) {
            resultVideo.style.height = videoH + "px";
        }
    }

    function _onResize() {
        try {
            _applyResponsiveLayout();
        } catch (e) {}
    }

    // ===== OVERLAY UI =====
    function _ensureOverlay() {
        if (overlay) {
            return;
        }

        overlay = document.createElement("div");
        overlay.id = "gestureTryOverlay";
        overlay.style.cssText =
            "position:fixed; top:0; right:0; bottom:0; left:0; z-index:99999;" +
            "display:none; background:rgba(0,0,0,0.70);" +
            "align-items:center; justify-content:center; padding:10px;";

        panel = document.createElement("div");
        panel.style.cssText =
            "width:92vw; max-width:860px; max-height:88vh;" +
            "background:#0f172a; color:#e2e8f0;" +
            "border-radius:14px; box-shadow:0 18px 50px rgba(0,0,0,0.35);" +
            "overflow:hidden;";

        header = document.createElement("div");
        header.style.cssText =
            "padding:10px 12px;" +
            "display:flex; align-items:center; justify-content:space-between;" +
            "border-bottom:1px solid rgba(255,255,255,0.08);";

        var title = document.createElement("div");
        title.id = "gestureTryTitle";
        title.style.cssText = "font-weight:800; font-size:15px;";
        title.textContent = "Prova gesto";

        btnClose = document.createElement("button");
        btnClose.type = "button";
        btnClose.textContent = "Chiudi";
        btnClose.style.cssText =
            "background:rgba(255,255,255,0.10); color:#e2e8f0;" +
            "border:1px solid rgba(255,255,255,0.18); border-radius:10px;" +
            "padding:7px 10px; cursor:pointer; font-weight:700;";
        btnClose.addEventListener("click", close);

        header.appendChild(title);
        header.appendChild(btnClose);

        bodyWrap = document.createElement("div");
        bodyWrap.style.cssText =
            "padding:12px 12px; overflow-y:auto; -webkit-overflow-scrolling:touch;";

        var body = document.createElement("div");
        body.style.cssText = "display:flex; flex-wrap:wrap; align-items:flex-start;";

        var left = document.createElement("div");
        left.style.cssText = "flex:1 1 320px; min-width:240px; padding-right:6px;";

        var liveLabel = document.createElement("div");
        liveLabel.style.cssText = "font-weight:700; opacity:0.95; margin-bottom:8px;";
        liveLabel.textContent = "Registrazione (live)";

        liveVideo = document.createElement("video");
        liveVideo.autoplay = true;
        liveVideo.muted = true;
        liveVideo.playsInline = true;

        try {
            liveVideo.setAttribute("autoplay", "");
        } catch (e0) {}

        try {
            liveVideo.setAttribute("muted", "");
        } catch (e1) {}

        try {
            liveVideo.setAttribute("playsinline", "");
        } catch (e2) {}

        try {
            liveVideo.setAttribute("webkit-playsinline", "");
        } catch (e3) {}

        /*
         * Su Chrome 49 Android evitare object-fit, border-radius, transform e filter.
         * Queste proprietà possono causare preview nera anche con camera attiva.
         */
        liveVideo.style.cssText =
            "width:100%; height:240px;" +
            "background:#020617;" +
            "border:1px solid rgba(255,255,255,0.10);" +
            "display:block;";

        left.appendChild(liveLabel);
        left.appendChild(liveVideo);

        var right = document.createElement("div");
        right.style.cssText = "flex:1 1 320px; min-width:240px; padding-left:6px;";

        var resLabel = document.createElement("div");
        resLabel.style.cssText = "font-weight:700; opacity:0.95; margin-bottom:8px;";
        resLabel.textContent = "Risultato";

        resultVideo = document.createElement("video");
        resultVideo.controls = true;
        resultVideo.playsInline = true;

        try {
            resultVideo.setAttribute("playsinline", "");
        } catch (e4) {}

        try {
            resultVideo.setAttribute("webkit-playsinline", "");
        } catch (e5) {}

        resultVideo.style.cssText =
            "width:100%; height:240px;" +
            "background:#020617;" +
            "border:1px solid rgba(255,255,255,0.10);" +
            "display:block;";

        percentText = document.createElement("div");
        percentText.style.cssText = "font-size:22px; font-weight:900; margin-top:6px;";
        percentText.textContent = "--%";

        statusText = document.createElement("div");
        statusText.style.cssText = "opacity:0.95; margin-top:6px; font-size:13px;";

        feedbackList = document.createElement("ul");
        feedbackList.style.cssText = "margin:6px 0 0 18px; padding:0; opacity:0.95; font-size:13px;";

        right.appendChild(resLabel);
        right.appendChild(resultVideo);
        right.appendChild(percentText);
        right.appendChild(statusText);
        right.appendChild(feedbackList);

        body.appendChild(left);
        body.appendChild(right);
        bodyWrap.appendChild(body);

        footer = document.createElement("div");
        footer.style.cssText =
            "padding:10px 12px; border-top:1px solid rgba(255,255,255,0.08);" +
            "display:flex; align-items:center; justify-content:space-between;" +
            "flex-wrap:wrap;";

        var leftControls = document.createElement("div");
        leftControls.style.cssText = "display:flex; align-items:center; flex-wrap:wrap; gap:8px;";

        btnRec = document.createElement("button");
        btnRec.type = "button";
        btnRec.textContent = "REC";
        btnRec.style.cssText =
            "background:#22c55e; color:#052e16; border:none; border-radius:10px;" +
            "padding:9px 12px; cursor:pointer; font-weight:900;";
        btnRec.addEventListener("click", function () {
            startRecording(DEFAULT_RECORD_MS);
        });

        btnStop = document.createElement("button");
        btnStop.type = "button";
        btnStop.textContent = "STOP";
        btnStop.disabled = true;
        btnStop.style.cssText =
            "background:rgba(255,255,255,0.10); color:#e2e8f0;" +
            "border:1px solid rgba(255,255,255,0.18); border-radius:10px;" +
            "padding:9px 12px; cursor:pointer; font-weight:900;";
        btnStop.addEventListener("click", stopRecording);

        timerText = document.createElement("div");
        timerText.style.cssText = "font-family:monospace; opacity:0.95; font-size:13px;";
        timerText.textContent = "0.0s";

        leftControls.appendChild(btnRec);
        leftControls.appendChild(btnStop);
        leftControls.appendChild(timerText);

        footer.appendChild(leftControls);

        panel.appendChild(header);
        panel.appendChild(bodyWrap);
        panel.appendChild(footer);

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        try {
            window.addEventListener("resize", _onResize);
        } catch (e6) {}

        _applyResponsiveLayout();
    }

    // ===== getUserMedia compat =====
    function _getUserMedia(constraints) {
        /*
         * Chrome 49 Android:
         * dare priorità a webkitGetUserMedia.
         */
        var legacy =
            navigator.webkitGetUserMedia ||
            navigator.getUserMedia ||
            navigator.mozGetUserMedia;

        if (legacy) {
            return new Promise(function (resolve, reject) {
                legacy.call(navigator, constraints, resolve, reject);
            });
        }

        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            return navigator.mediaDevices.getUserMedia(constraints);
        }

        return Promise.reject(new Error("getUserMedia non disponibile in questo browser/contesto."));
    }

    // ===== PREVIEW CAMERA =====
    function _startPreview() {
        if (stream) {
            return Promise.resolve();
        }

        if (!liveVideo) {
            return Promise.resolve();
        }

        liveVideo.autoplay = true;
        liveVideo.muted = true;
        liveVideo.playsInline = true;

        try {
            liveVideo.setAttribute("autoplay", "");
        } catch (e0) {}

        try {
            liveVideo.setAttribute("muted", "");
        } catch (e1) {}

        try {
            liveVideo.setAttribute("playsinline", "");
        } catch (e2) {}

        try {
            liveVideo.setAttribute("webkit-playsinline", "");
        } catch (e3) {}

        /*
         * Chrome 49 Android:
         * constraints minimi.
         */
        var constraints = {
            video: true,
            audio: false
        };

        function attachStream(s) {
            stream = s;

            try {
                liveVideo.pause();
            } catch (e0) {}

            try {
                liveVideo.srcObject = null;
            } catch (e1) {}

            try {
                liveVideo.removeAttribute("src");
            } catch (e2) {}

            try {
                liveVideo.load();
            } catch (e3) {}

            liveVideo.autoplay = true;
            liveVideo.muted = true;
            liveVideo.playsInline = true;

            try {
                liveVideo.setAttribute("autoplay", "");
            } catch (e4) {}

            try {
                liveVideo.setAttribute("muted", "");
            } catch (e5) {}

            try {
                liveVideo.setAttribute("playsinline", "");
            } catch (e6) {}

            try {
                liveVideo.setAttribute("webkit-playsinline", "");
            } catch (e7) {}

            /*
             * Punto chiave per Chrome 49:
             * non usare srcObject, ma createObjectURL(stream).
             */
            try {
                var urlCreator = window.URL || window.webkitURL;

                if (FORCE_LEGACY_CAMERA_MODE) {
                    if (urlCreator && urlCreator.createObjectURL) {
                        liveVideo.src = urlCreator.createObjectURL(stream);
                    } else {
                        throw new Error("URL.createObjectURL non disponibile");
                    }
                } else {
                    if ("srcObject" in liveVideo) {
                        liveVideo.srcObject = stream;
                    } else if (urlCreator && urlCreator.createObjectURL) {
                        liveVideo.src = urlCreator.createObjectURL(stream);
                    } else {
                        throw new Error("Nessun metodo disponibile per collegare lo stream");
                    }
                }
            } catch (e8) {
                console.log("Errore collegamento stream camera:", e8);
                setText(statusText, "Camera aperta, ma il browser non riesce a mostrare la preview.");
                throw e8;
            }

            return new Promise(function (resolve) {
                setTimeout(resolve, 700);
            }).then(function () {
                try {
                    liveVideo.play();
                } catch (e9) {
                    console.log("Errore play preview legacy:", e9);
                    setText(statusText, "Camera collegata, ma play preview fallito.");
                }
            }).then(function () {
                setTimeout(function () {
                    try {
                        console.log(
                            "[GestureTry] liveVideo readyState=" + liveVideo.readyState +
                            " videoWidth=" + liveVideo.videoWidth +
                            " videoHeight=" + liveVideo.videoHeight
                        );

                        if (liveVideo.videoWidth === 0 || liveVideo.videoHeight === 0) {
                            setText(
                                statusText,
                                "Camera autorizzata, ma Chrome 49 non sta renderizzando la preview."
                            );
                        }
                    } catch (e10) {}
                }, 1000);
            });
        }

        setText(statusText, "Apertura camera...");

        return _getUserMedia(constraints)
            .then(function (s) {
                setText(statusText, "Camera aperta. Preparazione preview...");
                return attachStream(s);
            })
            .then(function () {
                setText(statusText, "Pronto. Premi REC e poi esegui il gesto.");
            })
            .catch(function (err) {
                console.error("Errore camera:", err);
                setText(statusText, "Preview non disponibile: " + (err && err.message ? err.message : err));
                throw err;
            });
    }

    function _stopPreview() {
        if (!stream) {
            return;
        }

        try {
            var tracks = stream.getTracks();

            for (var i = 0; i < tracks.length; i++) {
                tracks[i].stop();
            }
        } catch (e) {}

        stream = null;

        if (liveVideo) {
            try {
                liveVideo.pause();
            } catch (e0) {}

            try {
                liveVideo.srcObject = null;
            } catch (e1) {}

            try {
                liveVideo.removeAttribute("src");
            } catch (e2) {}

            try {
                liveVideo.load();
            } catch (e3) {}
        }
    }

    // ===== UI RECORDING =====
    function _setRecordingUI(on) {
        isRecording = on;

        if (btnRec) {
            btnRec.disabled = on;
        }

        if (btnStop) {
            btnStop.disabled = !on;
        }
    }

    function _startTimer() {
        recordStartTs = Date.now();

        if (timerIntervalId) {
            clearInterval(timerIntervalId);
        }

        timerIntervalId = setInterval(function () {
            var secs = (Date.now() - recordStartTs) / 1000;
            setText(timerText, secs.toFixed(1) + "s");
        }, 100);
    }

    function _stopTimer() {
        if (timerIntervalId) {
            clearInterval(timerIntervalId);
        }

        timerIntervalId = null;
    }

    function _resetResultUI() {
        if (resultVideo) {
            try {
                resultVideo.pause();
            } catch (e) {}

            resultVideo.removeAttribute("src");

            try {
                resultVideo.load();
            } catch (e2) {}
        }

        setText(percentText, "--%");
        setText(statusText, "");

        if (feedbackList) {
            feedbackList.innerHTML = "";
        }
    }

    function _setFeedback(items) {
        items = items || [];

        if (!feedbackList) {
            return;
        }

        feedbackList.innerHTML = "";

        for (var i = 0; i < items.length; i++) {
            var li = document.createElement("li");
            li.textContent = items[i];
            feedbackList.appendChild(li);
        }
    }

    // ===== RECORDING =====
    function startRecording(durationMs) {
        _ensureApiBase();

        durationMs = typeof durationMs === "number" && isFinite(durationMs)
            ? durationMs
            : DEFAULT_RECORD_MS;

        return _startPreview().then(function () {
            if (!stream) {
                throw new Error("Stream camera non disponibile");
            }

            if (isRecording) {
                return;
            }

            _resetResultUI();
            chunks = [];

            if (typeof window.MediaRecorder === "undefined") {
                setText(statusText, "MediaRecorder non supportato su Chrome 49 / Android 5.1.");
                throw new Error("MediaRecorder non supportato");
            }

            var mime = "";

            try {
                if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("video/webm")) {
                    mime = "video/webm";
                } else if (
                    MediaRecorder.isTypeSupported &&
                    MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
                ) {
                    mime = "video/webm;codecs=vp8";
                }
            } catch (e) {}

            try {
                recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
            } catch (e2) {
                try {
                    recorder = new MediaRecorder(stream);
                } catch (e3) {
                    setText(statusText, "Impossibile inizializzare MediaRecorder su questo browser.");
                    throw e3;
                }
            }

            recorder.ondataavailable = function (e) {
                if (e && e.data && e.data.size > 0) {
                    chunks.push(e.data);
                }
            };

            recorder.onerror = function (e) {
                console.log("[GestureTry] recorder error:", e);
                setText(statusText, "Errore durante la registrazione video.");
            };

            recorder.onstop = function () {
                _stopTimer();
                _setRecordingUI(false);

                if (!chunks || chunks.length === 0) {
                    setText(statusText, "Nessun dato video registrato.");
                    return;
                }

                var blob = new Blob(chunks, { type: "video/webm" });
                setText(statusText, "Caricamento e preparazione...");

                _upload(blob, currentGestureId).then(function (uploadJson) {
                    currentSessionId = uploadJson && uploadJson.sessionId
                        ? uploadJson.sessionId
                        : null;

                    if (!currentSessionId) {
                        throw new Error("sessionId mancante");
                    }

                    setText(statusText, "Upload completato. Elaborazione in corso...");

                    return _poll(currentSessionId);
                }).then(function (finalJson) {
                    if (finalJson && finalJson.status === "done") {
                        var r = finalJson.result || {};
                        var percent = typeof r.percent === "number" ? r.percent : 0;

                        setText(percentText, String(percent) + "%");
                        setText(statusText, r.ok ? "Gesto riconosciuto" : "Da migliorare");
                        _setFeedback(r.feedback || []);

                        var url = API_BASE + "/skeleton/" + currentSessionId + ".mp4?t=" + Date.now();
                        resultVideo.src = url;

                        try {
                            resultVideo.load();
                        } catch (e4) {}
                    } else {
                        setText(
                            statusText,
                            "Errore: " + ((finalJson && finalJson.error) ? finalJson.error : "analisi fallita")
                        );
                    }
                }).catch(function (err) {
                    console.error(err);
                    setText(statusText, "Errore: " + (err && err.message ? err.message : err));
                });
            };

            try {
                recorder.start();
            } catch (e5) {
                setText(statusText, "Avvio registrazione fallito.");
                throw e5;
            }

            _setRecordingUI(true);
            setText(statusText, "Registrazione... esegui il gesto ora");
            _startTimer();

            if (recordTimeoutId) {
                clearTimeout(recordTimeoutId);
            }

            recordTimeoutId = setTimeout(function () {
                if (isRecording) {
                    stopRecording();
                }
            }, durationMs);
        });
    }

    function stopRecording() {
        if (!recorder || !isRecording) {
            return;
        }

        if (recordTimeoutId) {
            clearTimeout(recordTimeoutId);
        }

        recordTimeoutId = null;

        try {
            recorder.stop();
        } catch (e) {
            console.log("[GestureTry] errore stop recorder:", e);
        }
    }

    // ===== API CALLS =====
    function _upload(blob, gestureId) {
        var fd = new FormData();

        fd.append("video", blob, "try.webm");
        fd.append("gestureId", gestureId);

        return xhrRequest("POST", API_BASE, {
            body: fd,
            timeoutMs: UPLOAD_TIMEOUT_MS
        }).then(function (res) {
            if (!res.ok) {
                return res.text().then(function (txt) {
                    throw new Error("Upload fallito (" + res.status + "): " + txt);
                });
            }

            return res.json();
        });
    }

    function _poll(sessionId) {
        var networkErrors = 0;

        function step() {
            var statusUrl = API_BASE + "/status/" + sessionId + "?t=" + Date.now();

            return xhrRequest("GET", statusUrl, {
                noStore: true,
                timeoutMs: STATUS_TIMEOUT_MS
            }).then(function (res) {
                if (!res.ok) {
                    return res.text().then(function (txt) {
                        var msg = "Status fallito (" + res.status + "): " + txt;

                        if (res.status === 502 || res.status === 503 || res.status === 504) {
                            throw makeError("TEMP_STATUS_ERROR: " + msg, true);
                        }

                        throw makeError(msg, false);
                    });
                }

                return res.json();
            }).then(function (json) {
                if (!json) {
                    throw makeError("Risposta status vuota", true);
                }

                networkErrors = 0;

                if (json.status) {
                    console.log("[GestureTry] status:", json.status);
                    setText(statusText, "Elaborazione in corso... stato: " + json.status);
                }

                if (json.status === "done" || json.status === "error") {
                    return json;
                }

                return sleep(POLL_INTERVAL_MS).then(step);
            }).catch(function (err) {
                if (isTemporaryStatusError(err)) {
                    networkErrors++;

                    console.warn("[GestureTry] errore temporaneo status", networkErrors, err);

                    if (networkErrors <= MAX_STATUS_NETWORK_RETRIES) {
                        setText(
                            statusText,
                            "Elaborazione in corso... riconnessione allo status (" +
                            networkErrors + "/" + MAX_STATUS_NETWORK_RETRIES + ")"
                        );

                        return sleep(POLL_INTERVAL_MS).then(step);
                    }
                }

                throw err;
            });
        }

        return step();
    }

    function _cleanupServer() {
        if (!currentSessionId) {
            return Promise.resolve();
        }

        var sid = currentSessionId;
        currentSessionId = null;

        return xhrRequest("DELETE", API_BASE + "/" + sid, {
            timeoutMs: DELETE_TIMEOUT_MS
        }).catch(function () {});
    }

    // ===== PUBLIC API =====
    function init(opts) {
        opts = opts || {};

        if (opts.appContext) {
            APP_CONTEXT = opts.appContext;
        }

        if (typeof opts.defaultRecordMs === "number" && isFinite(opts.defaultRecordMs)) {
            DEFAULT_RECORD_MS = opts.defaultRecordMs;
        }

        if (typeof opts.pollIntervalMs === "number" && isFinite(opts.pollIntervalMs)) {
            POLL_INTERVAL_MS = opts.pollIntervalMs;
        }

        _ensureApiBase();
    }

    function open(params) {
        params = params || {};

        var gestureId = params.gestureId;
        var titleText = params.titleText;

        _ensureApiBase();
        _ensureOverlay();

        currentGestureId = gestureId || "unknown";

        var titleEl = document.getElementById("gestureTryTitle");

        if (titleEl) {
            titleEl.textContent = titleText || ("Prova gesto: " + currentGestureId);
        }

        _resetResultUI();
        setText(statusText, "Pronto. Apertura camera...");
        setText(timerText, "0.0s");

        overlay.style.display = "flex";
        _applyResponsiveLayout();

        return new Promise(function (resolve) {
            setTimeout(resolve, 100);
        }).then(_startPreview).catch(function (err) {
            console.error("Errore open GestureTry:", err);
            alert("Errore apertura schermata Prova gesto: " + (err && err.message ? err.message : err));
        });
    }

    function close() {
        if (isRecording) {
            try {
                recorder.stop();
            } catch (e) {}
        }

        _stopTimer();
        _setRecordingUI(false);

        return _cleanupServer().then(function () {
            _stopPreview();

            if (overlay) {
                overlay.style.display = "none";
            }
        });
    }

    return {
        init: init,
        open: open,
        close: close
    };
})();