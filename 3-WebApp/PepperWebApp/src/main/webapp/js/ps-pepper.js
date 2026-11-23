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
       Esito dei comandi
       Ogni comando accodato ha un id; /api/pepper/command?id=... ne restituisce lo stato:
       queued -> sent -> done | failed, oppure expired / unconfirmed.
    ========================= */

    var COMMAND_MESSAGES = {
        done: "Eseguito",
        failed: "Errore del robot",
        expired: "Il robot non ha preso il comando in tempo",
        unconfirmed: "Nessuna conferma dal robot",
        offline: "Robot non collegato",
        network: "Errore di rete",
        timeout: "Nessuna risposta dal robot"
    };

    /* Legge la risposta di /say, /animated-say, /gesture: {ok, id} oppure {ok:false, robotOnline, error}. */
    function readQueued(res) {
        return res.json().then(function (data) {
            data = data || {};
            if (res.ok && data.ok && data.id) {
                return { ok: true, id: data.id };
            }
            if (data.robotOnline === false) {
                return { ok: false, status: "offline", message: data.error || COMMAND_MESSAGES.offline };
            }
            return { ok: false, status: "failed", message: data.error || ("HTTP " + res.status) };
        }, function () {
            return { ok: false, status: "failed", message: "HTTP " + res.status };
        });
    }

    /*
     * Attende la fine di un comando. Risolve sempre con
     * {ok, status, message}: ok = true solo se il robot lo ha eseguito.
     */
    function waitForCommand(commandId, options) {
        var urls = PS.config.urls || {};
        var timeoutMs = (options && options.timeoutMs) || 70000;
        var intervalMs = (options && options.intervalMs) || 500;
        var startedAt = Date.now();

        function step() {
            if (Date.now() - startedAt > timeoutMs) {
                return Promise.resolve({ ok: false, status: "timeout", message: COMMAND_MESSAGES.timeout });
            }
            return PS.util.xhrRequest("GET", urls.pepperCommand + "?id=" + encodeURIComponent(commandId))
                .then(function (res) {
                    return res.json().then(function (data) {
                        if (!res.ok || !data || !data.ok) {
                            return { ok: false, status: "failed", message: (data && data.error) || ("HTTP " + res.status) };
                        }
                        if (data["final"]) {
                            return {
                                ok: data.status === "done",
                                status: data.status,
                                message: data.message || COMMAND_MESSAGES[data.status] || data.status
                            };
                        }
                        return PS.util.sleep(intervalMs).then(step);
                    }, function () {
                        // risposta non JSON (es. pagina di errore di Tomcat o di un proxy)
                        return { ok: false, status: "failed", message: "Risposta non valida dal server (HTTP " + res.status + ")" };
                    });
                }, function () {
                    return PS.util.sleep(intervalMs * 2).then(step);
                });
        }

        return step();
    }

    /* Invia un comando (POST form) e ne attende l'esito: risolve con {ok, status, message}. */
    function sendAndWait(url, form, options) {
        return PS.util.xhrRequest("POST", url, {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: PS.util.formUrlEncode(form)
        }).then(readQueued, function () {
            return { ok: false, status: "network", message: COMMAND_MESSAGES.network };
        }).then(function (queued) {
            if (!queued.ok) {
                return queued;
            }
            if (options && options.onQueued) {
                options.onQueued(queued.id);
            }
            return waitForCommand(queued.id, options);
        });
    }

    PS.pepper.COMMAND_MESSAGES = COMMAND_MESSAGES;
    PS.pepper.readQueued = readQueued;
    PS.pepper.waitForCommand = waitForCommand;
    PS.pepper.sendAndWait = sendAndWait;

    /* =========================
       ANIMATED SAY: ritorna la Promise con l'esito {ok, status, message}
    ========================= */
    PS.pepper.animatedSay = function (text) {
        if (!text) return Promise.resolve({ ok: false, status: "failed", message: "testo vuoto" });

        var urls = PS.config.urls || {};
        var url = urls.pepperAnimatedSay;

        if (!url) {
            console.error("URL pepperAnimatedSay non configurato!");
            return Promise.resolve({ ok: false, status: "failed", message: "URL non configurato" });
        }

        return sendAndWait(url, { text: text }).then(function (result) {
            if (!result.ok) {
                console.error("Errore Pepper (animated say):", result.message);
            }
            return result;
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