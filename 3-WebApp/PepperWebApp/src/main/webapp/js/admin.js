(function () {
    "use strict";

    var APP_CONTEXT = window.PEPPERSIGN_CONTEXT_PATH || "";
    var WELCOME_STORAGE_KEY = "peppersign_welcome_seen_v1";

    function $(id) {
        return document.getElementById(id);
    }

    function xhrRequest(options, callback) {
        var xhr = new XMLHttpRequest();
        xhr.open(options.method || "GET", options.url, true);

        if (options.headers) {
            for (var key in options.headers) {
                if (options.headers.hasOwnProperty(key)) {
                    xhr.setRequestHeader(key, options.headers[key]);
                }
            }
        }

        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4) {
                return;
            }
            callback(null, {
                status: xhr.status,
                text: xhr.responseText,
                contentType: xhr.getResponseHeader("Content-Type") || ""
            });
        };

        xhr.onerror = function () {
            callback(new Error("Errore di rete"));
        };

        xhr.send(options.body || null);
    }

    function safeParseJson(text) {
        if (!text) {
            return null;
        }
        try {
            return JSON.parse(text);
        } catch (e) {
            return null;
        }
    }

    function setOutput(elementId, value) {
        var el = $(elementId);
        if (!el) {
            return;
        }
        if (typeof value === "string") {
            el.textContent = value;
        } else {
            el.textContent = JSON.stringify(value, null, 2);
        }
    }

    function setBadge(elementId, label, type) {
        var el = $(elementId);
        if (!el) {
            return;
        }
        el.className = "admin-badge " + (type || "admin-badge-neutral");
        el.textContent = label;
    }

    function buildFormBody(data) {
        var pairs = [];
        var key;
        for (key in data) {
            if (data.hasOwnProperty(key)) {
                pairs.push(encodeURIComponent(key) + "=" + encodeURIComponent(data[key]));
            }
        }
        return pairs.join("&");
    }

    function formatResponse(prefix, result) {
        var parsed = safeParseJson(result.text);
        var bodyText = parsed ? JSON.stringify(parsed, null, 2) : (result.text || "(vuoto)");
        return prefix + "\nHTTP " + result.status + "\n\n" + bodyText;
    }

    function loadAnimatableGestures(onDone) {
        xhrRequest({
            method: "GET",
            url: APP_CONTEXT + "/api/pepper/animatable"
        }, function (err, result) {
            var select = $("gestureSelect");
            var data, list, i, option;

            if (err) {
                setBadge("statusAnimatable", "Errore rete", "admin-badge-error");
                setOutput("gestureOutput", "Impossibile caricare i segni animabili.\n" + err.message);
                if (typeof onDone === "function") {
                    onDone(err);
                }
                return;
            }

            data = safeParseJson(result.text);
            list = data && data.animatable ? data.animatable : [];

            if (select) {
                select.innerHTML = "";
                option = document.createElement("option");
                option.value = "";
                option.appendChild(document.createTextNode("Seleziona un segno..."));
                select.appendChild(option);

                for (i = 0; i < list.length; i++) {
                    option = document.createElement("option");
                    option.value = list[i];
                    option.appendChild(document.createTextNode(list[i]));
                    select.appendChild(option);
                }
            }

            if (result.status >= 200 && result.status < 300) {
                setBadge("statusAnimatable", "OK", "admin-badge-ok");
            } else {
                setBadge("statusAnimatable", "Errore " + result.status, "admin-badge-error");
            }

            if (typeof onDone === "function") {
                onDone(null, list, result);
            }
        });
    }

    function runPassiveChecks() {
        setOutput("passiveChecksOutput", "Verifica in corso...");

        xhrRequest({
            method: "GET",
            url: APP_CONTEXT + "/api/media"
        }, function (errMedia, mediaResult) {
            var messages = [];
            var mediaData, count;

            if (errMedia) {
                setBadge("statusMedia", "Errore rete", "admin-badge-error");
                messages.push("GET /api/media -> errore rete: " + errMedia.message);
            } else {
                mediaData = safeParseJson(mediaResult.text);
                count = mediaData && mediaData.length ? mediaData.length : 0;

                if (mediaResult.status >= 200 && mediaResult.status < 300) {
                    setBadge("statusMedia", "OK", "admin-badge-ok");
                    messages.push("GET /api/media -> HTTP " + mediaResult.status + " | elementi: " + count);
                } else {
                    setBadge("statusMedia", "Errore " + mediaResult.status, "admin-badge-error");
                    messages.push("GET /api/media -> HTTP " + mediaResult.status);
                }
            }

            loadAnimatableGestures(function (errAnim, list, animResult) {
                if (errAnim) {
                    messages.push("GET /api/pepper/animatable -> errore rete: " + errAnim.message);
                } else {
                    if (animResult.status >= 200 && animResult.status < 300) {
                        messages.push("GET /api/pepper/animatable -> HTTP " + animResult.status + " | segni: " + (list ? list.length : 0));
                    } else {
                        messages.push("GET /api/pepper/animatable -> HTTP " + animResult.status);
                    }
                }

                setOutput("passiveChecksOutput", messages.join("\n"));
            });
        });
    }

    function sendSayCommand() {
        var text = ($("sayText").value || "").replace(/^\s+|\s+$/g, "");

        if (!text) {
            setBadge("statusSay", "Test non valido", "admin-badge-warn");
            setOutput("sayOutput", "Inserisci un testo prima di inviare il comando SAY.");
            return;
        }

        setOutput("sayOutput", "Invio comando SAY in corso...");

        xhrRequest({
            method: "POST",
            url: APP_CONTEXT + "/api/pepper/say",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            body: buildFormBody({ text: text })
        }, function (err, result) {
            if (err) {
                setBadge("statusSay", "Errore rete", "admin-badge-error");
                setOutput("sayOutput", "Errore di rete durante l'invio del comando SAY.\n" + err.message);
                return;
            }

            handleCommandResponse("statusSay", "sayOutput", "SAY", result);
        });
    }

    /*
     * Dopo l'invio di un comando segue il suo stato su /api/pepper/command
     * fino all'esito (eseguito, fallito, scaduto, non confermato).
     */
    function followCommand(commandId, badgeId, outputId, label, firstText) {
        var startedAt = new Date().getTime();

        function step() {
            if (new Date().getTime() - startedAt > 70000) {
                setBadge(badgeId, "Nessuna risposta", "admin-badge-warn");
                setOutput(outputId, firstText + "\n\nEsito: nessuna risposta dal robot entro 70 s.");
                return;
            }
            xhrRequest({
                method: "GET",
                url: APP_CONTEXT + "/api/pepper/command?id=" + encodeURIComponent(commandId)
            }, function (err, result) {
                var data = result ? safeParseJson(result.text) : null;
                if (err || !data || !data.ok) {
                    window.setTimeout(step, 1000);
                    return;
                }
                if (!data["final"]) {
                    setBadge(badgeId, data.status === "sent" ? "In esecuzione" : "In coda", "admin-badge-neutral");
                    window.setTimeout(step, 500);
                    return;
                }
                if (data.status === "done") {
                    setBadge(badgeId, "Eseguito", "admin-badge-ok");
                } else {
                    setBadge(badgeId, data.status === "failed" ? "Fallito" : "Non eseguito", "admin-badge-error");
                }
                setOutput(outputId, firstText + "\n\nEsito " + label + ": " + data.status
                    + (data.message ? " - " + data.message : ""));
            });
        }

        step();
    }

    /* Badge e uscita dopo l'invio di un comando; se la WebApp ha dato un id, segue l'esito. */
    function handleCommandResponse(badgeId, outputId, label, result) {
        var data = safeParseJson(result.text) || {};
        var text = formatResponse("Risposta comando " + label, result);

        setOutput(outputId, text);
        if (result.status >= 200 && result.status < 300 && data.id) {
            setBadge(badgeId, "In coda", "admin-badge-neutral");
            followCommand(data.id, badgeId, outputId, label, text);
        } else if (data.robotOnline === false) {
            setBadge(badgeId, "Robot non collegato", "admin-badge-error");
        } else if (result.status >= 200 && result.status < 300) {
            setBadge(badgeId, "OK", "admin-badge-ok");
        } else {
            setBadge(badgeId, "Errore " + result.status, "admin-badge-error");
        }
    }

    function getSelectedGestureId() {
        var customValue = ($("gestureCustom").value || "").replace(/^\s+|\s+$/g, "");
        var selectValue = $("gestureSelect").value || "";
        return customValue || selectValue;
    }

    function sendGestureCommand() {
        var gestureId = getSelectedGestureId();

        if (!gestureId) {
            setBadge("statusGesture", "Test non valido", "admin-badge-warn");
            setOutput("gestureOutput", "Seleziona o scrivi un gestureId prima di inviare il comando.");
            return;
        }

        setOutput("gestureOutput", "Invio comando GESTURE in corso...");

        xhrRequest({
            method: "POST",
            url: APP_CONTEXT + "/api/pepper/gesture",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            body: buildFormBody({ gestureId: gestureId })
        }, function (err, result) {
            if (err) {
                setBadge("statusGesture", "Errore rete", "admin-badge-error");
                setOutput("gestureOutput", "Errore di rete durante l'invio del segno.\n" + err.message);
                return;
            }

            handleCommandResponse("statusGesture", "gestureOutput", "GESTURE", result);
        });
    }

    function sendLessonTest() {
        var target = ($("lessonTarget").value || "").replace(/^\s+|\s+$/g, "");

        if (!target) {
            setBadge("statusLesson", "Test non valido", "admin-badge-warn");
            setOutput("lessonOutput", "Inserisci un target prima di inviare il test lesson.");
            return;
        }

        setOutput("lessonOutput", "Invio richiesta lesson in corso...");

        xhrRequest({
            method: "POST",
            url: APP_CONTEXT + "/api/lesson",
            headers: {
                "Content-Type": "application/json; charset=UTF-8"
            },
            body: JSON.stringify({ target: target })
        }, function (err, result) {
            if (err) {
                setBadge("statusLesson", "Errore rete", "admin-badge-error");
                setOutput("lessonOutput", "Errore di rete durante il test lesson.\n" + err.message);
                return;
            }

            if (result.status >= 200 && result.status < 300) {
                setBadge("statusLesson", "OK", "admin-badge-ok");
            } else {
                setBadge("statusLesson", "Errore " + result.status, "admin-badge-error");
            }

            setOutput("lessonOutput", formatResponse("Risposta test lesson", result));
        });
    }

    function loadMediaCatalog() {
        setOutput("mediaOutput", "Caricamento catalogo media in corso...");

        xhrRequest({
            method: "GET",
            url: APP_CONTEXT + "/api/media"
        }, function (err, result) {
            var data, lines, i, item;

            if (err) {
                setOutput("mediaOutput", "Errore di rete durante il caricamento del catalogo media.\n" + err.message);
                return;
            }

            data = safeParseJson(result.text);

            if (!(data && typeof data.length !== "undefined")) {
                setOutput("mediaOutput", formatResponse("Risposta catalogo media", result));
                return;
            }

            lines = [];
            lines.push("HTTP " + result.status);
            lines.push("Elementi trovati: " + data.length);

            for (i = 0; i < data.length && i < 8; i++) {
                item = data[i];
                lines.push("- " + item.nome + " | img: " + item.urlImmagine + " | video: " + item.urlVideo);
            }

            if (data.length > 8) {
                lines.push("... altri " + (data.length - 8) + " elementi");
            }

            setOutput("mediaOutput", lines.join("\n"));
        });
    }

    function clearCookie(name) {
        document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    }

    function resetWelcomeFirstVisit() {
        var storageOk = false;
        var cookieOk = false;
        var messages = [];

        try {
            if (window.localStorage) {
                window.localStorage.removeItem(WELCOME_STORAGE_KEY);
                storageOk = true;
            }
        } catch (e) {
            messages.push("localStorage non disponibile o non accessibile.");
        }

        try {
            clearCookie(WELCOME_STORAGE_KEY);
            cookieOk = true;
        } catch (err) {
            messages.push("Impossibile cancellare il cookie di fallback.");
        }

        if (storageOk) {
            messages.push("Flag localStorage rimosso: " + WELCOME_STORAGE_KEY);
        } else {
            messages.push("Flag localStorage non rimosso.");
        }

        if (cookieOk) {
            messages.push("Cookie di fallback cancellato: " + WELCOME_STORAGE_KEY);
        } else {
            messages.push("Cookie di fallback non cancellato.");
        }

        messages.push("");
        messages.push("Adesso puoi tornare alla home e ricaricare la pagina per verificare di nuovo il popup di benvenuto.");

        setOutput("resetWelcomeOutput", messages.join("\n"));
    }

    function bind(id, eventName, handler) {
        var el = $(id);
        if (el) {
            el.addEventListener(eventName, handler, false);
        }
    }

    function init() {
        bind("runPassiveChecksBtn", "click", runPassiveChecks);
        bind("reloadGesturesBtn", "click", function () {
            setOutput("gestureOutput", "Ricarico la lista dei segni animabili...");
            loadAnimatableGestures(function (err, list) {
                if (err) {
                    return;
                }
                setOutput("gestureOutput", "Segni disponibili caricati: " + list.length);
            });
        });
        bind("sendSayBtn", "click", sendSayCommand);
        bind("sendGestureBtn", "click", sendGestureCommand);
        bind("sendLessonBtn", "click", sendLessonTest);
        bind("loadMediaBtn", "click", loadMediaCatalog);
        bind("resetWelcomeBtn", "click", resetWelcomeFirstVisit);

        loadAnimatableGestures(function (err, list) {
            if (!err) {
                setOutput("gestureOutput", "Segni disponibili caricati: " + list.length);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, false);
    } else {
        init();
    }
}());
