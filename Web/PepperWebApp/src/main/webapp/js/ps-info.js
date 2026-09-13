/* PepperSign - ps-info.js
   Gestione bottoni info + contenuti dinamici
*/
(function (window, document) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.info = PS.info || {};

    /* =========================
       MAPPA CONTENUTI INFO
       👉 AGGIUNGI QUI NUOVE SEZIONI
    ========================= */
    var INFO_MAP = {

        // 🔹 ESEMPIO 1
        interazione: `
            <h2>Interazione con Pepper</h2>
            <p>
                Questa sezione permette di interagire direttamente con Pepper tramite voce.
            </p>
            <p>
                Premi il pulsante e parla chiaramente: il sistema utilizzerà il riconoscimento vocale
                per interpretare il comando.
            </p>
           
        `,

        // 🔹 ESEMPIO 2
        gesti: `
            <h2>Sezione Gesti</h2>
            <p>
                Qui sono presenti tutti i gesti disponibili che Pepper può eseguire.
            </p>
            <p>
                Puoi:
                <ul>
                    <li>visualizzare i gesti</li>
                    <li>eseguirli sul robot</li>
                    <li>testare le animazioni</li>
                </ul>
            </p>
           
        `

    };

    /* =========================
       RECUPERO CONTENUTO
    ========================= */
    function getInfoContent(key) {
        return INFO_MAP[key] || `
            <h2>Info</h2>
            <p>Nessuna informazione disponibile per questa sezione.</p>
        `;
    }

    /* =========================
       EVENTI CLICK (ROBUSTO)
    ========================= */
    function stripHtml(html) {
        var tmp = document.createElement("div");
        tmp.innerHTML = html;
        return tmp.textContent || tmp.innerText || "";
    }

    function bind() {
        document.addEventListener("click", function (e) {

            var btn = e.target.closest(".info-btn");
            if (!btn) return;

            var key = btn.getAttribute("data-info");
            var content = getInfoContent(key);

            if (PS.infoModal && PS.infoModal.open) {
                PS.infoModal.open(content);
            } else {
                console.error("PS.infoModal non disponibile");
            }

            var textToSpeak = stripHtml(content);

            if (PS.pepper && PS.pepper.animatedSay) {
                PS.pepper.animatedSay(textToSpeak);
            }
        });
    }

    /* =========================
       AUTO INIT
    ========================= */
    document.addEventListener("DOMContentLoaded", function () {
        bind();
    });

    /* =========================
       EXPORT (opzionale)
    ========================= */
    PS.info.getInfoContent = getInfoContent;

})(window, document);