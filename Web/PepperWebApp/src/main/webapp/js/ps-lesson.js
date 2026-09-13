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
