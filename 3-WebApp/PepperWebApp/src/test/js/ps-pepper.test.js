/*
 * Test di ps-pepper.js (esito dei comandi), senza browser e senza dipendenze.
 * Uso, dalla cartella PepperWebApp:   node src/test/js/ps-pepper.test.js
 * Le risposte del server sono simulate; ogni caso deve risolvere con {ok, status, message}.
 */
"use strict";
var path = require("path");

function response(status, body) {
    return {
        ok: status >= 200 && status < 300,
        status: status,
        json: function () {
            return typeof body === "string" ? Promise.reject(new SyntaxError("Unexpected token <"))
                                            : Promise.resolve(body);
        }
    };
}

global.window = global;
global.PS = {
    config: { urls: { pepperCommand: "/api/pepper/command", pepperAnimatedSay: "/api/pepper/animated-say" } },
    util: {
        sleep: function () { return Promise.resolve(); },
        formUrlEncode: function (o) { return Object.keys(o).map(function (k) { return k + "=" + o[k]; }).join("&"); },
        xhrRequest: null
    }
};
require(path.join(__dirname, "..", "..", "main", "webapp", "js", "ps-pepper.js"));

var failures = 0;
function check(label, actual, expected) {
    var ok = JSON.stringify(actual) === JSON.stringify(expected);
    console.log("  [" + (ok ? "OK  " : "FAIL") + "] " + label + (ok ? "" : " -> " + JSON.stringify(actual)));
    if (!ok) { failures++; }
}

/* xhrRequest che risponde con una sequenza fissa (POST e poi le GET dello stato) */
function server(responses) {
    var i = 0;
    PS.util.xhrRequest = function () {
        var r = responses[Math.min(i, responses.length - 1)];
        i++;
        return r === "network" ? Promise.reject(new Error("Network error")) : Promise.resolve(r);
    };
}

var cases = [
    ["eseguito", [response(200, { ok: true, id: "c1" }), response(200, { ok: true, status: "sent", "final": false }),
                  response(200, { ok: true, status: "done", "final": true, message: "detto" })],
     { ok: true, status: "done", message: "detto" }],
    ["fallito sul robot", [response(200, { ok: true, id: "c2" }),
                           response(200, { ok: true, status: "failed", "final": true, message: "gestureId non mappato: x" })],
     { ok: false, status: "failed", message: "gestureId non mappato: x" }],
    ["robot non collegato", [response(503, { ok: false, queued: false, robotOnline: false, error: "Robot non collegato" })],
     { ok: false, status: "offline", message: "Robot non collegato" }],
    ["coda piena", [response(503, { ok: false, queued: false, robotOnline: true, error: "Coda Pepper piena" })],
     { ok: false, status: "failed", message: "Coda Pepper piena" }],
    ["errore di rete all'invio", ["network"], { ok: false, status: "network", message: "Errore di rete" }],
    ["pagina HTML all'invio", [response(502, "<html>")], { ok: false, status: "failed", message: "HTTP 502" }],
    ["pagina HTML durante l'attesa (prima: Promise rifiutata)", [response(200, { ok: true, id: "c3" }), response(502, "<html>")],
     { ok: false, status: "failed", message: "Risposta non valida dal server (HTTP 502)" }],
    ["comando sconosciuto (WebApp riavviata)", [response(200, { ok: true, id: "c4" }),
                                                 response(404, { ok: false, error: "Comando sconosciuto: c4" })],
     { ok: false, status: "failed", message: "Comando sconosciuto: c4" }],
    ["scaduto in coda", [response(200, { ok: true, id: "c5" }), response(200, { ok: true, status: "expired", "final": true })],
     { ok: false, status: "expired", message: "Il robot non ha preso il comando in tempo" }]
];

var chain = Promise.resolve();
cases.forEach(function (c) {
    chain = chain.then(function () {
        server(c[1]);
        return PS.pepper.sendAndWait("/api/pepper/gesture", { gestureId: "x" }).then(function (r) {
            check(c[0], r, c[2]);
        }, function (e) {
            check(c[0] + " (Promise rifiutata)", String(e), c[2]);
        });
    });
});
chain.then(function () {
    server([response(200, { ok: true, id: "c6" }), response(200, { ok: true, status: "done", "final": true })]);
    return PS.pepper.animatedSay("ciao").then(function (r) {
        check("animatedSay restituisce l'esito", r, { ok: true, status: "done", message: "Eseguito" });
    });
}).then(function () {
    console.log("ESITO: " + (failures ? "FALLITI " + failures + " controlli" : "OK"));
    process.exit(failures ? 1 : 0);
});
