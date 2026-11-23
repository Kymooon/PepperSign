/* PepperSign - ps-core.js
   Utilita' comuni ES5 / browser legacy friendly.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.util = PS.util || {};

    function trim(value) {
        return String(value == null ? "" : value).replace(/^\s+|\s+$/g, "");
    }

    function xhrRequest(method, url, options) {
        options = options || {};
        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.open(method, url, true);

            if (options.headers) {
                for (var k in options.headers) {
                    if (options.headers.hasOwnProperty(k)) {
                        xhr.setRequestHeader(k, options.headers[k]);
                    }
                }
            }

            xhr.onload = function () {
                var status = xhr.status;
                var responseText = xhr.responseText;

                resolve({
                    ok: status >= 200 && status < 300,
                    status: status,
                    text: function () {
                        return Promise.resolve(responseText);
                    },
                    json: function () {
                        try {
                            return Promise.resolve(JSON.parse(responseText));
                        } catch (e) {
                            return Promise.reject(e);
                        }
                    }
                });
            };

            xhr.onerror = function () {
                reject(new Error("Network error"));
            };

            xhr.send(options.body || null);
        });
    }

    function formUrlEncode(obj) {
        var pairs = [];
        var key;
        for (key in obj) {
            if (obj.hasOwnProperty(key)) {
                pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(obj[key]));
            }
        }
        return pairs.join("&");
    }

    function dispatchInputEvent(el) {
        var ev;
        if (!el) return;
        try {
            ev = document.createEvent("Event");
            ev.initEvent("input", true, true);
            el.dispatchEvent(ev);
        } catch (e) {
            if (typeof el.oninput === "function") el.oninput();
        }
    }

    function sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    function getAudioStream() {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            return navigator.mediaDevices.getUserMedia({ audio: true });
        }

        var legacy = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia;
        if (legacy) {
            return new Promise(function (resolve, reject) {
                legacy.call(navigator, { audio: true }, resolve, reject);
            });
        }

        return Promise.reject(new Error("getUserMedia non supportato su questo browser"));
    }

    /* Lettere accentate -> lettera semplice (mappa esplicita: String.normalize
       non c'e' sui browser piu' vecchi, come quello del tablet di Pepper). */
    var ACCENT_MAP = {
        "a": /[\u00e0\u00e1\u00e2\u00e3\u00e4\u00e5]/g,
        "e": /[\u00e8\u00e9\u00ea\u00eb]/g,
        "i": /[\u00ec\u00ed\u00ee\u00ef]/g,
        "o": /[\u00f2\u00f3\u00f4\u00f5\u00f6]/g,
        "u": /[\u00f9\u00fa\u00fb\u00fc]/g,
        "c": /\u00e7/g,
        "n": /\u00f1/g
    };

    function foldAccents(text) {
        var out = String(text || "").toLowerCase();
        var letter;
        for (letter in ACCENT_MAP) {
            if (ACCENT_MAP.hasOwnProperty(letter)) {
                out = out.replace(ACCENT_MAP[letter], letter);
            }
        }
        return out.replace(/[\u0300-\u036f]/g, "");
    }

    /* Id del gesto: stessa regola di GestureIds.java, utils.normalize_gesture_id
       (Controll) e _safe_slug (Process). Es. "Universit\u00e0" -> "universita". */
    function normalizeGestureId(name) {
        return foldAccents(trim(name)).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    }

    function setText(el, text) {
        if (el) el.textContent = text;
    }

    function create(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (typeof text !== "undefined" && text !== null) el.textContent = text;
        return el;
    }

    PS.util.trim = trim;
    PS.util.xhrRequest = xhrRequest;
    PS.util.formUrlEncode = formUrlEncode;
    PS.util.dispatchInputEvent = dispatchInputEvent;
    PS.util.sleep = sleep;
    PS.util.getAudioStream = getAudioStream;
    PS.util.normalizeGestureId = normalizeGestureId;
    PS.util.foldAccents = foldAccents;
    PS.util.setText = setText;
    PS.util.create = create;
})(window);
