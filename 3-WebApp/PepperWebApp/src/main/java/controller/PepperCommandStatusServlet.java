package controller;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

/**
 * Stato di un comando per il tablet: GET /api/pepper/command?id=...
 * status: queued | sent | done | failed | expired | unconfirmed
 */
@WebServlet("/api/pepper/command")
public class PepperCommandStatusServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String id = req.getParameter("id");
        PepperCommandBus bus = PepperCommandBus.getInstance();
        PepperCommand cmd = bus.find(id == null ? null : id.trim());

        if (cmd == null) {
            PepperApi.writeJson(resp, HttpServletResponse.SC_NOT_FOUND, PepperApi.error("Comando sconosciuto: " + id));
            return;
        }
        PepperApi.writeJson(resp, HttpServletResponse.SC_OK, PepperApi.describe(cmd, bus));
    }
}
