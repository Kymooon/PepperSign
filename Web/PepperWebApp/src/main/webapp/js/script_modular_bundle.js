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
            pepperAnimatable: appContext + "/api/pepper/animatable",
            pepperGesture: appContext + "/api/pepper/gesture",
            asr: pyBase + "/transcribe"
        };

        return PS.config;
    }

    PS.config.init = init;
})(window);


/* PepperSign - ps-state.js
   Stato condiviso dell'app.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.state = PS.state || {};

    PS.state.refs = {};
    PS.state.mediaElements = [];
    PS.state.isSpeakBusy = false;
    PS.state.audioMode = "PC";

    function init() {
        try {
            PS.state.audioMode = localStorage.getItem("audioMode") || "PC";
        } catch (e) {
            PS.state.audioMode = "PC";
        }
    }

    function setRefs(refs) {
        PS.state.refs = refs || {};
    }

    function getRefs() {
        return PS.state.refs || {};
    }

    function setAudioMode(mode) {
        PS.state.audioMode = (mode === "PEPPER") ? "PEPPER" : "PC";
        try {
            localStorage.setItem("audioMode", PS.state.audioMode);
        } catch (e) {}
    }

    function getAudioMode() {
        return PS.state.audioMode || "PC";
    }

    function setMediaElements(list) {
        PS.state.mediaElements = list || [];
    }

    function getMediaElements() {
        return PS.state.mediaElements || [];
    }

    function setAsrStatus(msg) {
        var refs = getRefs();
        if (refs.asrText) refs.asrText.textContent = msg;
    }

    function updateAudioModeUI() {
        var refs = getRefs();
        if (refs.audioModeLabel) refs.audioModeLabel.textContent = (getAudioMode() === "PC" ? "PC" : "Pepper");
        if (refs.audioSourceToggle) refs.audioSourceToggle.checked = (getAudioMode() === "PEPPER");
    }

    PS.state.init = init;
    PS.state.setRefs = setRefs;
    PS.state.getRefs = getRefs;
    PS.state.setAudioMode = setAudioMode;
    PS.state.getAudioMode = getAudioMode;
    PS.state.setMediaElements = setMediaElements;
    PS.state.getMediaElements = getMediaElements;
    PS.state.setAsrStatus = setAsrStatus;
    PS.state.updateAudioModeUI = updateAudioModeUI;
})(window);


/* PepperSign - ps-modal.js
   Gestione apertura/chiusura video modal.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.modal = PS.modal || {};

    function close() {
        var refs = PS.state.getRefs();
        if (!refs.videoModal || !refs.videoPlayer) return;

        refs.videoModal.style.display = "none";

        try {
            refs.videoPlayer.pause();
        } catch (e) {}

        try {
            refs.videoPlayer.currentTime = 0;
        } catch (e2) {}

        refs.videoPlayer.src = "";
    }

    function open(videoUrl) {
        var refs = PS.state.getRefs();
        if (!refs.videoModal || !refs.videoPlayer) return;

        refs.videoPlayer.src = videoUrl;
        refs.videoModal.style.display = "flex";

        try {
            var playPromise = refs.videoPlayer.play();
            if (playPromise && typeof playPromise.catch === "function") {
                playPromise.catch(function () {
                    console.log("Autoplay bloccato dal browser");
                });
            }
        } catch (e) {
            console.log("play() non disponibile:", e);
        }
    }

    function bind() {
        var refs = PS.state.getRefs();

        if (refs.closeModalBtn) {
            refs.closeModalBtn.addEventListener("click", close);
        }

        window.addEventListener("click", function (e) {
            if (refs.videoModal && e.target === refs.videoModal) {
                close();
            }
        });
    }

    function init() {
        bind();
    }

    PS.modal.init = init;
    PS.modal.open = open;
    PS.modal.close = close;
})(window);


/* PepperSign - ps-lesson.js
   Flusso condiviso di conferma + avvio lezione.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.lesson = PS.lesson || {};

    function syncSearchInput(target) {
        var refs = PS.state.getRefs();
        if (refs.searchInput) {
            refs.searchInput.value = target;
            PS.util.dispatchInputEvent(refs.searchInput);
        }
    }

    function refreshAfterLesson(status, target) {
        if (status === "GENERATING") {
            PS.state.setAsrStatus('Genero il gesto per "' + target + '"... attendi qualche secondo.');
            setTimeout(function () {
                if (PS.media && PS.media.fetchMedia) PS.media.fetchMedia();
            }, 8000);
        } else {
            PS.state.setAsrStatus('Trovato: "' + target + '".');
            if (PS.media && PS.media.fetchMedia) PS.media.fetchMedia();
        }
    }

    function handleMissingTarget(transcript, showAlert) {
        var message = 'Ho capito: "' + (transcript || "") + '". Ma non riesco a estrarre la parola.';
        PS.state.setAsrStatus(message);
        if (showAlert) {
            alert("Non ho capito la parola. Riprova dicendo: 'voglio imparare ...'");
        }
        return Promise.resolve();
    }

    function confirmAndStart(target, transcript) {
        var urls = PS.config.urls || {};
        var ok;

        if (!target) {
            return handleMissingTarget(transcript, true);
        }

        if (transcript) {
            PS.state.setAsrStatus('Ho capito: "' + transcript + '" -> parola: "' + target + '"');
        } else {
            PS.state.setAsrStatus('Parola riconosciuta: "' + target + '"');
        }

        ok = confirm('Vuoi imparare: "' + target + '" ?');
        if (!ok) {
            PS.state.setAsrStatus("Ok, riprova quando vuoi.");
            return Promise.resolve();
        }

        PS.state.setAsrStatus('Avvio lezione per "' + target + '"...');

        return PS.util.xhrRequest("POST", urls.lesson, {
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target: target })
        }).then(function (res) {
            if (!res.ok) {
                return res.text().then(function (text) {
                    throw new Error(text || "Errore /api/lesson");
                });
            }
            return res.json();
        }).then(function (lessonJson) {
            if (!lessonJson || !lessonJson.target) {
                PS.state.setAsrStatus("Risposta lezione non valida.");
                alert("Errore avvio lezione.");
                return;
            }

            if (lessonJson.status !== "FOUND" && lessonJson.status !== "GENERATING") {
                PS.state.setAsrStatus("Errore durante avvio lezione.");
                alert("Errore avvio lezione.");
                return;
            }

            syncSearchInput(lessonJson.target);
            refreshAfterLesson(lessonJson.status, lessonJson.target);
        });
    }

    PS.lesson.syncSearchInput = syncSearchInput;
    PS.lesson.handleMissingTarget = handleMissingTarget;
    PS.lesson.confirmAndStart = confirmAndStart;
})(window);


/* PepperSign - ps-media.js
   Caricamento media, ricerca, generazione e rendering griglia.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.media = PS.media || {};

    function buildCard(element) {
        var gridItem = PS.util.create("div", "grid-item");
        var image = PS.util.create("img");
        var title = PS.util.create("p");
        var tryBtn = PS.util.create("button", "try-btn", "Prova gesto");
        var name = (element && element.nome) ? element.nome : "";
        var gestureId = PS.util.normalizeGestureId(name);
        var videoUrl = (element && element.urlVideo) ? element.urlVideo : "";
        var imageUrl = (element && element.urlImmagine) ? element.urlImmagine : "";

        gridItem.setAttribute("data-gesture-id", gestureId);

        image.src = imageUrl;
        image.alt = name;
        title.textContent = name;

        tryBtn.type = "button";
        tryBtn.addEventListener("click", function (ev) {
            ev.stopPropagation();

            if (typeof window.GestureTry === "undefined") {
                alert("Funzione Prova gesto non disponibile: gestureTry.js non caricato.");
                return;
            }

            window.GestureTry.open({ gestureId: gestureId });
        });

        gridItem.addEventListener("click", function () {
            PS.modal.open(videoUrl);
        });

        gridItem.appendChild(image);
        gridItem.appendChild(title);
        gridItem.appendChild(tryBtn);

        return gridItem;
    }

    function renderGrid(elements) {
        var refs = PS.state.getRefs();
        var i;

        if (!refs.mediaGrid) return;

        refs.mediaGrid.innerHTML = "";

        if (!elements || elements.length === 0) {
            refs.mediaGrid.innerHTML = "<p>Nessun elemento trovato.</p>";
            return;
        }

        for (i = 0; i < elements.length; i++) {
            refs.mediaGrid.appendChild(buildCard(elements[i]));
        }

        if (PS.cards && PS.cards.enhanceAll) {
            PS.cards.enhanceAll();
        }
    }

    function fetchMedia() {
        var urls = PS.config.urls || {};
        var refs = PS.state.getRefs();

        return PS.util.xhrRequest("GET", urls.mediaList).then(function (response) {
            if (!response.ok) throw new Error("Errore HTTP: " + response.status);
            return response.json();
        }).then(function (json) {
            PS.state.setMediaElements(json || []);
            renderGrid(PS.state.getMediaElements());
        }).catch(function (error) {
            console.error("Errore caricamento media:", error);
            if (refs.mediaGrid) {
                refs.mediaGrid.innerHTML = '<p style="color: red;">Errore caricamento. Controlla console.</p>';
            }
        });
    }

    function filterByQuery(query) {
        var q = PS.util.trim(query).toLowerCase();
        var all = PS.state.getMediaElements();
        var filtered = [];
        var i;
        var name;

        if (q === "") {
            renderGrid(all);
            return;
        }

        for (i = 0; i < all.length; i++) {
            name = String((all[i] && all[i].nome) || "").toLowerCase();
            if (name.indexOf(q) !== -1) filtered.push(all[i]);
        }

        renderGrid(filtered);
    }

    function requestElementGeneration(elementName) {
        var urls = PS.config.urls || {};
        var url = urls.generate + "?name=" + encodeURIComponent(elementName);

        return PS.util.xhrRequest("POST", url, { body: null }).then(function (response) {
            if (response.status === 409) {
                alert('L\'elemento "' + elementName + '" esiste gia\' sul server.');
                return;
            }

            if (!response.ok) {
                return response.text().then(function (text) {
                    throw new Error(text || "Errore");
                });
            }

            alert("Generazione avviata! Attendi qualche secondo...");
            setTimeout(function () {
                fetchMedia();
            }, 6000);
        }).catch(function (error) {
            console.error("Errore generazione:", error);
            alert("Errore: " + (error && error.message ? error.message : error));
        });
    }

    function bindSearch() {
        var refs = PS.state.getRefs();
        if (!refs.searchInput) return;

        refs.searchInput.addEventListener("input", function () {
            filterByQuery(refs.searchInput.value || "");
        });
    }

    function bindAddButton() {
        var refs = PS.state.getRefs();
        if (!refs.addButton) return;

        refs.addButton.addEventListener("click", function () {
            var newElementName = prompt("Inserisci la parola da generare:");
            var trimmedName;
            var all;
            var i;
            var currentName;

            if (!newElementName || PS.util.trim(newElementName) === "") return;
            trimmedName = PS.util.trim(newElementName);
            all = PS.state.getMediaElements();

            for (i = 0; i < all.length; i++) {
                currentName = String((all[i] && all[i].nome) || "").toLowerCase();
                if (currentName === trimmedName.toLowerCase()) {
                    alert('L\'elemento "' + trimmedName + '" esiste gia\'.');
                    return;
                }
            }

            requestElementGeneration(trimmedName);
        });
    }

    function init() {
        bindSearch();
        bindAddButton();
    }

    PS.media.init = init;
    PS.media.renderGrid = renderGrid;
    PS.media.fetchMedia = fetchMedia;
    PS.media.filterByQuery = filterByQuery;
    PS.media.requestElementGeneration = requestElementGeneration;
})(window);


/* PepperSign - ps-audio-pc.js
   Registrazione audio lato PC/tablet e invio al server ASR.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.audio = PS.audio || {};

    function recordAudioForSeconds(seconds) {
        seconds = (typeof seconds === "number" ? seconds : 4);

        if (typeof window.MediaRecorder === "undefined") {
            return Promise.reject(new Error("MediaRecorder non supportato su questo browser (Android 5.1)."));
        }

        return PS.util.getAudioStream().then(function (stream) {
            var recorder = new MediaRecorder(stream);
            var chunks = [];

            recorder.ondataavailable = function (e) {
                if (e && e.data) chunks.push(e.data);
            };

            return new Promise(function (resolve, reject) {
                recorder.onerror = function (e) {
                    reject((e && e.error) ? e.error : new Error("Errore recorder"));
                };

                recorder.onstop = function () {
                    var tracks;
                    var i;
                    try {
                        tracks = stream.getTracks();
                        for (i = 0; i < tracks.length; i++) tracks[i].stop();
                    } catch (err) {}

                    resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
                };

                recorder.start();

                setTimeout(function () {
                    try {
                        recorder.stop();
                    } catch (e2) {}
                }, seconds * 1000);
            });
        });
    }

    function runPcFlow() {
        var urls = PS.config.urls || {};
        var fd;

        PS.state.setAsrStatus("Sto ascoltando... parla ora (4s).");

        return recordAudioForSeconds(4).then(function (audioBlob) {
            PS.state.setAsrStatus("Invio audio al server (ASR)...");
            fd = new FormData();
            fd.append("audio", audioBlob, "audio.webm");
            return PS.util.xhrRequest("POST", urls.asr, { body: fd });
        }).then(function (asrRes) {
            if (!asrRes.ok) {
                return asrRes.text().then(function (text) {
                    throw new Error(text || "Errore ASR");
                });
            }
            return asrRes.json();
        }).then(function (asrJson) {
            if (!asrJson || !asrJson.target) {
                return PS.lesson.handleMissingTarget(asrJson ? asrJson.transcript : "", true);
            }
            return PS.lesson.confirmAndStart(asrJson.target, asrJson.transcript);
        }).catch(function (err) {
            console.error(err);
            PS.state.setAsrStatus("Errore microfono o server. Controlla console.");
            alert("Errore. Controlla che il servizio ASR e /api/lesson siano disponibili.");
        });
    }

    PS.audio.recordAudioForSeconds = recordAudioForSeconds;
    PS.audio.runPcFlow = runPcFlow;
})(window);


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


/* PepperSign - ps-cards.js
   Abilita badge e pulsante "Esegui gesto" sulle card.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.cards = PS.cards || {};

    var animatableMap = {};
    var observerStarted = false;

    function loadAnimatable() {
        var urls = PS.config.urls || {};
        return PS.util.xhrRequest("GET", urls.pepperAnimatable).then(function (res) {
            if (!res.ok) return { animatable: [] };
            return res.json();
        }).then(function (data) {
            var list = (data && data.animatable) ? data.animatable : [];
            var i;
            var key;

            animatableMap = {};
            for (i = 0; i < list.length; i++) {
                key = PS.util.normalizeGestureId(list[i]);
                if (key) animatableMap[key] = true;
            }
        }).catch(function (e) {
            console.warn("Impossibile caricare animatable list:", e);
            animatableMap = {};
        });
    }

    function getGestureIdFromCard(card) {
        var ds;
        var p;

        ds = card.getAttribute("data-gesture-id");
        if (PS.util.trim(ds)) return PS.util.normalizeGestureId(ds);

        if (card.dataset && card.dataset.gestureId && PS.util.trim(card.dataset.gestureId)) {
            return PS.util.normalizeGestureId(card.dataset.gestureId);
        }

        p = card.querySelector("p");
        if (p && p.textContent) return PS.util.normalizeGestureId(p.textContent);
        return "";
    }

    function enhanceCard(card) {
        var gestureId;
        var can;
        var capRow;
        var icon;
        var label;
        var execBtn;
        var tryBtn;
        var urls = PS.config.urls || {};

        if (!card || card.getAttribute("data-pepper-enhanced") === "1") return;

        gestureId = getGestureIdFromCard(card);
        can = !!animatableMap[gestureId];

        capRow = PS.util.create("div", "pepper-cap-row");
        icon = PS.util.create("span", "pepper-cap-icon " + (can ? "on" : "off"));
        label = PS.util.create("span");
        execBtn = PS.util.create("button", "exec-btn", "Esegui gesto");

        icon.title = can ? "Eseguibile fisicamente da Pepper" : "Non disponibile su Pepper";
        label.style.fontWeight = "800";
        label.style.opacity = can ? "0.95" : "0.45";
        label.textContent = can ? "Eseguibile su Pepper" : "Solo video";

        execBtn.type = "button";
        execBtn.disabled = !can;
        execBtn.addEventListener("click", function (ev) {
            var body;

            ev.preventDefault();
            ev.stopPropagation();

            if (!gestureId || !can) return;

            body = PS.util.formUrlEncode({ gestureId: gestureId });

            PS.util.xhrRequest("POST", urls.pepperGesture, {
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: body
            }).catch(function (e) {
                console.warn("Errore invio gesture a Pepper:", e);
            });
        });

        capRow.appendChild(icon);
        capRow.appendChild(label);

        tryBtn = card.querySelector(".try-btn");
        if (tryBtn && tryBtn.parentNode) {
            if (tryBtn.nextSibling) {
                tryBtn.parentNode.insertBefore(capRow, tryBtn.nextSibling);
            } else {
                tryBtn.parentNode.appendChild(capRow);
            }

            if (capRow.nextSibling) {
                tryBtn.parentNode.insertBefore(execBtn, capRow.nextSibling);
            } else {
                tryBtn.parentNode.appendChild(execBtn);
            }
        } else {
            card.appendChild(capRow);
            card.appendChild(execBtn);
        }

        card.setAttribute("data-pepper-enhanced", "1");
    }

    function enhanceAll() {
        var refs = PS.state.getRefs();
        var cards;
        var i;

        if (!refs.mediaGrid) return Promise.resolve();

        return loadAnimatable().then(function () {
            cards = refs.mediaGrid.querySelectorAll(".grid-item");
            for (i = 0; i < cards.length; i++) enhanceCard(cards[i]);
        });
    }

    function watchGrid() {
        var refs = PS.state.getRefs();
        var observer;

        if (!window.MutationObserver || observerStarted || !refs.mediaGrid) return;

        observerStarted = true;
        observer = new MutationObserver(function () {
            var cards = refs.mediaGrid.querySelectorAll(".grid-item");
            var i;
            for (i = 0; i < cards.length; i++) enhanceCard(cards[i]);
        });

        observer.observe(refs.mediaGrid, { childList: true, subtree: true });
    }

    function init() {
        watchGrid();
    }

    PS.cards.init = init;
    PS.cards.enhanceAll = enhanceAll;
})(window);


/* PepperSign - ps-app.js
   Bootstrap dell'applicazione.
*/
(function (window, document) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.app = PS.app || {};

    function getRefs() {
        return {
            mediaGrid: document.getElementById("mediaGrid"),
            searchInput: document.getElementById("searchInput"),
            videoModal: document.getElementById("videoModal"),
            videoPlayer: document.getElementById("videoPlayer"),
            closeModalBtn: document.querySelector(".close-btn"),
            addButton: document.getElementById("addButton"),
            audioSourceToggle: document.getElementById("audioSourceToggle"),
            audioModeLabel: document.getElementById("audioModeLabel"),
            speakButton: document.getElementById("speakButton"),
            asrText: document.getElementById("asrText")
        };
    }

    function updateInitialStatus() {
        if (PS.state.getAudioMode() === "PEPPER") {
            PS.state.setAsrStatus("Modalita' Pepper: premi 'Parla con Pepper' per avviare l'interazione.");
        } else {
            PS.state.setAsrStatus("Premi 'Parla con Pepper' e pronuncia: 'voglio imparare ...'");
        }
    }

    function bindAudioToggle() {
        var refs = PS.state.getRefs();
        if (!refs.audioSourceToggle) return;

        refs.audioSourceToggle.addEventListener("change", function () {
            PS.state.setAudioMode(refs.audioSourceToggle.checked ? "PEPPER" : "PC");
            PS.state.updateAudioModeUI();
            updateInitialStatus();
        });
    }

    function unlockSpeakButton() {
        var refs = PS.state.getRefs();
        PS.state.isSpeakBusy = false;
        if (refs.speakButton) refs.speakButton.disabled = false;
    }

    function lockSpeakButton() {
        var refs = PS.state.getRefs();
        PS.state.isSpeakBusy = true;
        if (refs.speakButton) refs.speakButton.disabled = true;
    }

    function runSpeakFlow() {
        var mode = PS.state.getAudioMode();
        var introText = "Che gesto vuoi imparare oggi?";

        lockSpeakButton();

        PS.pepper.playIntroPrompt(introText, 4000).then(function () {
            if (mode === "PEPPER") {
                return PS.pepper.runPepperFlow();
            }
            return PS.audio.runPcFlow();
        }).then(function () {
            unlockSpeakButton();
        }).catch(function (err) {
            console.error("Errore generale speak flow:", err);
            unlockSpeakButton();
        });
    }

    function bindSpeakButton() {
        var refs = PS.state.getRefs();
        if (!refs.speakButton) return;

        refs.speakButton.addEventListener("click", function () {
            if (PS.state.isSpeakBusy) return;
            runSpeakFlow();
        });
    }

    function initGestureTry() {
        if (typeof window.GestureTry !== "undefined") {
            window.GestureTry.init({
                serviceBaseUrl: PS.config.pyBase,
                defaultRecordMs: 4000
            });
        } else {
            console.warn("GestureTry non caricato. Metti gestureTry.js prima di ps-app.js nell'HTML.");
        }
    }

    function init() {
        var refs = getRefs();

        if (!refs.mediaGrid) {
            console.error("ERRORE: #mediaGrid non trovato nell'HTML");
            return;
        }

        PS.config.init();
        PS.state.init();
        PS.state.setRefs(refs);

        PS.modal.init();
        PS.media.init();
        PS.cards.init();
        bindAudioToggle();
        bindSpeakButton();
        PS.state.updateAudioModeUI();
        updateInitialStatus();
        initGestureTry();
        PS.media.fetchMedia();
    }

    PS.app.init = init;

    document.addEventListener("DOMContentLoaded", init);
})(window, document);
