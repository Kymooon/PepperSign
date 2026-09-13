/* PepperSign - ps-config.js
   Configurazione centralizzata e URL API.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.config = PS.config || {};

    function detectAppContext() {
        var path = window.location.pathname || "";
        var raw = path.split("/");
        var parts = [];
        var i;

        for (i = 0; i < raw.length; i++) {
            if (raw[i]) parts.push(raw[i]);
        }

        return parts.length > 0 ? "/" + parts[0] : "";
    }

    function detectPyBase() {
        if (window.PS_API_BASE && String(window.PS_API_BASE).replace(/^\s+|\s+$/g, "")) {
            return String(window.PS_API_BASE).replace(/^\s+|\s+$/g, "").replace(/\/$/, "");
        }
        return String(location.protocol) + "//" + String(location.hostname) + ":5000";
    }

    function init() {
        var appContext = detectAppContext();
        var pyBase = detectPyBase();

        PS.config.appContext = appContext;
        PS.config.pyBase = pyBase;

        PS.config.urls = {
            mediaList: appContext + "/api/media",
            generate: appContext + "/api/generate",
            lesson: appContext + "/api/lesson",
            pepperStart: appContext + "/api/pepper/start",
            pepperStatus: appContext + "/api/pepper/status",
            pepperSay: appContext + "/api/pepper/say",
            pepperAnimatedSay: appContext + "/api/pepper/animated-say",
            pepperAnimatable: appContext + "/api/pepper/animatable",
            pepperGesture: appContext + "/api/pepper/gesture",
            asr: appContext + "/api/asr"
        };

        return PS.config;
    }

    PS.config.init = init;
})(window);