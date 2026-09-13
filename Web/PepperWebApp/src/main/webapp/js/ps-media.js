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
