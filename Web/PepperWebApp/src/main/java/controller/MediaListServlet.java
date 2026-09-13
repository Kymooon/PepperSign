package controller;

import com.google.gson.Gson;
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import model.ElementoMultimediale;

import java.io.File;
import java.io.IOException;
import java.io.PrintWriter;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@WebServlet("/api/media")
public class MediaListServlet extends HttpServlet {

    private static final Gson GSON = new Gson();

    private static final String DEFAULT_MEDIA_DIR_PATH =
            System.getProperty("user.home") + File.separator + "PepperSignData";

    private String getMediaDirPath() {
        String configured = getServletConfig() != null ? getServletConfig().getInitParameter("mediaDirPath") : null;
        return (configured != null && !configured.trim().isEmpty())
                ? configured.trim()
                : DEFAULT_MEDIA_DIR_PATH;
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {

        String contextPath = request.getContextPath();
        List<ElementoMultimediale> elementi = scanMediaDirectory(contextPath);

        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");

        PrintWriter out = response.getWriter();
        out.print(GSON.toJson(elementi));
        out.flush();
    }

    private List<ElementoMultimediale> scanMediaDirectory(String contextPath) throws IOException {
        List<ElementoMultimediale> elementi = new ArrayList<ElementoMultimediale>();
        File mediaDir = new File(getMediaDirPath());

        if (!mediaDir.exists() || !mediaDir.isDirectory()) {
            log("Directory media non trovata o non valida: " + mediaDir.getAbsolutePath());
            return elementi;
        }

        File[] allFiles = mediaDir.listFiles();
        if (allFiles == null) {
            log("Impossibile leggere il contenuto della directory media: " + mediaDir.getAbsolutePath());
            return elementi;
        }

        Arrays.sort(allFiles, Comparator.comparing(File::getName, String.CASE_INSENSITIVE_ORDER));

        Map<String, String> videosByBaseName = buildVideoIndex(allFiles);
        List<File> imageFiles = collectImageFiles(allFiles);

        for (File imageFile : imageFiles) {
            String baseName = getBaseName(imageFile.getName());
            String normalizedBaseName = normalizeName(baseName);

            String videoFileName = videosByBaseName.get(normalizedBaseName);
            if (videoFileName == null) {
                continue;
            }

            String imgUrl = contextPath + "/media/" + encodePathSegment(imageFile.getName());
            String vidUrl = contextPath + "/media/" + encodePathSegment(videoFileName);

            elementi.add(new ElementoMultimediale(baseName, imgUrl, vidUrl));
        }

        return elementi;
    }

    private Map<String, String> buildVideoIndex(File[] files) {
        Map<String, String> videosByBaseName = new HashMap<String, String>();

        for (File file : files) {
            if (!file.isFile()) {
                continue;
            }

            String fileName = file.getName();
            if (!isVideoFile(fileName)) {
                continue;
            }

            String baseName = normalizeName(getBaseName(fileName));

            if (!videosByBaseName.containsKey(baseName)) {
                videosByBaseName.put(baseName, fileName);
            }
        }

        return videosByBaseName;
    }

    private List<File> collectImageFiles(File[] files) {
        List<File> imageFiles = new ArrayList<File>();

        for (File file : files) {
            if (file.isFile() && isImageFile(file.getName())) {
                imageFiles.add(file);
            }
        }

        return imageFiles;
    }

    private boolean isImageFile(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".jpg") || lower.endsWith(".png") || lower.endsWith(".jpeg") || lower.endsWith(".webp");
    }

    private boolean isVideoFile(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        return lower.endsWith(".mp4") || lower.endsWith(".mov");
    }

    private String getBaseName(String fileName) {
        int dotIndex = fileName.lastIndexOf('.');
        return (dotIndex == -1) ? fileName : fileName.substring(0, dotIndex);
    }

    private String normalizeName(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }

    private String encodePathSegment(String value) throws IOException {
        return URLEncoder.encode(value, "UTF-8").replace("+", "%20");
    }
}