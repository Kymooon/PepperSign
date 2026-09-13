/* PepperSign - ps-info-modal.js
   Modal dedicato alle informazioni testuali
*/
(function (window) {
    "use strict";

    var PS = window.PS = window.PS || {};
    PS.infoModal = PS.infoModal || {};

    var modal = null;
    var contentBox = null;
    var closeBtn = null;

    /* =========================
       CREATE MODAL (una volta sola)
    ========================= */
    function create() {
        if (modal) return;

        modal = document.createElement("div");
        modal.id = "psInfoModal";
        modal.style.display = "none";
        modal.style.position = "fixed";
        modal.style.top = "0";
        modal.style.left = "0";
        modal.style.right = "0";
        modal.style.bottom = "0";
        modal.style.background = "rgba(0,0,0,0.85)";
        modal.style.zIndex = "2000";
        modal.style.textAlign = "center";

        // container contenuto
        contentBox = document.createElement("div");
        contentBox.style.display = "inline-block";
        contentBox.style.verticalAlign = "middle";
        contentBox.style.background = "#ffffff";
        contentBox.style.color = "#243343";
        contentBox.style.padding = "24px";
        contentBox.style.borderRadius = "12px";
        contentBox.style.maxWidth = "640px";
        contentBox.style.width = "90%";
        contentBox.style.textAlign = "left";
        contentBox.style.boxShadow = "0 8px 24px rgba(0,0,0,0.3)";

        // hack vertical align (compat browser vecchi)
        var spacer = document.createElement("span");
        spacer.style.display = "inline-block";
        spacer.style.height = "100%";
        spacer.style.verticalAlign = "middle";

        // bottone chiusura
        closeBtn = document.createElement("button");
        closeBtn.innerHTML = "×";
        closeBtn.style.position = "absolute";
        closeBtn.style.top = "14px";
        closeBtn.style.right = "14px";
        closeBtn.style.width = "44px";
        closeBtn.style.height = "44px";
        closeBtn.style.borderRadius = "50%";
        closeBtn.style.border = "none";
        closeBtn.style.fontSize = "28px";
        closeBtn.style.background = "rgba(255,255,255,0.15)";
        closeBtn.style.color = "#fff";
        closeBtn.style.cursor = "pointer";

        modal.appendChild(spacer);
        modal.appendChild(contentBox);
        modal.appendChild(closeBtn);

        document.body.appendChild(modal);

        bind();
    }

    /* =========================
       OPEN
    ========================= */
    function open(htmlContent) {
        if (!modal) create();

        contentBox.innerHTML = htmlContent;
        modal.style.display = "block";
    }

    /* =========================
       CLOSE
    ========================= */
    function close() {
        if (!modal) return;
        modal.style.display = "none";
        contentBox.innerHTML = "";
    }

    /* =========================
       EVENTS
    ========================= */
    function bind() {
        closeBtn.addEventListener("click", close);

        modal.addEventListener("click", function (e) {
            if (e.target === modal) {
                close();
            }
        });
    }

    /* =========================
       INIT
    ========================= */
    function init() {
        create();
    }

    /* =========================
       EXPORT
    ========================= */
    PS.infoModal.init = init;
    PS.infoModal.open = open;
    PS.infoModal.close = close;

})(window);