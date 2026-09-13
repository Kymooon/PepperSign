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

    function normalizeGestureId(name) {
        return trim(name).toLowerCase().replace(/\s+/g, "_");
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
    PS.util.setText = setText;
    PS.util.create = create;
})(window);
