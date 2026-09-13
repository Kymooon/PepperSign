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
