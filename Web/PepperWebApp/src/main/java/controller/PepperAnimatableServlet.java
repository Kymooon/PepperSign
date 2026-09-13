package controller;

import com.google.gson.Gson;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Espone la lista dei gestureId animabili su Pepper.
 */
@WebServlet("/api/pepper/animatable")
public class PepperAnimatableServlet extends HttpServlet {

    private static final Gson GSON = new Gson();

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        Map<String, Object> out = new LinkedHashMap<String, Object>();
        out.put("animatable", PepperAnimatableGestures.list());

        writeJson(resp, HttpServletResponse.SC_OK, out);
    }

    private void writeJson(HttpServletResponse resp, int status, Map<String, Object> payload) throws IOException {
        resp.setStatus(status);
        resp.setContentType("application/json");
        resp.setCharacterEncoding("UTF-8");
        resp.getWriter().write(GSON.toJson(payload));
    }
}
