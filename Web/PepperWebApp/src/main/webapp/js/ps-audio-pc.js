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
