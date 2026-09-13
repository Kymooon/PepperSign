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
