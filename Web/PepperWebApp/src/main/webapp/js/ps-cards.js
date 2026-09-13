/* PepperSign - ps-cards.js
   Abilita badge e pulsante "Esegui gesto" sulle card.

   Modifiche:
   - prima di eseguire il gesto, Pepper dice a voce il gesto che sta per eseguire;
   - modalità testing locale:
     se attiva da admin, sostituisce "Prova gesto" ed "Esegui gesto"
     con veri <button disabled>, solo sul browser/dispositivo corrente.
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.cards = PS.cards || {};

    var animatableMap = {};
    var observerStarted = false;

    var LOCAL_DISABLE_KEY = "peppersign_disable_gesture_buttons";

    function areGestureButtonsDisabledLocally() {
        try {
            return window.localStorage.getItem(LOCAL_DISABLE_KEY) === "1";
        } catch (e) {
            return false;
        }
    }

    function hasClass(el, className) {
        if (!el || !el.className) {
            return false;
        }

        return (" " + el.className + " ").indexOf(" " + className + " ") !== -1;
    }

    function addClass(el, className) {
        if (!el) {
            return;
        }

        if (!hasClass(el, className)) {
            el.className = PS.util.trim((el.className || "") + " " + className);
        }
    }

    function removeClass(el, className) {
        if (!el || !el.className) {
            return;
        }

        el.className = PS.util.trim((" " + el.className + " ").replace(" " + className + " ", " "));
    }

    function getText(el) {
        if (!el) {
            return "";
        }

        return PS.util.trim(el.textContent || el.innerText || "");
    }

    function isTryGestureElement(el) {
        var text;

        if (!el) {
            return false;
        }

        if (hasClass(el, "try-btn")) {
            return true;
        }

        text = getText(el).toLowerCase();

        return text === "prova gesto" || text.indexOf("prova gesto") !== -1;
    }

    function isExecGestureElement(el) {
        var text;

        if (!el) {
            return false;
        }

        if (hasClass(el, "exec-btn")) {
            return true;
        }

        text = getText(el).toLowerCase();

        return text === "esegui gesto" || text.indexOf("esegui gesto") !== -1;
    }

    function findTryButton(card) {
        var direct;
        var elements;
        var i;

        direct = card.querySelector(".try-btn");

        if (direct) {
            return direct;
        }

        elements = card.querySelectorAll("button, a, div, span");

        for (i = 0; i < elements.length; i++) {
            if (isTryGestureElement(elements[i])) {
                return elements[i];
            }
        }

        return null;
    }

    function getReplacement(card, role) {
        return card.querySelector('[data-local-testing-replacement="' + role + '"]');
    }

    function createDisabledReplacement(original, label, role) {
        var btn;
        var style;

        btn = document.createElement("button");
        btn.type = "button";

        /*
         * Resta un vero bottone disabilitato,
         * quindi non è cliccabile.
         */
        btn.disabled = true;
        btn.setAttribute("disabled", "disabled");
        btn.setAttribute("aria-disabled", "true");
        btn.setAttribute("data-local-testing-replacement", role);

        /*
         * Mantiene le classi originali del tasto,
         * quindi conserva forma, dimensione e colore.
         */
        btn.className = original.className || "";

        addClass(btn, "local-testing-disabled-btn");

        btn.textContent = label;
        btn.title = "Disabilitato localmente per il testing";

        /*
         * Copia lo stile visivo reale del pulsante originale.
         * Serve perché i button disabled spesso diventano grigi di default.
         */
        if (window.getComputedStyle) {
            style = window.getComputedStyle(original);

            btn.style.backgroundColor = style.backgroundColor;
            btn.style.backgroundImage = style.backgroundImage;
            btn.style.color = style.color;
            btn.style.borderColor = style.borderColor;
            btn.style.borderStyle = style.borderStyle;
            btn.style.borderWidth = style.borderWidth;
            btn.style.borderRadius = style.borderRadius;
            btn.style.boxShadow = style.boxShadow;
            btn.style.fontFamily = style.fontFamily;
            btn.style.fontSize = style.fontSize;
            btn.style.fontWeight = style.fontWeight;
            btn.style.lineHeight = style.lineHeight;
            btn.style.padding = style.padding;
            btn.style.margin = style.margin;
            btn.style.width = style.width;
            btn.style.minWidth = style.minWidth;
            btn.style.height = style.height;
            btn.style.minHeight = style.minHeight;
            btn.style.textAlign = style.textAlign;
        }

        /*
         * Forza il mantenimento del colore anche quando il bottone è disabled.
         */
        btn.style.opacity = "1";
        btn.style.filter = "none";
        btn.style.cursor = "not-allowed";

        /*
         * Su Chrome/Android alcuni button disabled cambiano colore al testo.
         * Questa proprietà evita che il testo diventi grigio.
         */
        btn.style.webkitTextFillColor = btn.style.color;

        return btn;
    }

    function replaceWithDisabledButton(card, original, label, role) {
        var replacement;
        var originalDisplay;

        if (!card || !original || !original.parentNode) {
            return;
        }

        replacement = getReplacement(card, role);

        if (!replacement) {
            replacement = createDisabledReplacement(original, label, role);
            original.parentNode.insertBefore(replacement, original.nextSibling);
        }

        if (original.getAttribute("data-local-testing-hidden-original") !== "1") {
            originalDisplay = original.style.display || "";

            original.setAttribute("data-local-testing-hidden-original", "1");
            original.setAttribute("data-local-testing-role", role);
            original.setAttribute("data-local-testing-original-display", originalDisplay);
        }

        original.style.display = "none";
        original.setAttribute("aria-hidden", "true");

        if (original.tagName && original.tagName.toLowerCase() === "button") {
            original.disabled = true;
            original.setAttribute("disabled", "disabled");
        }
    }

    function restoreOriginalButton(card, original, role, shouldBeDisabled) {
        var replacement;
        var originalDisplay;

        if (!card || !original) {
            return;
        }

        replacement = getReplacement(card, role);

        if (replacement && replacement.parentNode) {
            replacement.parentNode.removeChild(replacement);
        }

        if (original.getAttribute("data-local-testing-hidden-original") === "1") {
            originalDisplay = original.getAttribute("data-local-testing-original-display");

            original.style.display = originalDisplay || "";
            original.removeAttribute("data-local-testing-hidden-original");
            original.removeAttribute("data-local-testing-role");
            original.removeAttribute("data-local-testing-original-display");
            original.removeAttribute("aria-hidden");
        }

        removeClass(original, "locally-disabled");

        if (original.tagName && original.tagName.toLowerCase() === "button") {
            original.disabled = !!shouldBeDisabled;

            if (shouldBeDisabled) {
                original.setAttribute("disabled", "disabled");
            } else {
                original.removeAttribute("disabled");
            }
        }
    }

    function applyLocalTestingState(card, can, execBtn) {
        var tryBtn;
        var disabledLocally;

        if (!card) {
            return;
        }

        tryBtn = findTryButton(card);
        disabledLocally = areGestureButtonsDisabledLocally();

        if (disabledLocally) {
            if (tryBtn) {
                replaceWithDisabledButton(card, tryBtn, "Prova gesto", "try");
            }

            if (execBtn) {
                replaceWithDisabledButton(card, execBtn, "Esegui gesto", "exec");
            }

            card.setAttribute("data-local-testing-disabled", "1");
        } else {
            if (tryBtn) {
                restoreOriginalButton(card, tryBtn, "try", false);
            }

            if (execBtn) {
                restoreOriginalButton(card, execBtn, "exec", !can);
            }

            card.removeAttribute("data-local-testing-disabled");
        }
    }

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

                if (key) {
                    animatableMap[key] = true;
                }
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

        if (PS.util.trim(ds)) {
            return PS.util.normalizeGestureId(ds);
        }

        if (card.dataset && card.dataset.gestureId && PS.util.trim(card.dataset.gestureId)) {
            return PS.util.normalizeGestureId(card.dataset.gestureId);
        }

        p = card.querySelector("p");

        if (p && p.textContent) {
            return PS.util.normalizeGestureId(p.textContent);
        }

        return "";
    }

    function cleanGestureNameForSpeech(value) {
        var text = value || "";

        try {
            text = decodeURIComponent(text);
        } catch (e) {}

        text = text.replace(/\.[^/.]+$/, "");
        text = text.replace(/[_-]+/g, " ");
        text = text.replace(/\s+/g, " ");
        text = PS.util.trim(text);

        if (!text) {
            text = "selezionato";
        }

        return text;
    }

    function getGestureLabelFromCard(card, gestureId) {
        var label;
        var p;

        label = card.getAttribute("data-gesture-name");

        if (!PS.util.trim(label)) {
            label = card.getAttribute("data-title");
        }

        if (!PS.util.trim(label) && card.dataset) {
            label = card.dataset.gestureName || card.dataset.title || "";
        }

        if (!PS.util.trim(label)) {
            p = card.querySelector("p");

            if (p && p.textContent) {
                label = p.textContent;
            }
        }

        if (!PS.util.trim(label)) {
            label = gestureId;
        }

        return cleanGestureNameForSpeech(label);
    }

    function inferContextPath() {
        var path = window.location.pathname || "";
        var secondSlash;

        if (!path || path === "/") {
            return "";
        }

        if (path.charAt(0) !== "/") {
            return "";
        }

        secondSlash = path.indexOf("/", 1);

        if (secondSlash === -1) {
            return "";
        }

        return path.substring(0, secondSlash);
    }

    function getPepperSayUrl(urls) {
        if (urls.pepperSay) {
            return urls.pepperSay;
        }

        if (urls.pepperSpeak) {
            return urls.pepperSpeak;
        }

        if (urls.pepperGesture) {
            return urls.pepperGesture.replace(/\/gesture([?#].*)?$/, "/say$1");
        }

        return inferContextPath() + "/api/pepper/say";
    }

    function wait(ms) {
        return new Promise(function (resolve) {
            window.setTimeout(resolve, ms);
        });
    }

    function sayGestureName(urls, gestureLabel) {
        var sayUrl = getPepperSayUrl(urls);
        var textToSay = "Sto per eseguire il gesto " + gestureLabel + ".";

        return PS.util.xhrRequest("POST", sayUrl, {
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: PS.util.formUrlEncode({
                text: textToSay
            })
        });
    }

    function executePepperGesture(urls, gestureId) {
        var body = PS.util.formUrlEncode({
            gestureId: gestureId
        });

        return PS.util.xhrRequest("POST", urls.pepperGesture, {
            headers: {
                "Content-Type": "application/x-www-form-urlencoded"
            },
            body: body
        });
    }

    function sayThenExecuteGesture(urls, gestureId, gestureLabel) {
        return sayGestureName(urls, gestureLabel).catch(function (e) {
            console.warn("Errore voce Pepper, eseguo comunque il gesto:", e);
        }).then(function () {
            return wait(900);
        }).then(function () {
            return executePepperGesture(urls, gestureId);
        });
    }

    function openVideoFromCard(card) {
        var event;

        if (!card) {
            return;
        }

        /*
         * Simula il click sulla card, così viene aperto lo stesso video
         * che si aprirebbe premendo normalmente sulla card.
         */
        try {
            if (typeof MouseEvent === "function") {
                event = new MouseEvent("click", {
                    bubbles: true,
                    cancelable: true,
                    view: window
                });
            } else {
                event = document.createEvent("MouseEvents");
                event.initMouseEvent(
                    "click",
                    true,
                    true,
                    window,
                    1,
                    0,
                    0,
                    0,
                    0,
                    false,
                    false,
                    false,
                    false,
                    0,
                    null
                );
            }

            card.dispatchEvent(event);
        } catch (e) {
            try {
                card.click();
            } catch (ignore) {}
        }
    }

    function ensureExecButton(card, gestureId) {
        var execBtn = card.querySelector(".exec-btn");
        var tryBtn = findTryButton(card);
        var urls = PS.config.urls || {};

        function openVideoFromCard() {
            var event;

            if (!card) {
                return;
            }

            /*
             * Simula il click sulla card, così si apre lo stesso video
             * che si aprirebbe premendo normalmente sulla card.
             */
            try {
                if (typeof MouseEvent === "function") {
                    event = new MouseEvent("click", {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                } else {
                    event = document.createEvent("MouseEvents");
                    event.initMouseEvent(
                        "click",
                        true,
                        true,
                        window,
                        1,
                        0,
                        0,
                        0,
                        0,
                        false,
                        false,
                        false,
                        false,
                        0,
                        null
                    );
                }

                card.dispatchEvent(event);
            } catch (e) {
                try {
                    card.click();
                } catch (ignore) {}
            }
        }

        if (execBtn) {
            return execBtn;
        }

        execBtn = PS.util.create("button", "exec-btn", "Esegui gesto");
        execBtn.type = "button";

        execBtn.addEventListener("click", function (ev) {
            var gestureLabel;
            var oldText;
            var can;

            ev.preventDefault();
            ev.stopPropagation();

            can = !!animatableMap[gestureId];

            if (!gestureId || execBtn.disabled || !can) {
                return;
            }

            if (areGestureButtonsDisabledLocally()) {
                return;
            }

            if (execBtn.getAttribute("data-running") === "1") {
                return;
            }

            /*
             * Quando premo "Esegui gesto", apro anche il video della card.
             */
            openVideoFromCard();

            gestureLabel = getGestureLabelFromCard(card, gestureId);
            oldText = execBtn.textContent;

            execBtn.setAttribute("data-running", "1");
            execBtn.disabled = true;
            execBtn.setAttribute("disabled", "disabled");
            execBtn.textContent = "Preparazione...";

            sayThenExecuteGesture(urls, gestureId, gestureLabel).then(function () {
                execBtn.textContent = oldText;
                execBtn.setAttribute("data-running", "0");
                execBtn.removeAttribute("disabled");
                applyLocalTestingState(card, !!animatableMap[gestureId], execBtn);
            }).catch(function (e) {
                console.warn("Errore invio gesture a Pepper:", e);

                execBtn.textContent = oldText;
                execBtn.setAttribute("data-running", "0");
                execBtn.removeAttribute("disabled");
                applyLocalTestingState(card, !!animatableMap[gestureId], execBtn);
            });
        });

        if (tryBtn && tryBtn.parentNode) {
            if (tryBtn.nextSibling) {
                tryBtn.parentNode.insertBefore(execBtn, tryBtn.nextSibling);
            } else {
                tryBtn.parentNode.appendChild(execBtn);
            }
        } else {
            card.appendChild(execBtn);
        }

        return execBtn;
    }

    function ensureCapRow(card) {
        var capRow = card.querySelector(".pepper-cap-row");
        var tryBtn = findTryButton(card);
        var icon;
        var label;

        if (capRow) {
            return {
                row: capRow,
                icon: capRow.querySelector(".pepper-cap-icon"),
                label: capRow.querySelector(".pepper-cap-label")
            };
        }

        capRow = PS.util.create("div", "pepper-cap-row");
        icon = PS.util.create("span", "pepper-cap-icon");
        label = PS.util.create("span", "pepper-cap-label");

        label.style.fontWeight = "800";

        capRow.appendChild(icon);
        capRow.appendChild(label);

        if (tryBtn && tryBtn.parentNode) {
            if (tryBtn.nextSibling) {
                tryBtn.parentNode.insertBefore(capRow, tryBtn.nextSibling);
            } else {
                tryBtn.parentNode.appendChild(capRow);
            }
        } else {
            card.appendChild(capRow);
        }

        return {
            row: capRow,
            icon: icon,
            label: label
        };
    }

    function enhanceCard(card) {
        var gestureId;
        var can;
        var cap;
        var execBtn;

        if (!card) {
            return;
        }

        gestureId = getGestureIdFromCard(card);
        can = !!animatableMap[gestureId];

        cap = ensureCapRow(card);
        execBtn = ensureExecButton(card, gestureId);

        cap.icon.className = "pepper-cap-icon " + (can ? "on" : "off");
        cap.icon.title = can ? "Eseguibile fisicamente da Pepper" : "Non disponibile su Pepper";

        cap.label.style.opacity = can ? "0.95" : "0.45";
        cap.label.textContent = can ? "Eseguibile su Pepper" : "Solo video";

        if (!areGestureButtonsDisabledLocally()) {
            execBtn.disabled = !can;

            if (can) {
                execBtn.removeAttribute("disabled");
            } else {
                execBtn.setAttribute("disabled", "disabled");
            }
        }

        applyLocalTestingState(card, can, execBtn);

        execBtn.setAttribute("data-gesture-id", gestureId);

        card.setAttribute("data-pepper-enhanced", "1");
    }

    function enhanceAll() {
        var refs = PS.state.getRefs();
        var cards;
        var i;

        if (!refs.mediaGrid) {
            return Promise.resolve();
        }

        return loadAnimatable().then(function () {
            cards = refs.mediaGrid.querySelectorAll(".grid-item");

            for (i = 0; i < cards.length; i++) {
                enhanceCard(cards[i]);
            }
        });
    }

    function refreshLocalTestingStateOnly() {
        var refs = PS.state.getRefs();
        var cards;
        var i;
        var card;
        var gestureId;
        var can;
        var execBtn;

        if (!refs.mediaGrid) {
            return;
        }

        cards = refs.mediaGrid.querySelectorAll(".grid-item");

        for (i = 0; i < cards.length; i++) {
            card = cards[i];
            gestureId = getGestureIdFromCard(card);
            can = !!animatableMap[gestureId];
            execBtn = card.querySelector(".exec-btn");

            applyLocalTestingState(card, can, execBtn);
        }
    }

    function watchGrid() {
        var refs = PS.state.getRefs();
        var observer;

        if (!window.MutationObserver || observerStarted || !refs.mediaGrid) {
            return;
        }

        observerStarted = true;

        observer = new MutationObserver(function () {
            enhanceAll();
        });

        observer.observe(refs.mediaGrid, {
            childList: true,
            subtree: true
        });
    }

    function init() {
        watchGrid();

        window.addEventListener("storage", function (ev) {
            if (ev.key === LOCAL_DISABLE_KEY) {
                refreshLocalTestingStateOnly();
            }
        });

        window.setInterval(function () {
            refreshLocalTestingStateOnly();
        }, 1000);
    }

    PS.cards.init = init;
    PS.cards.enhanceAll = enhanceAll;
    PS.cards.areGestureButtonsDisabledLocally = areGestureButtonsDisabledLocally;
})(window);