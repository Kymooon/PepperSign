/* PepperSign - ps-pepper.js
   Integrazione con servizi Pepper: prompt vocale, start, polling stato.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.pepper = PS.pepper || {};

    function sayPrompt(text) {
        var urls = PS.config.urls || {};
        var body = PS.util.formUrlEncode({ text: text });

        return PS.util.xhrRequest("POST", urls.pepperSay, {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: body
        });
    }

    /* =========================
       ✅ ANIMATED SAY (FIXATO)
    ========================= */
    PS.pepper.animatedSay = function (text) {
        if (!text) return;

        var urls = PS.config.urls || {};
        var url = urls.pepperAnimatedSay;

        if (!url) {
            console.error("URL pepperAnimatedSay non configurato!");
            return;
        }

        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'text=' + encodeURIComponent(text)
        })
            .then(function (res) {
                if (!res.ok) {
                    throw new Error("HTTP " + res.status);
                }
                return res.json();
            })
            .then(function (data) {
                if (!data.ok) {
                    console.error("Errore Pepper:", data.error);
                }
            })
            .catch(function (err) {
                console.error("Errore chiamata animatedSay:", err);
            });
    };

    function playIntroPrompt(text, waitMs) {
        waitMs = (typeof waitMs === "number") ? waitMs : 4000;
        PS.state.setAsrStatus('Pepper: "' + text + '"');

        return sayPrompt(text).catch(function (err) {
            console.warn("pepper/say error:", err);
        }).then(function () {
            return PS.util.sleep(waitMs);
        });
    }

    function pollUntilDone(sessionId) {
        var urls = PS.config.urls || {};
        var maxMs = 45000;
        var intervalMs = 1000;
        var startedAt = Date.now();

        function step() {
            var url;

            if (Date.now() - startedAt >= maxMs) {
                PS.state.setAsrStatus("Timeout: Pepper non ha risposto in tempo.");
                return Promise.resolve();
            }

            url = urls.pepperStatus + "?sessionId=" + encodeURIComponent(sessionId);

            return PS.util.xhrRequest("GET", url).then(function (res) {
                if (!res.ok) {
                    PS.state.setAsrStatus("Errore nel polling Pepper.");
                    return;
                }

                return res.json().then(function (statusJson) {
                    if (statusJson.status === "LISTENING") {
                        PS.state.setAsrStatus("Pepper sta ascoltando... parla ora.");
                        return PS.util.sleep(intervalMs).then(step);
                    }

                    if (statusJson.status === "DONE") {
                        if (!statusJson.target) {
                            return PS.lesson.handleMissingTarget(statusJson.transcript, false);
                        }
                        return PS.lesson.confirmAndStart(statusJson.target, statusJson.transcript);
                    }

                    if (statusJson.status === "ERROR") {
                        PS.state.setAsrStatus("Errore Pepper: " + (statusJson.error || "errore sconosciuto"));
                        return;
                    }

                    return PS.util.sleep(intervalMs).then(step);
                });
            }).catch(function () {
                PS.state.setAsrStatus("Errore nel polling Pepper.");
            });
        }

        return step();
    }

    function runPepperFlow() {
        var urls = PS.config.urls || {};

        PS.state.setAsrStatus("Pepper: avvio interazione...");

        return PS.util.xhrRequest("POST", urls.pepperStart, { body: null }).then(function (startRes) {
            if (!startRes.ok) throw new Error("Errore /api/pepper/start");

            return startRes.json().then(function (startJson) {
                PS.state.setAsrStatus(startJson.prompt || "Ciao, che parola vuoi imparare oggi?");
                return pollUntilDone(startJson.sessionId);
            });
        }).catch(function (e) {
            console.error(e);
            PS.state.setAsrStatus("Errore Pepper. Controlla console.");
            alert("Errore: controlla che i servizi Pepper (start/status) siano attivi.");
        });
    }

    PS.pepper.sayPrompt = sayPrompt;
    PS.pepper.playIntroPrompt = playIntroPrompt;
    PS.pepper.pollUntilDone = pollUntilDone;
    PS.pepper.runPepperFlow = runPepperFlow;

})(window);