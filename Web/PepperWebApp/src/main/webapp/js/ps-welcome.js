/* PepperSign - ps-welcome.js
   Popup di primo accesso con benvenuto Pepper e introduzione guidata.
*/
(function (window, document) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.welcome = PS.welcome || {};

    var STORAGE_KEY = "peppersign_welcome_seen_v1";
    var WELCOME_TEXT = "Benvenuto in PepperSign. Sono Pepper e ti accompagnerò nella scoperta del sito.";
    var WELCOME_GESTURE_ID = "ciao";
    var INTRO_START_TEXT = "Ti mostro una breve introduzione a PepperSign.";
    var INTRO_GESTURE_ID = "ciao";

    function getRefs() {
        return {
            modal: document.getElementById("welcomeModal"),
            message: document.getElementById("welcomeModalMessage"),
            yesBtn: document.getElementById("welcomeYesBtn"),
            noBtn: document.getElementById("welcomeNoBtn"),
            enterBtn: document.getElementById("welcomeEnterSiteBtn"),
            introSection: document.getElementById("welcomeIntroSection"),
            introVideo: document.getElementById("welcomeIntroVideo")
        };
    }

    function supportsLocalStorage() {
        try {
            var testKey = "__peppersign_test__";
            window.localStorage.setItem(testKey, "1");
            window.localStorage.removeItem(testKey);
            return true;
        } catch (e) {
            return false;
        }
    }

    function getCookie(name) {
        var cookies = document.cookie ? document.cookie.split(";") : [];
        var i, item, eqIndex, key, value;

        for (i = 0; i < cookies.length; i++) {
            item = cookies[i];
            eqIndex = item.indexOf("=");
            key = item.substring(0, eqIndex).replace(/^\s+|\s+$/g, "");
            value = item.substring(eqIndex + 1);

            if (key === name) {
                return value;
            }
        }

        return "";
    }

    function setCookie(name, value, days) {
        var expires = "";
        var date;

        if (days) {
            date = new Date();
            date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
            expires = "; expires=" + date.toUTCString();
        }

        document.cookie = name + "=" + value + expires + "; path=/";
    }

    function hasSeenWelcome() {
        if (supportsLocalStorage()) {
            return window.localStorage.getItem(STORAGE_KEY) === "1";
        }
        return getCookie(STORAGE_KEY) === "1";
    }

    function markWelcomeSeen() {
        if (supportsLocalStorage()) {
            window.localStorage.setItem(STORAGE_KEY, "1");
            return;
        }
        setCookie(STORAGE_KEY, "1", 365);
    }

    function showModal() {
        var refs = getRefs();
        if (!refs.modal) {
            return;
        }
        refs.modal.className = refs.modal.className + " is-open";
        refs.modal.setAttribute("aria-hidden", "false");
    }

    function hideModal() {
        var refs = getRefs();
        if (!refs.modal) {
            return;
        }
        refs.modal.className = refs.modal.className.replace(/\bis-open\b/g, "").replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
        refs.modal.setAttribute("aria-hidden", "true");

        if (refs.introVideo) {
            try {
                refs.introVideo.pause();
            } catch (e) {}
        }
    }

    function safePepperSay(text) {
        var urls = PS.config && PS.config.urls ? PS.config.urls : null;
        if (!urls || !urls.pepperSay || !PS.util || !PS.util.xhrRequest) {
            return;
        }

        PS.util.xhrRequest("POST", urls.pepperSay, {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: PS.util.formUrlEncode({ text: text })
        }).catch(function (err) {
            if (window.console && console.warn) {
                console.warn("Welcome pepper/say error:", err);
            }
        });
    }

    function safePepperGesture(gestureId) {
        var urls = PS.config && PS.config.urls ? PS.config.urls : null;
        if (!urls || !urls.pepperGesture || !PS.util || !PS.util.xhrRequest) {
            return;
        }

        PS.util.xhrRequest("POST", urls.pepperGesture, {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: PS.util.formUrlEncode({ gestureId: gestureId })
        }).catch(function (err) {
            if (window.console && console.warn) {
                console.warn("Welcome pepper/gesture error:", err);
            }
        });
    }

    function runWelcomeGreeting() {
        if (PS.state && PS.state.setAsrStatus) {
            PS.state.setAsrStatus('Pepper: "' + WELCOME_TEXT + '"');
        }

        safePepperSay(WELCOME_TEXT);

        setTimeout(function () {
            safePepperGesture(WELCOME_GESTURE_ID);
        }, 300);
    }

    function runIntroInteractionSequence() {
        if (PS.state && PS.state.setAsrStatus) {
            PS.state.setAsrStatus('Pepper: "' + INTRO_START_TEXT + '"');
        }

        safePepperSay(INTRO_START_TEXT);

        setTimeout(function () {
            safePepperGesture(INTRO_GESTURE_ID);
        }, 300);

        /*
         * TODO FUTURO:
         * Qui puoi aggiungere la vera sequenza guidata di Pepper.
         * Esempio:
         * 1. Pepper dice una frase introduttiva
         * 2. esegue un gesto
         * 3. dice un'altra frase
         * 4. esegue un altro gesto
         *
         * Puoi farlo con più chiamate a safePepperSay(...) e safePepperGesture(...)
         * scandite da setTimeout oppure da una piccola coda di step.
         */
    }

    function openIntroSection() {
        var refs = getRefs();

        if (refs.introSection) {
            refs.introSection.className = refs.introSection.className + " is-visible";
        }

        if (refs.introVideo && typeof refs.introVideo.play === "function") {
            try {
                refs.introVideo.play();
            } catch (e) {}
        }

        runIntroInteractionSequence();
    }

    function bindEvents() {
        var refs = getRefs();

        if (refs.noBtn) {
            refs.noBtn.onclick = function () {
                markWelcomeSeen();
                hideModal();
            };
        }

        if (refs.yesBtn) {
            refs.yesBtn.onclick = function () {
                markWelcomeSeen();
                openIntroSection();
            };
        }

        if (refs.enterBtn) {
            refs.enterBtn.onclick = function () {
                hideModal();
            };
        }
    }

    function init() {
        var refs = getRefs();

        if (!refs.modal) {
            return;
        }

        bindEvents();

        if (hasSeenWelcome()) {
            return;
        }

        setTimeout(function () {
            showModal();
            runWelcomeGreeting();
        }, 700);
    }

    PS.welcome.init = init;

    document.addEventListener("DOMContentLoaded", init);
})(window, document);
