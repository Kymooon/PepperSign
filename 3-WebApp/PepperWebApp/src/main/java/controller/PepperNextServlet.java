package controller;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * Polling di Controll: restituisce il prossimo comando per Pepper (e lo segna
 * come inviato) oppure {"action":"NONE"}. Ogni chiamata dice anche alla WebApp
 * che Controll e' collegato.
 */
@WebServlet("/api/pepper/next")
public class PepperNextServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        handle(resp);
    }

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        handle(resp);
    }

    private void handle(HttpServletResponse resp) throws IOException {
        PepperCommand cmd = PepperCommandBus.getInstance().poll();

        if (cmd == null) {
            cmd = PepperCommand.none();
        }

        PepperApi.writeJson(resp, HttpServletResponse.SC_OK, toMap(cmd));
    }

    static Map<String, Object> toMap(PepperCommand cmd) {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("action", cmd.getAction());
        out.put("text", cmd.getText() == null ? "" : cmd.getText());
        out.put("gestureId", cmd.getGestureId() == null ? "" : cmd.getGestureId());
        out.put("ts", cmd.getTs());
        if (cmd.getId() != null) {
            out.put("id", cmd.getId());
        }
        return out;
    }
}
